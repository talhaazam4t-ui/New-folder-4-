"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { Sidebar } from "@/components/shared/Sidebar";
import { StatCard } from "@/components/dashboard/StatCard";
import { apiRequest } from "@/lib/api";
import { getActiveTenant, getAuthToken } from "@/lib/auth";
import {
  CreditCard,
  DollarSign,
  Receipt,
  CheckCircle,
  Clock,
  Layers,
  ArrowRight,
  ShieldCheck,
  Zap,
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
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<boolean>(false);

  const fetchBillingData = async () => {
    const tenant = getActiveTenant();
    const indParam = tenant?.industry ? `&industry=${encodeURIComponent(tenant.industry)}` : "";
    try {
      const [servicesRes, subsRes, invoicesRes] = await Promise.all([
        apiRequest<ServiceItem[]>(`/api/v1/services?ensure_seeded=true${indParam}`),
        apiRequest<SubscriptionItem[]>("/api/v1/services/subscriptions"),
        apiRequest<InvoiceItem[]>("/api/v1/payments/invoices"),
      ]);

      if (Array.isArray(servicesRes)) setServices(servicesRes);
      else if (servicesRes.data) setServices(servicesRes.data);

      if (Array.isArray(subsRes)) setSubscriptions(subsRes);
      else if (subsRes.data) setSubscriptions(subsRes.data);

      if (Array.isArray(invoicesRes)) setInvoices(invoicesRes);
      else if (invoicesRes.data) setInvoices(invoicesRes.data);
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
      setActionMessage(`Subscribed to ${serviceName}! Invoice generated.`);
      fetchBillingData();
    } else {
      setActionError(true);
      setActionMessage(res.error?.message || "Failed to subscribe.");
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

        <main className="flex-1 p-6 sm:p-8 space-y-8 max-w-7xl mx-auto w-full">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-6">
            <div>
              <div className="flex items-center gap-2">
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

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {services.map((srv) => {
                const isSubscribed = subscriptions.some(
                  (s) => s.service_id === srv.id && s.status === "active"
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
                            Active
                          </span>
                        )}
                      </div>

                      <h3 className="text-base font-bold text-slate-900">{srv.name}</h3>
                      <p className="text-xs text-slate-600 leading-relaxed">{srv.description}</p>
                    </div>

                    <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between">
                      <div>
                        <span className="text-xl font-extrabold text-slate-900">
                          ${srv.configuration_schema?.packages?.[0]?.price ?? srv.configuration_schema?.base_price ?? 99}
                        </span>
                        <span className="text-xs text-slate-400"> / month</span>
                      </div>

                      {isSubscribed ? (
                        <button
                          disabled
                          className="rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 border border-emerald-200 cursor-default"
                        >
                          Subscribed
                        </button>
                      ) : (
                        <button
                          onClick={() =>
                            handleSubscribe(
                              srv.id,
                              srv.name,
                              srv.configuration_schema?.packages?.[0]?.price ??
                                srv.configuration_schema?.base_price ??
                                99,
                              srv.configuration_schema?.packages?.[0]?.plan_name ?? "starter"
                            )
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
