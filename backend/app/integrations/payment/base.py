"""Multi-Currency Payment Provider Abstraction Layer (PKR + USD).

Supports:
1. ManualPaymentProvider (Faysal Bank Direct PKR Transfer)
2. StripeProvider (USD Checkout Sessions + HMAC-SHA256 `t=...,v1=...` webhooks)
3. PayFastPakistanProvider (PKR Hosted Checkout + HMAC-SHA256 webhooks)
4. SafepayProvider (PKR Safepay Order Init + `X-SFPY-SIGNATURE` HMAC webhooks)
5. PayoneerProvider (USD Payoneer Receiving Account + HMAC webhooks)
"""

import hashlib
import hmac
import urllib.parse
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx
from app.config import settings
from pydantic import BaseModel


class PaymentIntentResult(BaseModel):
    success: bool
    provider: str = "manual"
    reference_id: str
    amount: float
    currency: str
    status: str  # pending, completed, failed
    checkout_url: Optional[str] = None
    checkout_fields: Optional[Dict[str, Any]] = None
    instructions: Optional[str] = None
    is_mock: bool = False


def _verify_hex_hmac(secret: Optional[str], payload: bytes, signature: str) -> bool:
    if not signature:
        return False
    clean_sig = signature.strip()
    if clean_sig.lower().startswith("sha256="):
        clean_sig = clean_sig.split("=", 1)[1].strip()
    clean_secret = (secret or "").strip()
    if clean_secret and clean_secret not in ("your-payment-webhook-secret", "mock"):
        expected = hmac.new(clean_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(clean_sig.lower(), expected.lower())
    if settings.app_env in ("development", "test"):
        return clean_sig == "valid_test_signature"
    return False


class PaymentProvider(ABC):
    """Abstract payment gateway interface."""

    @abstractmethod
    async def create_payment_intent(
        self,
        tenant_id: str,
        amount: float,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        """Create a payment intent or return deposit instructions."""
        pass

    @abstractmethod
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        """Cryptographically verify incoming provider webhook payload."""
        pass


class ManualPaymentProvider(PaymentProvider):
    """Manual Payment Provider (Faysal Bank Direct PKR Transfer)."""

    async def create_payment_intent(
        self,
        tenant_id: str,
        amount: float,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        ref_id = f"FAYS-{tenant_id[:8].upper()}-{uuid.uuid4().hex[:6].upper()}"
        return PaymentIntentResult(
            success=True,
            provider="bank_transfer",
            reference_id=ref_id,
            amount=amount,
            currency=currency,
            status="pending",
            instructions=(
                f"Transfer {amount:,.2f} {currency} to Faysal Bank (Title: Talha Azam, "
                f"Account: 3398701000005292, IBAN: PK97FAYS3398701000005292). "
                f"Submit reference '{ref_id}' on /dashboard or /billing for admin confirmation."
            ),
            is_mock=False,
        )

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        return False


class StripeProvider(PaymentProvider):
    """Stripe USD Adapter with real Checkout Session creation (when configured) and HMAC-SHA256 webhooks."""

    async def create_payment_intent(
        self,
        tenant_id: str,
        amount: float,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        secret = (settings.stripe_secret_key or settings.payment_secret_key or "").strip()
        meta = dict(metadata or {})
        meta.setdefault("tenant_id", tenant_id)
        ref_id = f"cs_{uuid.uuid4().hex[:14]}"

        if secret and secret.startswith("sk_") and settings.app_env != "test":
            cents = max(50, int(round(float(amount) * 100)))
            form_data = {
                "mode": "payment",
                "success_url": f"{settings.frontend_url}/billing?checkout=success&provider=stripe&ref={ref_id}",
                "cancel_url": f"{settings.frontend_url}/billing?checkout=cancelled&provider=stripe",
                "line_items[0][price_data][currency]": currency.lower()[:3],
                "line_items[0][price_data][product_data][name]": str(
                    meta.get("description") or "TaloxTech AI SaaS Service & Credits"
                )[:120],
                "line_items[0][price_data][unit_amount]": str(cents),
                "line_items[0][quantity]": "1",
                "metadata[tenant_id]": str(tenant_id),
                "metadata[purpose]": str(meta.get("purpose") or "subscription"),
                "metadata[provider_reference]": ref_id,
            }
            if meta.get("credits"):
                form_data["metadata[credits]"] = str(meta["credits"])
            if meta.get("invoice_id"):
                form_data["metadata[invoice_id]"] = str(meta["invoice_id"])
            if meta.get("subscription_id"):
                form_data["metadata[subscription_id]"] = str(meta["subscription_id"])

            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(
                        "https://api.stripe.com/v1/checkout/sessions",
                        data=form_data,
                        headers={"Authorization": f"Bearer {secret}"},
                    )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        return PaymentIntentResult(
                            success=True,
                            provider="stripe",
                            reference_id=str(data.get("id") or ref_id),
                            amount=amount,
                            currency=currency.upper()[:3],
                            status="pending",
                            checkout_url=data.get("url"),
                            instructions="Complete your USD card payment on Stripe Checkout; your workspace activates automatically via webhook.",
                            is_mock=False,
                        )
            except Exception:
                pass

        return PaymentIntentResult(
            success=True,
            provider="stripe",
            reference_id=f"pi_sandbox_{tenant_id[:8]}_{uuid.uuid4().hex[:6]}",
            amount=amount,
            currency=currency.upper()[:3],
            status="pending",
            checkout_url=f"{settings.frontend_url}/billing?sandbox_checkout=stripe&ref={ref_id}",
            instructions="Stripe sandbox checkout prepared. Configure STRIPE_SECRET_KEY & STRIPE_WEBHOOK_SECRET in Render for live card processing.",
            is_mock=True,
        )

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        if not signature:
            return False

        secret = (settings.stripe_webhook_secret or settings.payment_webhook_secret or "").strip()
        if secret and secret != "your-payment-webhook-secret":
            timestamp: Optional[str] = None
            v1_signatures = []
            for part in signature.split(","):
                key, _, val = part.strip().partition("=")
                if key == "t" and val:
                    timestamp = val
                elif key == "v1" and val:
                    v1_signatures.append(val)
            if not timestamp or not v1_signatures:
                return False
            signed_payload = f"{timestamp}.".encode("utf-8") + payload
            expected_sig = hmac.new(
                secret.encode("utf-8"),
                signed_payload,
                hashlib.sha256,
            ).hexdigest()
            return any(hmac.compare_digest(sig, expected_sig) for sig in v1_signatures)

        if settings.app_env in ("development", "test"):
            return signature == "valid_test_signature"
        return False


class PayFastPakistanProvider(PaymentProvider):
    """PayFast Pakistan (PKR) Hosted Checkout & HMAC Webhook Adapter."""

    async def create_payment_intent(
        self,
        tenant_id: str,
        amount: float,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        merchant_id = (settings.payfast_merchant_id or "").strip()
        secured_key = (settings.payfast_secured_key or "").strip()
        basket_id = f"PF-{tenant_id[:8].upper()}-{uuid.uuid4().hex[:6].upper()}"
        amount_str = f"{float(amount):.2f}"
        is_live = bool(merchant_id and secured_key)

        query_params = {
            "MERCHANT_ID": merchant_id or "PAYFAST_SANDBOX_MERCHANT",
            "BASKET_ID": basket_id,
            "TXNAMT": amount_str,
            "CURRENCY_CODE": currency.upper()[:3] or "PKR",
            "PROCCODE": "00",
            "SUCCESS_URL": f"{settings.frontend_url}/billing?checkout=success&provider=payfast&ref={basket_id}",
            "FAILURE_URL": f"{settings.frontend_url}/billing?checkout=failed&provider=payfast&ref={basket_id}",
            "CHECKOUT_URL": f"{settings.backend_url}/api/v1/payments/webhooks/payfast",
        }
        base_url = settings.payfast_base_url.rstrip("/")
        checkout_url = f"{base_url}/PostTransaction?{urllib.parse.urlencode(query_params)}"

        return PaymentIntentResult(
            success=True,
            provider="payfast",
            reference_id=basket_id,
            amount=float(amount),
            currency=currency.upper()[:3] or "PKR",
            status="pending",
            checkout_url=checkout_url,
            checkout_fields=query_params,
            instructions=(
                f"Pay {amount_str} {query_params['CURRENCY_CODE']} via PayFast Pakistan (JazzCash/Easypaisa/Cards/Bank) using Basket ID {basket_id}."
                if is_live
                else f"PayFast PKR sandbox checkout prepared (Basket {basket_id}). Add PAYFAST_MERCHANT_ID & PAYFAST_SECURED_KEY on Render to activate live PKR merchant checkout."
            ),
            is_mock=not is_live,
        )

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        secret = (settings.payfast_secured_key or settings.payment_webhook_secret or "").strip()
        return _verify_hex_hmac(secret, payload, signature)


class SafepayProvider(PaymentProvider):
    """Safepay Pakistan (PKR / Visa / Mastercard / Wallet) Adapter."""

    async def create_payment_intent(
        self,
        tenant_id: str,
        amount: float,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        api_key = (settings.safepay_api_key or "").strip()
        ref_id = f"SF-{tenant_id[:8].upper()}-{uuid.uuid4().hex[:6].upper()}"
        curr = currency.upper()[:3] or "PKR"

        if api_key and settings.app_env != "test":
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(
                        f"{settings.safepay_base_url.rstrip('/')}/order/v1/init",
                        json={
                            "client": api_key,
                            "amount": round(float(amount), 2),
                            "currency": curr,
                            "environment": "production" if settings.app_env == "production" else "sandbox",
                            "order_id": ref_id,
                        },
                    )
                    if resp.status_code in (200, 201):
                        data = (resp.json().get("data") or {})
                        tracker = data.get("token") or ref_id
                        return PaymentIntentResult(
                            success=True,
                            provider="safepay",
                            reference_id=str(tracker),
                            amount=float(amount),
                            currency=curr,
                            status="pending",
                            checkout_url=f"https://www.getsafepay.com/checkout/pay?tracker={urllib.parse.quote(str(tracker))}&order_id={ref_id}",
                            instructions=f"Complete PKR payment via Safepay using tracker {tracker}.",
                            is_mock=False,
                        )
            except Exception:
                pass

        return PaymentIntentResult(
            success=True,
            provider="safepay",
            reference_id=ref_id,
            amount=float(amount),
            currency=curr,
            status="pending",
            checkout_url=f"{settings.frontend_url}/billing?sandbox_checkout=safepay&ref={ref_id}",
            instructions=f"Safepay checkout prepared (Ref: {ref_id}). Add SAFEPAY_API_KEY & SAFEPAY_WEBHOOK_SECRET on Render for live processing.",
            is_mock=not bool(api_key),
        )

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        secret = (settings.safepay_webhook_secret or settings.payment_webhook_secret or "").strip()
        return _verify_hex_hmac(secret, payload, signature)


class PayoneerProvider(PaymentProvider):
    """Payoneer International USD Adapter."""

    async def create_payment_intent(
        self,
        tenant_id: str,
        amount: float,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        payoneer_email = (settings.payoneer_account_email or "").strip()
        is_live = bool(payoneer_email and payoneer_email.lower() != "mock")
        ref_id = f"PYNR-{tenant_id[:8].upper()}-{uuid.uuid4().hex[:6].upper()}"
        details = (settings.payoneer_receiving_details or "").strip()

        return PaymentIntentResult(
            success=True,
            provider="payoneer",
            reference_id=ref_id,
            amount=float(amount),
            currency=currency.upper()[:3] or "USD",
            status="pending",
            instructions=(
                details
                or (
                    f"Send ${float(amount):,.2f} USD via Payoneer to {payoneer_email} with Memo '{ref_id}'."
                    if is_live
                    else f"Payoneer USD reference '{ref_id}' generated. Payoneer account approval pending — add PAYONEER_ACCOUNT_EMAIL on Render once approved."
                )
            ),
            is_mock=not is_live,
        )

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        secret = (settings.payoneer_webhook_secret or settings.payment_webhook_secret or "").strip()
        return _verify_hex_hmac(secret, payload, signature)


# Preserve backwards-compatible symbol name
MockStripeProvider = StripeProvider


def get_payment_provider(provider_type: str = "manual") -> PaymentProvider:
    """Factory resolving configured payment provider."""
    normalized = (provider_type or "manual").strip().lower()
    if normalized == "stripe":
        return StripeProvider()
    if normalized == "payfast":
        return PayFastPakistanProvider()
    if normalized == "safepay":
        return SafepayProvider()
    if normalized == "payoneer":
        return PayoneerProvider()
    return ManualPaymentProvider()
