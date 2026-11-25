"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { Sidebar } from "@/components/shared/Sidebar";
import { StatCard } from "@/components/dashboard/StatCard";
import { apiRequest } from "@/lib/api";
import { getActiveTenant, getAuthToken } from "@/lib/auth";
import {
  Users,
  MessageSquare,
  CalendarCheck,
  TrendingUp,
  CheckCircle2,
  AlertCircle,
  Layers,
  Briefcase,
  Activity,
  FileBarChart,
  CreditCard,
  Sparkles,
  Copy,
  Check,
  Lock,
  Building2,
  Send,
  Clock,
  RefreshCw,
  PhoneCall,
} from "lucide-react";

interface OverviewPayload {
  tenant_id: string;
  tenant_name: string;
  role: string;
  selected_industry: string;
  service_status: string;
  automation_active: boolean;
  is_payment_approved?: boolean;
  payment_notified?: boolean;
  payment_reference?: string | null;
  wallet_summary?: {
    balance_credits: number;
    low_balance_threshold: number;
    auto_pause_enabled: boolean;
    is_paused: boolean;
    low_balance_alert: boolean;
  };
  trial_info?: {
    trial_used: boolean;
    trial_active: boolean;
    trial_expired: boolean;
    trial_ends_at: string | null;
    trial_days_remaining: number;
  };
  bank_details?: {
    bank_name: string;
    account_name: string;
    account_number: string;
    iban: string;
  };
  payment_rails?: {
    bank_transfer: {
      bank_name: string;
      account_name: string;
      account_number: string;
      iban: string;
    };
    payoneer: {
      enabled: boolean;
      status: string;
      account_email: string;
      receiving_details: string;
      currency: string;
    };
  };
  current_package: string;
  purchased_services: Array<{
    slot_number?: number;
    subscription_id: string;
    service_id: string;
    service_name: string;
    service_slug?: string;
    plan_name: string;
    price: number;
    billing_interval: string;
    status: string;
    required_integrations?: string[];
  }>;
  purchased_service_slugs?: string[];
  enabled_modules?: string[];
  outreach_performance?: {
    plan_name: string;
    monthly_lead_limit: number;
    leads_used_this_month: number;
    remaining_leads: number;
    quota_exhausted: boolean;
    gmail_drafts_ready: number;
    whatsapp_pitches_ready: number;
    linkedin_pitches_ready: number;
    pending_outreach_approvals: number;
    approved_sent_count: number;
  };
  subscription_info: {
    active_services_count: number;
    current_package: string;
    monthly_investment: number;
    billing_cycle: string;
    status: string;
  };
  integrations_status: Array<{
    provider: string;
    display_name: string;
    status: string;
    external_account_id: string | null;
  }>;
  metrics: {
    income: number;
    expenses: number;
    net_profit: number;
    outstanding: number;
    leads: number;
    leads_generated: number;
    qualified_leads: number;
    messages_sent: number;
    meetings_booked: number;
    conversion_rate: number;
  };
  lead_performance: Array<{
    id: string;
    name: string;
    source: string;
    status: string;
    qualification_score: number;
    messages_sent: number;
    meeting_booked: boolean;
    created_at: string;
  }>;
  appointment_performance: Array<{
    lead_id: string;
    client_name: string;
    meeting_title: string;
    scheduled_at: string;
    status: string;
  }>;
  recent_activity: Array<{
    id: string;
    action: string;
    resource_type: string;
    timestamp: string;
  }>;
  reports: {
    period: string;
    leads_generated: number;
    qualified_leads: number;
    messages_sent: number;
    meetings_booked: number;
    conversion_rate: number;
    net_business_value: number;
  };
}

export default function ClientDashboardPage() {
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  // 1-Click Copy States for Bank Account & IBAN
  const [copiedAccount, setCopiedAccount] = useState(false);
  const [copiedIban, setCopiedIban] = useState(false);

  // Payment Notification Form States
  const [isNotifyingPayment, setIsNotifyingPayment] = useState(false);
  const [txnRefInput, setTxnRefInput] = useState("");
  const [txnNotesInput, setTxnNotesInput] = useState("");
  const [notifyLoading, setNotifyLoading] = useState(false);
  const [notifySuccessMsg, setNotifySuccessMsg] = useState<string | null>(null);
  const [notifyErrorMsg, setNotifyErrorMsg] = useState<string | null>(null);
  const [trialStarting, setTrialStarting] = useState(false);

  const handleStartTrialFromDashboard = async () => {
    setTrialStarting(true);
    setNotifyErrorMsg(null);
    setNotifySuccessMsg(null);
    try {
      const res = await apiRequest("/api/v1/payments/start-trial", { method: "POST" });
      if (res.success || (res as any).data?.wallet) {
        setNotifySuccessMsg(
          "7-Day Free Trial activated with 100 starter credits! Your AI services are now unlocked."
        );
        await loadClientPerformance();
      } else {
        setNotifyErrorMsg(res.error?.message || "Failed to activate 7-day free trial.");
      }
    } catch (err: any) {
      setNotifyErrorMsg(err?.message || "Failed to activate 7-day free trial.");
    } finally {
      setTrialStarting(false);
    }
  };

  const loadClientPerformance = async () => {
    const tenant = getActiveTenant();
    if (!tenant?.id) {
      window.location.href = "/onboarding";
      return;
    }

    setOverviewError(null);
    setLoading(true);
    try {
      const res = await apiRequest<OverviewPayload>(`/api/v1/tenants/${tenant.id}/overview`);
      if (res.data) {
        setOverview(res.data);
        if (typeof window !== "undefined" && Array.isArray(res.data.enabled_modules)) {
          sessionStorage.setItem(
            `talox_enabled_modules_${tenant.id}`,
            JSON.stringify(res.data.enabled_modules)
          );
        }
      } else {
        setOverviewError(
          res.error?.message || "Failed to load workspace performance overview."
        );
      }
    } catch (err: any) {
      setOverviewError(
        err?.message || "Failed to communicate with performance overview API."
      );
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
    loadClientPerformance();
  }, []);

  const copyToClipboard = (text: string, type: "account" | "iban") => {
    if (navigator?.clipboard) {
      navigator.clipboard.writeText(text);
      if (type === "account") {
        setCopiedAccount(true);
        setTimeout(() => setCopiedAccount(false), 2000);
      } else {
        setCopiedIban(true);
        setTimeout(() => setCopiedIban(false), 2000);
      }
    }
  };

  const handleNotifyPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!txnRefInput.trim()) return;

    setNotifyLoading(true);
    setNotifyErrorMsg(null);
    setNotifySuccessMsg(null);

    try {
      const res = await apiRequest("/api/v1/payments/bank-transfer/notify", {
        method: "POST",
        body: JSON.stringify({
          transaction_reference: txnRefInput.trim(),
          notes: txnNotesInput.trim() || undefined,
        }),
      });

      if (res.success || (res as any).payment_id) {
        setNotifySuccessMsg(
          "Bank transfer submitted! Our admin team has been notified and will verify your payment to activate services."
        );
        setIsNotifyingPayment(false);
        loadClientPerformance();
      } else {
        setNotifyErrorMsg(res.error?.message || "Failed to submit transaction reference.");
      }
    } catch (err: any) {
      setNotifyErrorMsg(err.message || "An error occurred submitting payment notification.");
    } finally {
      setNotifyLoading(false);
    }
  };

  const m = overview?.metrics || {
    income: 0,
    expenses: 0,
    net_profit: 0,
    outstanding: 0,
    leads: 0,
    leads_generated: 0,
    qualified_leads: 0,
    messages_sent: 0,
    meetings_booked: 0,
    conversion_rate: 0,
  };

  const isApproved = Boolean(overview?.is_payment_approved);
  const isNotified = Boolean(overview?.payment_notified);
  const bankDetails = overview?.bank_details || {
    bank_name: "Faysal Bank",
    account_name: "Talha Azam",
    account_number: "3398701000005292",
    iban: "PK97FAYS3398701000005292",
  };

  const enabledModules = overview?.enabled_modules || [];
  const hasPurchasedServices = (overview?.purchased_services?.length ?? 0) > 0;
  const showAllByDefault = enabledModules.length === 0 && !hasPurchasedServices;
  const showConciergeModules =
    !isApproved ||
    showAllByDefault ||
    enabledModules.includes("whatsapp_concierge") ||
    enabledModules.includes("multi_agent_orchestration");
  const showLeadModules =
    !isApproved ||
    showAllByDefault ||
    enabledModules.includes("lead_crm") ||
    enabledModules.includes("marketing_growth") ||
    enabledModules.includes("lead_funnel") ||
    enabledModules.includes("multi_agent_orchestration");
  const showFinancialModules =
    !isApproved ||
    showAllByDefault ||
    enabledModules.includes("financial_ledger") ||
    enabledModules.includes("executive_analytics_compliance");
  const showReceptionistModule = enabledModules.includes("office_receptionist");

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />

      <div className="flex flex-1">
        <Sidebar currentPath="/dashboard" enabledModules={overview?.enabled_modules} />

        <main className="flex-1 min-w-0 p-4 sm:p-6 md:p-8 space-y-8 max-w-7xl mx-auto w-full">
          {overviewError && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-800">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{overviewError}</span>
              </div>
              <button
                type="button"
                onClick={loadClientPerformance}
                disabled={loading}
                className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-50 transition self-start sm:self-auto"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                <span>Retry</span>
              </button>
            </div>
          )}
          {/* Header Banner: Managed Service Status & Selected Industry */}
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-200 pb-6">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                  Managed Service Performance
                </h1>
                <span
                  className={`rounded-full px-3 py-0.5 text-xs font-semibold ${
                    isApproved
                      ? "bg-emerald-100 text-emerald-800"
                      : isNotified
                      ? "bg-blue-100 text-blue-800"
                      : "bg-amber-100 text-amber-800"
                  }`}
                >
                  {loading && !overview
                    ? "Loading workspace status..."
                    : isApproved
                    ? "Active — Delivering Outcomes"
                    : isNotified
                    ? "Payment Transfer Submitted — Verification In Progress"
                    : "Awaiting Bank Transfer Payment Approval"}
                </span>
              </div>
              <p className="mt-1 text-xs sm:text-sm text-slate-500">
                Done-for-you AI automation outcomes, lead conversions, booked appointments, and business results for{" "}
                <span className="font-semibold text-slate-800">
                  {overview?.tenant_name || "Your Workspace"}
                </span>
                .
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2 rounded-lg bg-white border border-slate-200 px-3.5 py-2 text-xs font-medium text-slate-700 shadow-sm">
                <Briefcase className="h-4 w-4 text-emerald-600" />
                <span>Industry:</span>
                <strong className="text-slate-900">
                  {overview?.selected_industry || "Not Selected"}
                </strong>
              </div>
              <a
                href="/billing"
                className={`flex items-center gap-2 rounded-lg border px-3.5 py-2 text-xs font-semibold shadow-sm transition ${
                  overview?.wallet_summary?.is_paused
                    ? "border-red-300 bg-red-50 text-red-800 hover:bg-red-100"
                    : overview?.wallet_summary?.low_balance_alert
                    ? "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100"
                    : "border-slate-200 bg-white text-slate-700 hover:border-emerald-300"
                }`}
              >
                <CreditCard className="h-4 w-4 text-emerald-600" />
                <span>Credits:</span>
                <strong className="font-mono text-slate-900">
                  {(overview?.wallet_summary?.balance_credits ?? 0).toFixed(0)} cr
                </strong>
                {overview?.trial_info?.trial_active && (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                    Trial {overview.trial_info.trial_days_remaining}d
                  </span>
                )}
              </a>
              <a
                href="/onboarding"
                className="flex items-center gap-1.5 rounded-lg bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition"
              >
                <Sparkles className="h-3.5 w-3.5 text-emerald-400" />
                <span>Manage Services & Connections</span>
              </a>
            </div>
          </div>

          {/* OFFICIAL COMPANY BANK DETAILS CARD WITH 1-CLICK COPY & PAYMENT NOTIFICATION */}
          <div className="rounded-2xl border-2 border-emerald-500/30 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 p-6 text-white shadow-xl space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-4">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-500 text-slate-950 font-bold shadow-lg shadow-emerald-500/20">
                  <Building2 className="h-6 w-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-extrabold text-white">
                      Official Company Bank Details (Direct Bank Transfer)
                    </h2>
                    <span className="rounded-full bg-emerald-500/20 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300 border border-emerald-500/30">
                      Verified Account
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">
                    Transfer your monthly service investment directly to our corporate bank account for instant admin approval.
                  </p>
                </div>
              </div>

              <div>
                {isApproved ? (
                  <div className="flex items-center gap-1.5 rounded-lg bg-emerald-500/20 px-3 py-1.5 text-xs font-bold text-emerald-300 border border-emerald-500/30">
                    <CheckCircle2 className="h-4 w-4" />
                    <span>Payment Approved & Verified</span>
                  </div>
                ) : isNotified ? (
                  <div className="flex items-center gap-1.5 rounded-lg bg-blue-500/20 px-3 py-1.5 text-xs font-bold text-blue-300 border border-blue-500/30">
                    <Clock className="h-4 w-4 animate-spin" />
                    <span>Transfer Submitted — Awaiting Verification</span>
                  </div>
                ) : (
                  <button
                    onClick={() => setIsNotifyingPayment(true)}
                    className="flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-extrabold text-slate-950 hover:bg-emerald-400 shadow-md shadow-emerald-500/20 transition"
                  >
                    <Send className="h-3.5 w-3.5" />
                    <span>I Have Made the Transfer</span>
                  </button>
                )}
              </div>
            </div>

            {/* Bank Details Grid with 1-Click Copy */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
              <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3.5 space-y-1">
                <p className="text-[11px] font-medium text-slate-400">Bank Name</p>
                <p className="text-sm font-bold text-white">{bankDetails.bank_name}</p>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3.5 space-y-1">
                <p className="text-[11px] font-medium text-slate-400">Account Title / Name</p>
                <p className="text-sm font-bold text-white">{bankDetails.account_name}</p>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3.5 flex items-center justify-between">
                <div>
                  <p className="text-[11px] font-medium text-slate-400">Account Number</p>
                  <p className="text-sm font-mono font-bold text-emerald-400 tracking-wider">
                    {bankDetails.account_number}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => copyToClipboard(bankDetails.account_number, "account")}
                  className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-[11px] font-semibold text-slate-200 hover:border-emerald-500 hover:text-white transition"
                  title="Copy Account Number"
                >
                  {copiedAccount ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                      <span className="text-emerald-400">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5 text-slate-400" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3.5 flex items-center justify-between">
                <div>
                  <p className="text-[11px] font-medium text-slate-400">IBAN</p>
                  <p className="text-xs font-mono font-bold text-emerald-400 tracking-wider">
                    {bankDetails.iban}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => copyToClipboard(bankDetails.iban, "iban")}
                  className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-[11px] font-semibold text-slate-200 hover:border-emerald-500 hover:text-white transition"
                  title="Copy IBAN"
                >
                  {copiedIban ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                      <span className="text-emerald-400">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5 text-slate-400" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* International Payoneer (USD) Receiving Rail */}
            {overview?.payment_rails?.payoneer && (
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white">International Payoneer (USD)</span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border ${
                        overview.payment_rails.payoneer.enabled
                          ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                          : "bg-amber-500/20 text-amber-300 border-amber-500/30"
                      }`}
                    >
                      {overview.payment_rails.payoneer.enabled ? "Active" : "Account Approval Pending"}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    {overview.payment_rails.payoneer.receiving_details}
                  </p>
                </div>
                {overview.payment_rails.payoneer.enabled && (
                  <span className="font-mono text-xs font-semibold text-emerald-400 shrink-0">
                    {overview.payment_rails.payoneer.account_email}
                  </span>
                )}
              </div>
            )}

            {/* Notification / Proof Submission Modal Form */}
            {isNotifyingPayment && (
              <form
                onSubmit={handleNotifyPayment}
                className="mt-4 rounded-xl border border-emerald-500/40 bg-slate-950 p-4 space-y-3 animate-in fade-in duration-150"
              >
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-extrabold text-white">
                    Notify Platform Admin of Completed Bank Transfer
                  </h4>
                  <button
                    type="button"
                    onClick={() => setIsNotifyingPayment(false)}
                    className="text-xs text-slate-400 hover:text-white"
                  >
                    Cancel
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-300">
                      Transaction Reference / Receipt ID *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g., FT26118909 or Bank Reference No."
                      value={txnRefInput}
                      onChange={(e) => setTxnRefInput(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-slate-300">
                      Additional Notes / Transfer Slip Note (Optional)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., Transferred from Meezan Bank"
                      value={txnNotesInput}
                      onChange={(e) => setTxnNotesInput(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsNotifyingPayment(false)}
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={notifyLoading || !txnRefInput.trim()}
                    className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-1.5 text-xs font-bold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
                  >
                    {notifyLoading ? "Submitting Notification..." : "Submit Payment Verification"}
                  </button>
                </div>
              </form>
            )}

            {notifySuccessMsg && (
              <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
                <span>{notifySuccessMsg}</span>
              </div>
            )}

            {notifyErrorMsg && (
              <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
                <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
                <span>{notifyErrorMsg}</span>
              </div>
            )}

            {/* Inactive Notice Banner when not approved */}
            {!isApproved && (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-200">
                <div className="flex items-start gap-3">
                  <Lock className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
                  <div>
                    <p className="font-bold text-amber-300">
                      AI Services Currently Locked — Awaiting Payment Approval
                    </p>
                    <p className="text-slate-300 mt-0.5">
                      Your managed AI services remain inactive until payment is received or you start your 7-Day Free Trial (100 credits included).
                    </p>
                  </div>
                </div>
                {!overview?.trial_info?.trial_used && (
                  <button
                    type="button"
                    disabled={trialStarting}
                    onClick={handleStartTrialFromDashboard}
                    className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3.5 py-2 text-xs font-extrabold text-slate-950 hover:bg-emerald-400 disabled:opacity-50 transition"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    <span>
                      {trialStarting ? "Activating..." : "Start 7-Day Free Trial (100 Credits)"}
                    </span>
                  </button>
                )}
              </div>
            )}
          </div>

          {/* MANAGED AI SERVICES & SUBSCRIPTION SYNCHRONIZATION */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-100 pb-4">
              <div className="flex items-center gap-2">
                <Layers className="h-5 w-5 text-emerald-600" />
                <div>
                  <h2 className="text-base font-bold text-slate-900">
                    Managed AI Services & Synchronized Packages
                  </h2>
                  <p className="text-xs text-slate-500">
                    Precisely mirroring your chosen services, package slots, and pricing from onboarding for {overview?.selected_industry}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span className="rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1 text-xs font-bold text-emerald-700">
                  Primary Package: {overview?.current_package || "None"}
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                    isApproved
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-amber-100 text-amber-800"
                  }`}
                >
                  {isApproved ? "Services Activated" : "Pending Payment Approval"}
                </span>
              </div>
            </div>

            {/* Synchronized Services List with exact slot numbers */}
            {overview?.purchased_services && overview.purchased_services.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
                {overview.purchased_services.map((srv, idx) => (
                  <div
                    key={srv.subscription_id || idx}
                    className="flex flex-col justify-between rounded-xl border border-slate-200 bg-slate-50/50 p-4 space-y-3 hover:border-emerald-300 transition"
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="rounded-md bg-slate-200/80 px-2 py-0.5 text-[10px] font-extrabold uppercase text-slate-700">
                          Slot {srv.slot_number || idx + 1}
                        </span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                            isApproved
                              ? "bg-emerald-100 text-emerald-800"
                              : "bg-amber-100 text-amber-800"
                          }`}
                        >
                          {srv.status || (isApproved ? "Active" : "Awaiting Approval")}
                        </span>
                      </div>

                      <h3 className="mt-2 text-sm font-bold text-slate-900">
                        {srv.service_name}
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5 capitalize">
                        Tier: <strong className="text-slate-700">{srv.plan_name}</strong>
                      </p>
                    </div>

                    <div className="pt-3 border-t border-slate-200/80 flex items-center justify-between text-xs">
                      <span className="font-mono text-base font-extrabold text-slate-900">
                        ${srv.price.toFixed(2)}
                        <span className="text-[11px] font-normal text-slate-500">
                          /{srv.billing_interval || "mo"}
                        </span>
                      </span>
                      <span className="text-[11px] text-slate-500">
                        {isApproved ? "Automated 24/7" : "Locked prior to payment"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg bg-slate-50 p-6 text-center text-xs text-slate-500 space-y-2">
                <p>No managed service packages selected yet.</p>
                <a
                  href="/onboarding"
                  className="inline-flex items-center gap-1 font-semibold text-emerald-600 hover:underline"
                >
                  <span>Select Industry Package in Onboarding →</span>
                </a>
              </div>
            )}

            <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
              <div className="flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-slate-400" />
                <span>
                  Total Synchronized Monthly Investment:{" "}
                  <strong className="text-slate-900 font-mono text-sm">
                    ${overview?.subscription_info?.monthly_investment?.toFixed(2) || "0.00"}
                  </strong>
                </span>
              </div>
              <a href="/billing" className="font-semibold text-emerald-600 hover:text-emerald-700">
                View Billing Invoices & Receipts →
              </a>
            </div>
          </div>

          {/* CONCISE OUTREACH TIER & MULTI-CHANNEL PERFORMANCE */}
          {showLeadModules && overview?.outreach_performance && (
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h2 className="text-base font-bold text-slate-900">
                    Outreach Tier Quota &amp; Multi-Channel Performance
                  </h2>
                  <p className="text-xs text-slate-500">
                    Active tier: <strong className="uppercase">{overview.outreach_performance.plan_name}</strong>{" "}
                    ({overview.outreach_performance.leads_used_this_month} / {overview.outreach_performance.monthly_lead_limit} leads used this month)
                  </p>
                </div>
                <a
                  href="/agents"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3.5 py-2 text-xs font-semibold text-white transition"
                >
                  <span>Review &amp; Approve Outreach ({overview.outreach_performance.pending_outreach_approvals})</span>
                </a>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                  <div className="text-slate-500">Remaining Lead Quota</div>
                  <div className="text-lg font-bold text-slate-900 mt-0.5">
                    {overview.outreach_performance.remaining_leads}
                  </div>
                </div>
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                  <div className="text-slate-500">Gmail Drafts Ready</div>
                  <div className="text-lg font-bold text-emerald-700 mt-0.5">
                    {overview.outreach_performance.gmail_drafts_ready}
                  </div>
                </div>
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                  <div className="text-slate-500">WhatsApp &amp; LinkedIn Ready</div>
                  <div className="text-lg font-bold text-indigo-700 mt-0.5">
                    {overview.outreach_performance.whatsapp_pitches_ready} / {overview.outreach_performance.linkedin_pitches_ready}
                  </div>
                </div>
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                  <div className="text-slate-500">Human-Approved Dispatches</div>
                  <div className="text-lg font-bold text-slate-900 mt-0.5">
                    {overview.outreach_performance.approved_sent_count}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* PRIMARY OPERATIONAL OUTCOME KPIS (Locked / Empty State prior to approval) */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">
                Operational Outcomes & Deliverables
              </h2>
              {!isApproved && (
                <span className="flex items-center gap-1 text-xs text-amber-700 font-semibold bg-amber-50 border border-amber-200 px-2.5 py-0.5 rounded-full">
                  <Lock className="h-3 w-3" />
                  <span>Locked until payment approved</span>
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                title="Leads Generated"
                value={loading ? "..." : isApproved ? m.leads_generated : 0}
                icon={Users}
                badge={{
                  text: isApproved ? `${m.qualified_leads} Qualified` : "Locked (Pending Payment)",
                  variant: isApproved ? "success" : "neutral",
                }}
                subtext="Verified prospects sourced for your business"
              />
              <StatCard
                title="Messages Sent"
                value={loading ? "..." : isApproved ? m.messages_sent : 0}
                icon={MessageSquare}
                badge={{
                  text: isApproved ? "WhatsApp & Email" : "Inactive",
                  variant: isApproved ? "neutral" : "neutral",
                }}
                subtext="Automated outreach & concierge replies"
              />
              <StatCard
                title="Meetings Booked"
                value={loading ? "..." : isApproved ? m.meetings_booked : 0}
                icon={CalendarCheck}
                badge={{
                  text: isApproved ? "Calendar Synced" : "Pending Approval",
                  variant: isApproved ? "success" : "neutral",
                }}
                subtext="Confirmed client appointments scheduled"
              />
              <StatCard
                title="Conversion Rate"
                value={loading ? "..." : isApproved ? `${m.conversion_rate}%` : "0.0%"}
                icon={TrendingUp}
                badge={{
                  text: isApproved
                    ? m.conversion_rate >= 20
                      ? "High Performing"
                      : "Active Funnel"
                    : "Funnel Locked",
                  variant: isApproved ? "success" : "neutral",
                }}
                subtext="Lead-to-booked-appointment conversion"
              />
            </div>
          </div>

          {/* CLIENT-CHOSEN CUSTOM MODULES SECTION */}
          {/* If not approved, show clean empty state message */}
          {!isApproved ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center space-y-3">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-amber-600 border border-amber-200">
                <Lock className="h-6 w-6" />
              </div>
              <h3 className="text-base font-bold text-slate-800">
                Active Operations and Reporting Feeds are Inactive
              </h3>
              <p className="text-xs text-slate-500 max-w-lg mx-auto">
                Once your payment is approved by the platform admin, this area will exclusively show the live operational modules for your selected services (e.g. WhatsApp Concierge, Lead Funnel, or Financial Ledger).
              </p>
            </div>
          ) : (
            <>
              {/* Dynamic Modules based on purchased services */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Lead Performance Module (if Lead Gen / Outreach service selected) */}
                {showLeadModules && (
                  <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-base font-bold text-slate-900">Lead Performance</h3>
                        <p className="text-xs text-slate-500">
                          Recent leads sourced, qualified, and contacted on your behalf
                        </p>
                      </div>
                      <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-700">
                        {overview?.lead_performance?.length || 0} Recent
                      </span>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-slate-200 text-slate-400 uppercase font-semibold">
                            <th className="py-2.5 px-2">Prospect</th>
                            <th className="py-2.5 px-2">Source</th>
                            <th className="py-2.5 px-2">Score</th>
                            <th className="py-2.5 px-2">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 text-slate-700">
                          {!overview?.lead_performance || overview.lead_performance.length === 0 ? (
                            <tr>
                              <td colSpan={4} className="py-6 text-center text-slate-400">
                                No leads recorded yet.
                              </td>
                            </tr>
                          ) : (
                            overview.lead_performance.map((lead) => (
                              <tr key={lead.id}>
                                <td className="py-2.5 px-2 font-semibold text-slate-900">{lead.name}</td>
                                <td className="py-2.5 px-2 uppercase text-[10px] font-mono text-slate-500">
                                  {lead.source}
                                </td>
                                <td className="py-2.5 px-2 font-mono font-bold text-emerald-700">
                                  {lead.qualification_score}%
                                </td>
                                <td className="py-2.5 px-2">
                                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase text-slate-700">
                                    {lead.status}
                                  </span>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Appointment Performance Module (if WhatsApp Concierge service selected) */}
                {showConciergeModules && (
                  <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-base font-bold text-slate-900">Appointment Performance</h3>
                        <p className="text-xs text-slate-500">
                          Confirmed meetings and consultations booked by your AI Concierge
                        </p>
                      </div>
                      <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
                        {m.meetings_booked} Booked
                      </span>
                    </div>

                    <div className="space-y-2.5">
                      {!overview?.appointment_performance ||
                      overview.appointment_performance.length === 0 ? (
                        <p className="text-xs text-slate-400 py-6 text-center">
                          Booked meetings will appear here automatically as leads convert.
                        </p>
                      ) : (
                        overview.appointment_performance.map((appt) => (
                          <div
                            key={appt.lead_id}
                            className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 p-3 text-xs"
                          >
                            <div>
                              <p className="font-bold text-slate-900">{appt.client_name}</p>
                              <p className="text-slate-500">{appt.meeting_title}</p>
                            </div>
                            <div className="text-right">
                              <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-bold uppercase text-emerald-800">
                                {appt.status}
                              </span>
                              <p className="text-[10px] text-slate-400 mt-1">
                                {new Date(appt.scheduled_at).toLocaleDateString()}
                              </p>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}

                {showReceptionistModule && (
                  <div className="rounded-xl border border-emerald-200 bg-gradient-to-br from-emerald-50/70 via-white to-white p-6 shadow-sm flex flex-col justify-between space-y-4">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600 text-white">
                            <PhoneCall className="h-4 w-4" />
                          </div>
                          <div>
                            <h3 className="text-base font-bold text-slate-900">
                              Office Receptionist (AI Voice Agent)
                            </h3>
                            <p className="text-xs text-slate-500">
                              24/7 Retell AI + Telnyx Voice + Cal.com Booking &amp; Call Logs
                            </p>
                          </div>
                        </div>
                        <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-bold uppercase text-emerald-800">
                          Active
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 leading-relaxed">
                        View your assigned Telnyx AI phone number, Call Forwarding dial codes, live
                        call transcripts, FAQs, and booked appointments in the Receptionist console.
                      </p>
                    </div>
                    <div>
                      <a
                        href="/receptionist"
                        className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition"
                      >
                        <PhoneCall className="h-3.5 w-3.5" />
                        <span>Open AI Voice Receptionist Console →</span>
                      </a>
                    </div>
                  </div>
                )}
              </div>

              {/* Bottom Section: Reports & Business Results + Recent Activity Feed */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Reports and Business Results */}
                {showFinancialModules && (
                  <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <div className="flex items-center gap-2">
                      <FileBarChart className="h-5 w-5 text-emerald-600" />
                      <div>
                        <h3 className="text-base font-bold text-slate-900">
                          Reports & Business Results
                        </h3>
                        <p className="text-xs text-slate-500">
                          Verified financial and operational outcomes ({overview?.reports?.period || "Current Period"})
                        </p>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 pt-2">
                      <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-100">
                        <p className="text-[11px] text-slate-500">Recorded Revenue</p>
                        <p className="text-lg font-extrabold text-slate-900">
                          ${m.income.toLocaleString()}
                        </p>
                      </div>
                      <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-100">
                        <p className="text-[11px] text-slate-500">Net Business Profit</p>
                        <p className="text-lg font-extrabold text-emerald-700">
                          ${m.net_profit.toLocaleString()}
                        </p>
                      </div>
                      <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-100">
                        <p className="text-[11px] text-slate-500">Qualified Pipeline</p>
                        <p className="text-lg font-extrabold text-slate-900">
                          {m.qualified_leads} Prospects
                        </p>
                      </div>
                      <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-100">
                        <p className="text-[11px] text-slate-500">Outstanding Receivables</p>
                        <p className="text-lg font-extrabold text-amber-700">
                          ${m.outstanding.toLocaleString()}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Recent Activity Feed */}
                <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                  <div className="flex items-center gap-2">
                    <Activity className="h-5 w-5 text-emerald-600" />
                    <div>
                      <h3 className="text-base font-bold text-slate-900">Recent Activity Feed</h3>
                      <p className="text-xs text-slate-500">
                        Automated agent operations and audit logs
                      </p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    {!overview?.recent_activity || overview.recent_activity.length === 0 ? (
                      <p className="text-xs text-slate-400 py-6 text-center">
                        No activity recorded in this billing cycle.
                      </p>
                    ) : (
                      overview.recent_activity.map((act) => (
                        <div
                          key={act.id}
                          className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 p-2.5 text-xs"
                        >
                          <div>
                            <p className="font-semibold text-slate-800">{act.action}</p>
                            <p className="text-[10px] text-slate-400 capitalize">
                              Resource: {act.resource_type}
                            </p>
                          </div>
                          <p className="text-[10px] text-slate-400">
                            {new Date(act.timestamp).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
