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

export default function BillingPage() {
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionItem[]>([]);
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
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
      const [servicesRes, subsRes, invoicesRes, bankRes] = await Promise.all([
        apiRequest<ServiceItem[]>(`/api/v1/services?ensure_seeded=true${indParam}`),
        apiRequest<SubscriptionItem[]>("/api/v1/services/subscriptions"),
        apiRequest<InvoiceItem[]>("/api/v1/payments/invoices"),
        apiRequest<any>("/api/v1/payments/bank-details"),
      ]);
      if (bankRes?.data?.account_number) {
        setBankDetails(bankRes.data);
      }

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
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
        </main>
      </div>
    </div>
  );
}
