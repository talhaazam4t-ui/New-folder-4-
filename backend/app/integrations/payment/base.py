"""Payment Provider Abstraction Layer.

Defines the contract for payment rails (Manual/Bank Transfer, Stripe, Local Pakistan Rails),
ensuring zero tight coupling to any single gateway.
"""

import hashlib
import hmac
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.config import settings
from pydantic import BaseModel


class PaymentIntentResult(BaseModel):
    success: bool
    reference_id: str
    amount: float
    currency: str
    status: str  # pending, completed, failed
    checkout_url: Optional[str] = None
    instructions: Optional[str] = None
    is_mock: bool = False


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
    """Manual Payment Provider (Bank Transfer / Cash / Cheque).

    Enables verified offline payment records without third-party fees.
    """

    async def create_payment_intent(
        self,
        tenant_id: str,
        amount: float,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        ref_id = f"MANUAL-{tenant_id[:8].upper()}-{int(amount)}"
        return PaymentIntentResult(
            success=True,
            reference_id=ref_id,
            amount=amount,
            currency=currency,
            status="pending",
            instructions=(
                f"Please transfer {amount} {currency} to Account: TALOX-CORP-99201. "
                f"Include Reference ID '{ref_id}' on your slip and upload proof."
            ),
            is_mock=False,
        )

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        # Manual provider does not support automated webhooks
        return False


class MockStripeProvider(PaymentProvider):
    """Stripe Adapter with HMAC-SHA256 webhook verification and dev/test sandbox fallback."""

    async def create_payment_intent(
        self,
        tenant_id: str,
        amount: float,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        return PaymentIntentResult(
            success=True,
            reference_id=f"pi_mock_{tenant_id[:8]}",
            amount=amount,
            currency=currency,
            status="completed",
            checkout_url="https://checkout.stripe.mock/pay",
            is_mock=True,
        )

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        if not signature:
            return False

        secret = (settings.payment_webhook_secret or "").strip()
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


def get_payment_provider(provider_type: str = "manual") -> PaymentProvider:
    """Factory resolving configured payment provider."""
    if provider_type == "stripe":
        return MockStripeProvider()
    return ManualPaymentProvider()
