"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { Sidebar } from "@/components/shared/Sidebar";
import { StatCard } from "@/components/dashboard/StatCard";
import { apiRequest } from "@/lib/api";
import { getActiveTenant, getAuthToken } from "@/lib/auth";
import {
  CreditCard,
  Receipt,
  CheckCircle,
  Layers,
  ArrowRight,
  AlertCircle,
  RefreshCw,
  XCircle,
  Building2,
  Copy,
  Check,
  Wallet,
  Sparkles,
  ShieldAlert,
  RotateCcw,
  ExternalLink,
} from "lucide-react";

interface ServiceItem {
  id: string;
  name: string;
  slug: string;
  category: string;
  description: string;
  configuration_schema?: {
    base_price?: number;
    industries?: string[];
    packages?: Array<{
      plan_name: string;
      display_name: string;
      price: number;
      billing_interval: string;
      features?: string[];
    }>;
  };
}

interface SubscriptionItem {
  id: string;
  service_id: string;
  service_name: string;
  service_slug: string;
  plan_name: string;
  status: string;
  price: number;
  billing_interval: string;
  started_at: string;
  expires_at?: string;
}

interface InvoiceItem {
  id: string;
  invoice_number: string;
  subtotal: number;
  tax: number;
  total: number;
  currency: string;
  status: string;
  due_at: string;
  created_at: string;
}

interface WalletState {
  balance_credits: number;
  low_balance_threshold: number;
  auto_pause_enabled: boolean;
  is_paused: boolean;
  low_balance_alert: boolean;
  lifetime_credited: number;
  lifetime_debited: number;
}

interface TrialState {
  trial_used: boolean;
  trial_active: boolean;
  trial_expired: boolean;
  trial_ends_at: string | null;
  trial_days_remaining: number;
  trial_grant_credits: number;
  trial_duration_days: number;
}

interface CreditPackItem {
  pack_id: string;
  name: string;
  credits: number;
  amount_usd: number;
  amount_pkr: number;
  description: string;
}

interface LedgerRow {
  id: string;
  entry_type: string;
  category: string;
  credits_delta: number;
  balance_after: number;
  description: string;
  created_at: string;
}

interface PaymentRecordItem {
  id: string;
  amount: number;
  currency: string;
  payment_method: string;
  provider_reference: string | null;
  status: string;
  paid_at: string | null;
  created_at: string;
}

interface CheckoutSessionResult {
  payment_id: string;
  provider: string;
  purpose: string;
  reference_id: string;
  amount: number;
  currency: string;
  credits_to_grant?: number | null;
  checkout_url?: string | null;
  instructions?: string | null;
}

export default function BillingPage() {
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionItem[]>([]);
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
  const [paymentsList, setPaymentsList] = useState<PaymentRecordItem[]>([]);
  const [wallet, setWallet] = useState<WalletState | null>(null);
  const [trial, setTrial] = useState<TrialState | null>(null);
  const [creditPacks, setCreditPacks] = useState<CreditPackItem[]>([]);
  const [creditRates, setCreditRates] = useState<Record<string, number>>({});
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [thresholdInput, setThresholdInput] = useState<string>("25");
  const [autoPauseInput, setAutoPauseInput] = useState<boolean>(false);
  const [savingWalletSettings, setSavingWalletSettings] = useState<boolean>(false);
  const [startingTrial, setStartingTrial] = useState<boolean>(false);
  const [checkoutCurrency, setCheckoutCurrency] = useState<"PKR" | "USD">("PKR");
  const [checkoutProvider, setCheckoutProvider] = useState<string>("payfast");
  const [checkoutLoading, setCheckoutLoading] = useState<boolean>(false);
  const [checkoutResult, setCheckoutResult] = useState<CheckoutSessionResult | null>(null);
  const [refundLoadingId, setRefundLoadingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [selectedPackages, setSelectedPackages] = useState<Record<string, string>>({});
  const [cancelingSubId, setCancelingSubId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<boolean>(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [bankDetails, setBankDetails] = useState({
    bank_name: "Faysal Bank",
    account_name: "Talha Azam",
    account_number: "3398701000005292",
    iban: "PK97FAYS3398701000005292",
  });

  const handleCopyBankField = (label: string, val: string) => {
    if (navigator?.clipboard) {
      navigator.clipboard.writeText(val);
      setCopiedField(label);
      setTimeout(() => setCopiedField(null), 2000);
    }
  };

  const fetchBillingData = async () => {
    const tenant = getActiveTenant();
    const indParam = tenant?.industry ? `&industry=${encodeURIComponent(tenant.industry)}` : "";
    setFetchError(null);
    setLoading(true);
    try {
      const [servicesRes, subsRes, invoicesRes, bankRes, walletRes, paymentsRes] = await Promise.all([
        apiRequest<ServiceItem[]>(`/api/v1/services?ensure_seeded=true${indParam}`),
        apiRequest<SubscriptionItem[]>("/api/v1/services/subscriptions"),
        apiRequest<InvoiceItem[]>("/api/v1/payments/invoices"),
        apiRequest<any>("/api/v1/payments/bank-details"),
        apiRequest<any>("/api/v1/payments/wallet"),
        apiRequest<PaymentRecordItem[]>("/api/v1/payments"),
      ]);
      if (bankRes?.data?.account_number) {
        setBankDetails(bankRes.data);
      }
      if (walletRes?.data) {
        const wData = walletRes.data;
        if (wData.wallet) {
          setWallet(wData.wallet);
          setThresholdInput(String(wData.wallet.low_balance_threshold ?? 25));
          setAutoPauseInput(Boolean(wData.wallet.auto_pause_enabled));
        }
        if (wData.trial) setTrial(wData.trial);
        if (Array.isArray(wData.credit_packs)) setCreditPacks(wData.credit_packs);
        if (wData.credit_rates) setCreditRates(wData.credit_rates);
        if (Array.isArray(wData.ledger)) setLedger(wData.ledger);
      }
      if (Array.isArray(paymentsRes)) setPaymentsList(paymentsRes);
      else if (Array.isArray((paymentsRes as any)?.data)) setPaymentsList((paymentsRes as any).data);

      const errors: string[] = [];
      if (servicesRes && !Array.isArray(servicesRes) && servicesRes.error) {
        errors.push(servicesRes.error.message || "Failed to load services");
      }
      if (subsRes && !Array.isArray(subsRes) && subsRes.error) {
        errors.push(subsRes.error.message || "Failed to load subscriptions");
      }
      if (invoicesRes && !Array.isArray(invoicesRes) && invoicesRes.error) {
        errors.push(invoicesRes.error.message || "Failed to load invoices");
      }

      if (errors.length > 0) {
        setFetchError(errors.join(" • "));
      }

      if (Array.isArray(servicesRes)) setServices(servicesRes);
      else if (Array.isArray(servicesRes.data)) setServices(servicesRes.data);

      const loadedSubs: SubscriptionItem[] = Array.isArray(subsRes)
        ? subsRes
        : Array.isArray(subsRes.data)
          ? subsRes.data
          : [];
      setSubscriptions(loadedSubs);
      setSelectedPackages((prev) => {
        const next = { ...prev };
        for (const sub of loadedSubs) {
          if (sub.status === "active" && !next[sub.service_id]) {
            next[sub.service_id] = (sub.plan_name || "starter").toLowerCase();
          }
        }
        return next;
      });

      if (Array.isArray(invoicesRes)) setInvoices(invoicesRes);
      else if (Array.isArray(invoicesRes.data)) setInvoices(invoicesRes.data);
    } catch (err: any) {
      setFetchError(err?.message || "Failed to load billing data. Please retry.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    const tenant = getActiveTenant();
    if (!tenant) {
      window.location.href = "/onboarding";
      return;
    }
    fetchBillingData();
  }, []);

  const handleSubscribe = async (serviceId: string, serviceName: string, price = 99.0, planName = "starter") => {
    setActionError(false);
    setActionMessage(`Activating subscription for ${serviceName}...`);
    const res = await apiRequest("/api/v1/services/subscribe", {
      method: "POST",
      body: JSON.stringify({
        service_id: serviceId,
        plan_name: planName,
        billing_interval: "monthly",
        price,
      }),
    });

    if (!res.error && (res.id || res.data?.id)) {
      setActionError(false);
      setActionMessage(`Subscribed to ${serviceName} (${planName.toUpperCase()} tier)! Invoice generated.`);
      fetchBillingData();
    } else {
      setActionError(true);
      setActionMessage(res.error?.message || "Failed to subscribe.");
    }
  };

  const handleCancelSubscription = async (subscriptionId: string, serviceName: string) => {
    setActionError(false);
    setCancelingSubId(subscriptionId);
    setActionMessage(`Canceling subscription for ${serviceName}...`);
    try {
      const res = await apiRequest(`/api/v1/services/subscriptions/${subscriptionId}/cancel`, {
        method: "POST",
      });
      if (!res.error && (res.id || res.data?.id || res.status === "canceled")) {
        setActionError(false);
        setActionMessage(`Subscription for "${serviceName}" has been canceled.`);
        await fetchBillingData();
      } else {
        setActionError(true);
        setActionMessage(res.error?.message || `Failed to cancel "${serviceName}".`);
      }
    } catch (err: any) {
      setActionError(true);
      setActionMessage(err?.message || "Failed to cancel subscription.");
    } finally {
      setCancelingSubId(null);
    }
  };

  const handleStartFreeTrial = async () => {
    setActionError(false);
    setStartingTrial(true);
    setActionMessage("Activating 7-Day Free Trial (100 starter credits)...");
    try {
      const res = await apiRequest<any>("/api/v1/payments/start-trial", { method: "POST" });
      if (res.success || res.data?.wallet) {
        setActionError(false);
        setActionMessage("7-Day Free Trial activated! 100 prepaid credits have been added to your wallet.");
        await fetchBillingData();
      } else {
        setActionError(true);
        setActionMessage(res.error?.message || "Failed to activate free trial.");
      }
    } catch (err: any) {
      setActionError(true);
      setActionMessage(err?.message || "Failed to activate free trial.");
    } finally {
      setStartingTrial(false);
    }
  };

  const handleSaveWalletSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingWalletSettings(true);
    setActionError(false);
    try {
      const res = await apiRequest<any>("/api/v1/payments/wallet/settings", {
        method: "PATCH",
        body: JSON.stringify({
          low_balance_threshold: Number(thresholdInput || 25),
          auto_pause_enabled: autoPauseInput,
        }),
      });
      if (res.success || res.data) {
        setActionError(false);
        setActionMessage("Wallet threshold and auto-pause protection saved.");
        await fetchBillingData();
      } else {
        setActionError(true);
        setActionMessage(res.error?.message || "Could not update wallet settings.");
      }
    } catch (err: any) {
      setActionError(true);
      setActionMessage(err?.message || "Could not update wallet settings.");
    } finally {
      setSavingWalletSettings(false);
    }
  };

  const handleStartCheckout = async (
    purpose: "subscription" | "wallet_topup",
    packId?: string,
    invoiceId?: string
  ) => {
    setCheckoutLoading(true);
    setActionError(false);
    setCheckoutResult(null);
    try {
      const res = await apiRequest<CheckoutSessionResult>("/api/v1/payments/checkout", {
        method: "POST",
        body: JSON.stringify({
          provider: checkoutProvider,
          purpose,
          pack_id: packId,
          invoice_id: invoiceId,
          currency: checkoutCurrency,
        }),
      });
      if (res.success && res.data) {
        setCheckoutResult(res.data);
        setActionError(false);
        setActionMessage(
          `Checkout ready via ${res.data.provider.toUpperCase()} (${res.data.amount} ${res.data.currency}). Reference: ${res.data.reference_id}`
        );
        await fetchBillingData();
      } else {
        setActionError(true);
        setActionMessage(res.error?.message || "Could not initialize checkout session.");
      }
    } catch (err: any) {
      setActionError(true);
      setActionMessage(err?.message || "Could not initialize checkout session.");
    } finally {
      setCheckoutLoading(false);
    }
  };

  const handleRequestRefund = async (paymentId: string) => {
    setRefundLoadingId(paymentId);
    setActionError(false);
    try {
      const res = await apiRequest<any>(`/api/v1/payments/${paymentId}/refund-request`, {
        method: "POST",
        body: JSON.stringify({
          reason: "Client requested billing refund review from Billing Portal",
        }),
      });
      if (res.success || res.data?.approval) {
        setActionError(false);
        setActionMessage(
          "Refund request queued for Human-in-the-Loop Admin approval on /approvals."
        );
      } else {
        setActionError(true);
        setActionMessage(res.error?.message || "Could not queue refund request.");
      }
    } catch (err: any) {
      setActionError(true);
      setActionMessage(err?.message || "Could not queue refund request.");
    } finally {
      setRefundLoadingId(null);
    }
  };

  const handlePayInvoice = async (invoiceId: string) => {
    setActionError(false);
    setActionMessage("Submitting invoice payment...");
    const res = await apiRequest(`/api/v1/payments/invoices/${invoiceId}/pay`, {
      method: "POST",
    });

    if (!res.error && (res.id || res.data?.id)) {
      const paymentStatus = res.status || res.data?.status;
      setActionError(false);
      if (paymentStatus === "completed") {
        setActionMessage("Payment successful! Invoice marked as paid.");
      } else {
        setActionMessage(
          "Bank transfer payment submitted (pending Super Admin confirmation). Invoice status is now payment_pending."
        );
      }
      fetchBillingData();
    } else {
      setActionError(true);
      setActionMessage(res.error?.message || "Payment submission failed.");
    }
  };

  const totalMonthlySpend = subscriptions
    .filter((s) => s.status === "active")
    .reduce((acc, curr) => acc + curr.price, 0);

  const unpaidInvoices = invoices.filter((inv) =>
    ["issued", "payment_pending", "overdue"].includes(inv.status)
  );
  const totalOutstanding = unpaidInvoices.reduce((acc, curr) => acc + curr.total, 0);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />

      <div className="flex flex-1">
        <Sidebar currentPath="/billing" />

        <main className="flex-1 min-w-0 p-4 sm:p-6 md:p-8 space-y-8 max-w-7xl mx-auto w-full">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-6">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                  Subscription & Billing
                </h1>
                <span className="rounded-full bg-emerald-100 text-emerald-800 px-2.5 py-0.5 text-xs font-semibold">
                  Payment Rails Active
                </span>
              </div>
              <p className="mt-1 text-xs sm:text-sm text-slate-500">
                Manage service subscriptions, review itemized invoices, and track billing history.
              </p>
            </div>
          </div>

          {fetchError && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-800">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{fetchError}</span>
              </div>
              <button
                type="button"
                onClick={fetchBillingData}
                disabled={loading}
                className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-50 transition self-start sm:self-auto"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                <span>Retry</span>
              </button>
            </div>
          )}

          {actionMessage && (
            <div
              className={`rounded-lg border p-3 text-xs font-medium ${
                actionError
                  ? "bg-red-50 border-red-200 text-red-800"
                  : "bg-emerald-50 border-emerald-200 text-emerald-800"
              }`}
            >
              {actionMessage}
            </div>
          )}

          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Active Subscriptions"
              value={subscriptions.filter((s) => s.status === "active").length}
              icon={Layers}
              badge={{ text: "Enabled", variant: "success" }}
              subtext="Platform services"
            />
            <StatCard
              title="Monthly Spend"
              value={`$${totalMonthlySpend.toFixed(2)}`}
              icon={CreditCard}
              badge={{ text: "Monthly", variant: "neutral" }}
              subtext="Next renewal: 30 days"
            />
            <StatCard
              title="Outstanding Balance"
              value={`$${totalOutstanding.toFixed(2)}`}
              icon={Receipt}
              badge={{
                text: totalOutstanding > 0 ? "Pending" : "Settled",
                variant: totalOutstanding > 0 ? "warning" : "success",
              }}
              subtext={`${unpaidInvoices.length} unpaid invoices`}
            />
            <StatCard
              title="Prepaid Credit Wallet"
              value={`${(wallet?.balance_credits ?? 0).toFixed(0)} cr`}
              icon={Wallet}
              badge={{
                text: wallet?.is_paused
                  ? "Auto-Paused"
                  : wallet?.low_balance_alert
                  ? "Low Balance"
                  : wallet?.auto_pause_enabled
                  ? "Protected"
                  : "Flexible",
                variant: wallet?.is_paused
                  ? "warning"
                  : wallet?.low_balance_alert
                  ? "warning"
                  : "success",
              }}
              subtext={`Alert below ${wallet?.low_balance_threshold ?? 25} credits`}
            />
          </div>

          {/* 7-Day Free Trial / Free Audit & Wallet Control */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="rounded-xl border border-emerald-500/30 bg-gradient-to-br from-emerald-950 via-slate-900 to-slate-950 p-6 text-white shadow-sm flex flex-col justify-between space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/20 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300 border border-emerald-500/30">
                    <Sparkles className="h-3 w-3" />
                    7-Day Free Trial
                  </span>
                  {trial?.trial_active && (
                    <span className="text-xs font-bold text-emerald-400">
                      {trial.trial_days_remaining} days left
                    </span>
                  )}
                </div>
                <h2 className="text-base font-extrabold text-white">
                  Free AI Audit &amp; 100 Starter Credits
                </h2>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Unlock your workspace immediately for 7 days with 100 prepaid credits to test AI Voice Receptionist calls, WhatsApp replies, and global lead discovery.
                </p>
              </div>
              {!trial?.trial_used ? (
                <button
                  type="button"
                  disabled={startingTrial}
                  onClick={handleStartFreeTrial}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2.5 text-xs font-extrabold text-slate-950 hover:bg-emerald-400 disabled:opacity-50 transition"
                >
                  <Sparkles className="h-4 w-4" />
                  <span>{startingTrial ? "Activating Trial..." : "Start 7-Day Free Trial (100 Credits)"}</span>
                </button>
              ) : trial.trial_active ? (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-200">
                  Trial active until{" "}
                  <strong className="text-white">
                    {trial.trial_ends_at ? new Date(trial.trial_ends_at).toLocaleDateString() : "7 days"}
                  </strong>
                  . Add payment before expiry for uninterrupted automation.
                </div>
              ) : (
                <div className="rounded-lg border border-slate-700 bg-slate-800/70 p-3 text-xs text-slate-300">
                  Trial already used on this workspace. Top up credits or activate your subscription below.
                </div>
              )}
            </div>

            <div className="lg:col-span-2 rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <Wallet className="h-5 w-5 text-emerald-600" />
                  <div>
                    <h2 className="text-base font-bold text-slate-900">
                      Prepaid Credit Rates &amp; Auto-Pause Protection
                    </h2>
                    <p className="text-xs text-slate-500">
                      Metered deductions prevent runaway AI or messaging spend when credits reach zero.
                    </p>
                  </div>
                </div>
                {wallet?.is_paused && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-red-100 text-red-700 px-2.5 py-0.5 text-xs font-bold">
                    <ShieldAlert className="h-3.5 w-3.5" />
                    Paused — Top Up Required
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                  <p className="text-[10px] uppercase text-slate-500 font-semibold">AI Voice Call</p>
                  <p className="text-sm font-bold text-slate-900 mt-0.5">
                    {creditRates.ai_call_minute ?? 5} cr / min
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                  <p className="text-[10px] uppercase text-slate-500 font-semibold">WhatsApp Msg</p>
                  <p className="text-sm font-bold text-slate-900 mt-0.5">
                    {creditRates.whatsapp_message ?? 1} cr / msg
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                  <p className="text-[10px] uppercase text-slate-500 font-semibold">Lead Discovery</p>
                  <p className="text-sm font-bold text-slate-900 mt-0.5">
                    {creditRates.lead_scrape ?? 2} cr / lead
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                  <p className="text-[10px] uppercase text-slate-500 font-semibold">Outreach Send</p>
                  <p className="text-sm font-bold text-slate-900 mt-0.5">
                    {creditRates.outreach_dispatch ?? 1} cr / send
                  </p>
                </div>
              </div>

              <form onSubmit={handleSaveWalletSettings} className="flex flex-wrap items-end gap-4 pt-1 text-xs">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600">
                    Low-Balance Alert Threshold (Credits)
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={thresholdInput}
                    onChange={(e) => setThresholdInput(e.target.value)}
                    className="mt-1 w-40 rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none"
                  />
                </div>
                <label className="flex items-center gap-2 py-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={autoPauseInput}
                    onChange={(e) => setAutoPauseInput(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="font-medium text-slate-700">
                    Enable Auto-Pause at 0 Credits
                  </span>
                </label>
                <button
                  type="submit"
                  disabled={savingWalletSettings}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50 transition"
                >
                  {savingWalletSettings ? "Saving..." : "Save Protection Settings"}
                </button>
              </form>
            </div>
          </div>

          {/* Multi-Currency Checkout & Prepaid Credit Packs (PKR + USD) */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-5">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-100 pb-4">
              <div>
                <h2 className="text-base font-bold text-slate-900">
                  Multi-Currency Checkout &amp; Credit Top-Up Packs
                </h2>
                <p className="text-xs text-slate-500">
                  Pay locally in PKR (PayFast, Safepay, Faysal Bank) or internationally in USD (Payoneer, Stripe).
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5">
                  <button
                    type="button"
                    onClick={() => {
                      setCheckoutCurrency("PKR");
                      setCheckoutProvider("payfast");
                    }}
                    className={`rounded-md px-3 py-1 font-bold transition ${
                      checkoutCurrency === "PKR"
                        ? "bg-slate-900 text-white"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    PKR (Pakistan)
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setCheckoutCurrency("USD");
                      setCheckoutProvider("payoneer");
                    }}
                    className={`rounded-md px-3 py-1 font-bold transition ${
                      checkoutCurrency === "USD"
                        ? "bg-slate-900 text-white"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    USD (International)
                  </button>
                </div>

                <select
                  value={checkoutProvider}
                  onChange={(e) => setCheckoutProvider(e.target.value)}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 focus:border-emerald-500 focus:outline-none"
                >
                  {checkoutCurrency === "PKR" ? (
                    <>
                      <option value="payfast">PayFast Pakistan (Cards / JazzCash / Easypaisa)</option>
                      <option value="safepay">Safepay Pakistan (PKR Gateway)</option>
                      <option value="bank_transfer">Faysal Bank Direct Transfer</option>
                    </>
                  ) : (
                    <>
                      <option value="payoneer">Payoneer International (USD)</option>
                      <option value="stripe">Stripe Checkout (USD Cards)</option>
                    </>
                  )}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {creditPacks.map((pack) => {
                const displayPrice =
                  checkoutCurrency === "PKR"
                    ? `PKR ${pack.amount_pkr.toLocaleString()}`
                    : `$${pack.amount_usd.toFixed(0)} USD`;
                return (
                  <div
                    key={pack.pack_id}
                    className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 flex flex-col justify-between space-y-3"
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-emerald-700">
                          +{pack.credits.toLocaleString()} Credits
                        </span>
                        <span className="text-sm font-extrabold text-slate-900">{displayPrice}</span>
                      </div>
                      <h3 className="text-sm font-bold text-slate-900 mt-1">{pack.name}</h3>
                      <p className="text-xs text-slate-600 mt-1">{pack.description}</p>
                    </div>
                    <button
                      type="button"
                      disabled={checkoutLoading}
                      onClick={() => handleStartCheckout("wallet_topup", pack.pack_id)}
                      className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition"
                    >
                      <span>Top Up via {checkoutProvider.toUpperCase()}</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })}
            </div>

            {checkoutResult && (
              <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-xs space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold text-emerald-950">
                    Checkout Initialized — {checkoutResult.provider.toUpperCase()} ({checkoutResult.amount}{" "}
                    {checkoutResult.currency})
                  </span>
                  <span className="font-mono font-semibold text-emerald-800">
                    Ref: {checkoutResult.reference_id}
                  </span>
                </div>
                {checkoutResult.instructions && (
                  <p className="text-emerald-900">{checkoutResult.instructions}</p>
                )}
                {checkoutResult.checkout_url && (
                  <a
                    href={checkoutResult.checkout_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 font-semibold text-white hover:bg-slate-800 transition"
                  >
                    <span>Open Gateway Checkout</span>
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            )}
          </div>

          {/* Service Marketplace Catalog */}
          <div className="space-y-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Available Platform Services</h2>
              <p className="text-xs text-slate-500">
                Select and activate services for your company workspace.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {services.map((srv) => {
                const activeSub = subscriptions.find(
                  (s) => s.service_id === srv.id && s.status === "active"
                );
                const isSubscribed = Boolean(activeSub);
                const packages = srv.configuration_schema?.packages || [];
                const defaultPlan = (
                  activeSub?.plan_name ||
                  packages[0]?.plan_name ||
                  "starter"
                ).toLowerCase();
                const chosenPlan = (selectedPackages[srv.id] || defaultPlan).toLowerCase();
                const activePkg =
                  packages.find((p) => p.plan_name.toLowerCase() === chosenPlan) ||
                  packages[0];
                const resolvedPrice =
                  activePkg?.price ?? srv.configuration_schema?.base_price ?? 99;
                const tierChanged = Boolean(
                  activeSub && chosenPlan !== (activeSub.plan_name || "").toLowerCase()
                );

                return (
                  <div
                    key={srv.id}
                    className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-6 shadow-sm hover:shadow-md transition"
                  >
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="rounded-full bg-slate-100 text-slate-700 px-2.5 py-0.5 text-[10px] font-semibold uppercase">
                          {srv.category}
                        </span>
                        {isSubscribed && (
                          <span className="flex items-center gap-1 text-[11px] font-bold text-emerald-600">
                            <CheckCircle className="h-3.5 w-3.5" />
                            Active ({activeSub?.plan_name})
                          </span>
                        )}
                      </div>

                      <h3 className="text-base font-bold text-slate-900">{srv.name}</h3>
                      <p className="text-xs text-slate-600 leading-relaxed">{srv.description}</p>

                      {packages.length > 0 && (
                        <div className="pt-2 space-y-2">
                          <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                            Select Package Tier
                          </label>
                          <div className="grid grid-cols-3 gap-1.5">
                            {packages.map((pkg) => {
                              const isChosen = pkg.plan_name.toLowerCase() === chosenPlan;
                              return (
                                <button
                                  key={pkg.plan_name}
                                  type="button"
                                  onClick={() =>
                                    setSelectedPackages((prev) => ({
                                      ...prev,
                                      [srv.id]: pkg.plan_name.toLowerCase(),
                                    }))
                                  }
                                  className={`rounded-lg border px-2 py-1.5 text-center text-[11px] transition ${
                                    isChosen
                                      ? "border-emerald-600 bg-emerald-50 text-emerald-900 font-bold"
                                      : "border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300"
                                  }`}
                                >
                                  <div className="capitalize">{pkg.plan_name}</div>
                                  <div className="font-mono text-emerald-700">${pkg.price}</div>
                                </button>
                              );
                            })}
                          </div>

                          {activePkg?.features && activePkg.features.length > 0 && (
                            <ul className="rounded-lg bg-slate-50 border border-slate-100 p-2.5 space-y-1 text-[11px] text-slate-600">
                              {activePkg.features.slice(0, 3).map((feat) => (
                                <li key={feat} className="flex items-start gap-1.5">
                                  <CheckCircle className="h-3 w-3 text-emerald-600 shrink-0 mt-0.5" />
                                  <span>{feat}</span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="mt-6 pt-4 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <span className="text-xl font-extrabold text-slate-900">
                          ${resolvedPrice}
                        </span>
                        <span className="text-xs text-slate-400"> / month</span>
                      </div>

                      {isSubscribed && activeSub ? (
                        <div className="flex flex-wrap items-center gap-2">
                          {tierChanged ? (
                            <button
                              type="button"
                              onClick={() =>
                                handleSubscribe(srv.id, srv.name, resolvedPrice, chosenPlan)
                              }
                              className="flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 transition"
                            >
                              <span>Switch Tier</span>
                              <ArrowRight className="h-3 w-3" />
                            </button>
                          ) : (
                            <span className="rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
                              Subscribed
                            </span>
                          )}
                          <button
                            type="button"
                            disabled={cancelingSubId === activeSub.id}
                            onClick={() => handleCancelSubscription(activeSub.id, srv.name)}
                            className="flex items-center gap-1 rounded-lg border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50 transition"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                            <span>
                              {cancelingSubId === activeSub.id ? "Canceling..." : "Cancel Subscription"}
                            </span>
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() =>
                            handleSubscribe(srv.id, srv.name, resolvedPrice, chosenPlan)
                          }
                          className="flex items-center gap-1 rounded-lg bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 transition"
                        >
                          <span>Subscribe</span>
                          <ArrowRight className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Direct Bank Transfer Instructions Banner */}
          <div className="rounded-xl border border-emerald-500/30 bg-slate-900 p-5 text-white shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500 text-slate-950 font-bold">
                  <Building2 className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">
                    Direct Bank Transfer Instructions ({bankDetails.bank_name})
                  </h3>
                  <p className="text-xs text-slate-400">
                    Transfer your invoice amount below, then submit your Transaction Reference on the
                    Dashboard for instant Admin approval.
                  </p>
                </div>
              </div>
              <a
                href="/dashboard"
                className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3.5 py-2 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition"
              >
                <span>Submit Transfer Reference on Dashboard →</span>
              </a>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                <p className="text-[10px] uppercase text-slate-400">Bank Name</p>
                <p className="font-bold text-white mt-0.5">{bankDetails.bank_name}</p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                <p className="text-[10px] uppercase text-slate-400">Account Title</p>
                <p className="font-bold text-white mt-0.5">{bankDetails.account_name}</p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3 flex items-center justify-between gap-2">
                <div>
                  <p className="text-[10px] uppercase text-slate-400">Account Number</p>
                  <p className="font-mono font-bold text-emerald-400 mt-0.5">
                    {bankDetails.account_number}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleCopyBankField("acc", bankDetails.account_number)}
                  className="rounded border border-slate-700 bg-slate-800 p-1.5 text-slate-300 hover:text-emerald-400"
                  title="Copy Account Number"
                >
                  {copiedField === "acc" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                </button>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3 flex items-center justify-between gap-2">
                <div>
                  <p className="text-[10px] uppercase text-slate-400">IBAN</p>
                  <p className="font-mono font-bold text-emerald-400 mt-0.5">
                    {bankDetails.iban}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleCopyBankField("iban", bankDetails.iban)}
                  className="rounded border border-slate-700 bg-slate-800 p-1.5 text-slate-300 hover:text-emerald-400"
                  title="Copy IBAN"
                >
                  {copiedField === "iban" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
          </div>

          {/* Invoices Table */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900">Billing Invoices</h3>
                <p className="text-xs text-slate-500">
                  Itemized invoice history and payment settlement.
                </p>
              </div>
              <span className="text-xs font-mono text-slate-500">{invoices.length} Invoices</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-400 uppercase font-semibold">
                    <th className="py-3 px-4">Invoice #</th>
                    <th className="py-3 px-4">Amount</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Due Date</th>
                    <th className="py-3 px-4">Created Date</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {invoices.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-slate-400">
                        No billing invoices generated yet.
                      </td>
                    </tr>
                  ) : (
                    invoices.map((inv) => (
                      <tr key={inv.id} className="hover:bg-slate-50 transition">
                        <td className="py-3 px-4 font-mono font-medium text-slate-900">
                          {inv.invoice_number}
                        </td>
                        <td className="py-3 px-4 font-semibold text-slate-900">
                          ${inv.total.toFixed(2)} {inv.currency}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                              inv.status === "paid"
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-amber-100 text-amber-800"
                            }`}
                          >
                            {inv.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-slate-500">
                          {new Date(inv.due_at).toLocaleDateString()}
                        </td>
                        <td className="py-3 px-4 text-slate-500">
                          {new Date(inv.created_at).toLocaleDateString()}
                        </td>
                        <td className="py-3 px-4 text-right">
                          {inv.status === "issued" || inv.status === "overdue" ? (
                            <button
                              onClick={() => handlePayInvoice(inv.id)}
                              className="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500 transition"
                            >
                              Submit Payment
                            </button>
                          ) : inv.status === "payment_pending" ? (
                            <span className="text-[11px] text-amber-600 font-semibold">
                              Pending Confirmation
                            </span>
                          ) : inv.status === "paid" ? (
                            <span className="text-[11px] text-emerald-600 font-medium">Settled</span>
                          ) : (
                            <span className="text-[11px] text-slate-400 uppercase">{inv.status}</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Usage Ledger & Payment Refund History */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-slate-900">Credit Usage Ledger</h3>
                  <p className="text-xs text-slate-500">
                    Real-time log of trial grants, credit top-ups, and metered deductions.
                  </p>
                </div>
                <span className="text-xs font-mono text-slate-500">{ledger.length} entries</span>
              </div>
              <div className="overflow-x-auto max-h-80">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-400 uppercase font-semibold">
                      <th className="py-2 pr-3">Description</th>
                      <th className="py-2 px-3">Credits</th>
                      <th className="py-2 pl-3 text-right">Balance</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {ledger.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="py-6 text-center text-slate-400">
                          No credit transactions recorded yet.
                        </td>
                      </tr>
                    ) : (
                      ledger.map((row) => (
                        <tr key={row.id}>
                          <td className="py-2.5 pr-3">
                            <div className="font-medium text-slate-900">{row.description}</div>
                            <div className="text-[10px] text-slate-400">
                              {row.category} • {new Date(row.created_at).toLocaleString()}
                            </div>
                          </td>
                          <td
                            className={`py-2.5 px-3 font-mono font-bold ${
                              row.credits_delta >= 0 ? "text-emerald-600" : "text-amber-700"
                            }`}
                          >
                            {row.credits_delta >= 0 ? "+" : ""}
                            {row.credits_delta.toFixed(2)}
                          </td>
                          <td className="py-2.5 pl-3 text-right font-mono text-slate-800">
                            {row.balance_after.toFixed(2)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    Payments &amp; Human-Approved Refunds
                  </h3>
                  <p className="text-xs text-slate-500">
                    Refunds are strictly routed to Admin Human-in-the-Loop approval.
                  </p>
                </div>
                <span className="text-xs font-mono text-slate-500">{paymentsList.length} payments</span>
              </div>
              <div className="overflow-x-auto max-h-80">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-400 uppercase font-semibold">
                      <th className="py-2 pr-3">Reference</th>
                      <th className="py-2 px-3">Amount</th>
                      <th className="py-2 px-3">Status</th>
                      <th className="py-2 pl-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {paymentsList.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="py-6 text-center text-slate-400">
                          No payment records yet.
                        </td>
                      </tr>
                    ) : (
                      paymentsList.map((p) => (
                        <tr key={p.id}>
                          <td className="py-2.5 pr-3">
                            <div className="font-mono font-semibold text-slate-900">
                              {p.provider_reference || p.id.slice(0, 8)}
                            </div>
                            <div className="text-[10px] text-slate-400 uppercase">
                              {p.payment_method}
                            </div>
                          </td>
                          <td className="py-2.5 px-3 font-semibold text-slate-900">
                            {p.amount.toFixed(2)} {p.currency}
                          </td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                                p.status === "completed"
                                  ? "bg-emerald-100 text-emerald-800"
                                  : p.status === "refunded"
                                  ? "bg-slate-200 text-slate-700"
                                  : "bg-amber-100 text-amber-800"
                              }`}
                            >
                              {p.status}
                            </span>
                          </td>
                          <td className="py-2.5 pl-3 text-right">
                            {p.status === "completed" ? (
                              <button
                                type="button"
                                disabled={refundLoadingId === p.id}
                                onClick={() => handleRequestRefund(p.id)}
                                className="inline-flex items-center gap-1 rounded border border-slate-300 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                              >
                                <RotateCcw className="h-3 w-3" />
                                <span>
                                  {refundLoadingId === p.id ? "Queuing..." : "Request Refund"}
                                </span>
                              </button>
                            ) : (
                              <span className="text-[11px] text-slate-400">—</span>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
