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
  Link2,
  FileBarChart,
  CreditCard,
  Sparkles,
} from "lucide-react";

interface OverviewPayload {
  tenant_id: string;
  tenant_name: string;
  role: string;
  selected_industry: string;
  service_status: string;
  automation_active: boolean;
  current_package: string;
  purchased_services: Array<{
    subscription_id: string;
    service_id: string;
    service_name: string;
    plan_name: string;
    price: number;
    billing_interval: string;
    status: string;
  }>;
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

  const loadClientPerformance = async () => {
    const tenant = getActiveTenant();
    if (!tenant?.id) {
      window.location.href = "/onboarding";
      return;
    }

    try {
      const res = await apiRequest<OverviewPayload>(`/api/v1/tenants/${tenant.id}/overview`);
      if (res.data) {
        setOverview(res.data);
      }
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

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />

      <div className="flex flex-1">
        <Sidebar currentPath="/dashboard" />

        <main className="flex-1 p-6 sm:p-8 space-y-8 max-w-7xl mx-auto w-full">
          {/* Header Banner: Managed Service Status & Selected Industry */}
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-200 pb-6">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                  Managed Service Performance
                </h1>
                <span
                  className={`rounded-full px-3 py-0.5 text-xs font-semibold ${
                    overview?.automation_active
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-amber-100 text-amber-800"
                  }`}
                >
                  {overview?.service_status || "Loading Status..."}
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
                href="/onboarding"
                className="flex items-center gap-1.5 rounded-lg bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition"
              >
                <Sparkles className="h-3.5 w-3.5 text-emerald-400" />
                <span>Manage Services & Connections</span>
              </a>
            </div>
          </div>

          {/* Primary Outcome KPIs: Leads Generated, Messages Sent, Meetings Booked, Conversion Rate */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Leads Generated"
              value={loading ? "..." : m.leads_generated}
              icon={Users}
              badge={{ text: `${m.qualified_leads} Qualified`, variant: "success" }}
              subtext="Verified prospects sourced for your business"
            />
            <StatCard
              title="Messages Sent"
              value={loading ? "..." : m.messages_sent}
              icon={MessageSquare}
              badge={{ text: "WhatsApp & Email", variant: "neutral" }}
              subtext="Automated outreach & concierge replies"
            />
            <StatCard
              title="Meetings Booked"
              value={loading ? "..." : m.meetings_booked}
              icon={CalendarCheck}
              badge={{ text: "Calendar Synced", variant: "success" }}
              subtext="Confirmed client appointments scheduled"
            />
            <StatCard
              title="Conversion Rate"
              value={loading ? "..." : `${m.conversion_rate}%`}
              icon={TrendingUp}
              badge={{
                text: m.conversion_rate >= 20 ? "High Performing" : "Active Funnel",
                variant: "success",
              }}
              subtext="Lead-to-booked-appointment conversion"
            />
          </div>

          {/* Middle Section: Current Package, Purchased Services & Integration Connection Status */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Purchased Services & Subscription Information */}
            <div className="lg:col-span-2 rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Layers className="h-5 w-5 text-emerald-600" />
                  <div>
                    <h2 className="text-base font-bold text-slate-900">
                      Purchased Services & Subscription Package
                    </h2>
                    <p className="text-xs text-slate-500">
                      Active managed AI services delivering outcomes for {overview?.selected_industry}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <span className="rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1 text-xs font-bold text-emerald-700">
                    Package: {overview?.current_package || "None"}
                  </span>
                </div>
              </div>

              {overview?.purchased_services && overview.purchased_services.length > 0 ? (
                <div className="divide-y divide-slate-100">
                  {overview.purchased_services.map((srv) => (
                    <div
                      key={srv.subscription_id}
                      className="py-3 flex items-center justify-between text-xs"
                    >
                      <div>
                        <p className="font-bold text-slate-900 text-sm">{srv.service_name}</p>
                        <p className="text-slate-500 capitalize">
                          Tier: {srv.plan_name} • Billing: {srv.billing_interval}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="font-mono font-bold text-slate-900 text-sm">
                          ${srv.price.toFixed(2)}/mo
                        </span>
                        <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-bold uppercase text-emerald-800">
                          {srv.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-lg bg-slate-50 p-4 text-xs text-slate-500 flex items-center justify-between">
                  <span>No managed service packages selected yet.</span>
                  <a
                    href="/onboarding"
                    className="font-semibold text-emerald-600 hover:underline"
                  >
                    Select Industry Package →
                  </a>
                </div>
              )}

              <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
                <div className="flex items-center gap-2">
                  <CreditCard className="h-4 w-4 text-slate-400" />
                  <span>
                    Monthly Subscription Total:{" "}
                    <strong className="text-slate-900">
                      ${overview?.subscription_info?.monthly_investment?.toFixed(2) || "0.00"}
                    </strong>
                  </span>
                </div>
                <a href="/billing" className="font-semibold text-emerald-600 hover:text-emerald-700">
                  View Invoices & Billing History →
                </a>
              </div>
            </div>

            {/* Integration Connection Status */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Link2 className="h-5 w-5 text-emerald-600" />
                  <div>
                    <h2 className="text-base font-bold text-slate-900">
                      Integration Status
                    </h2>
                    <p className="text-xs text-slate-500">Required service channels</p>
                  </div>
                </div>
                <a
                  href="/onboarding"
                  className="text-xs font-semibold text-emerald-600 hover:underline"
                >
                  Connect
                </a>
              </div>

              <div className="space-y-2.5">
                {overview?.integrations_status && overview.integrations_status.length > 0 ? (
                  overview.integrations_status.map((integ) => {
                    const connected = integ.status === "connected";
                    return (
                      <div
                        key={integ.provider}
                        className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 p-3 text-xs"
                      >
                        <div>
                          <p className="font-semibold text-slate-800">{integ.display_name}</p>
                          {integ.external_account_id && (
                            <p className="text-[10px] font-mono text-slate-500">
                              {integ.external_account_id}
                            </p>
                          )}
                        </div>
                        <span
                          className={`flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                            connected
                              ? "bg-emerald-100 text-emerald-800"
                              : "bg-amber-100 text-amber-800"
                          }`}
                        >
                          {connected ? (
                            <CheckCircle2 className="h-3 w-3" />
                          ) : (
                            <AlertCircle className="h-3 w-3" />
                          )}
                          {integ.status}
                        </span>
                      </div>
                    );
                  })
                ) : (
                  <p className="text-xs text-slate-400 py-4 text-center">
                    Select a service package to view required integrations.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Lead Performance & Appointment Performance */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Lead Performance */}
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

            {/* Appointment Performance */}
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
          </div>

          {/* Bottom Section: Reports & Business Results + Recent Activity Feed */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Reports and Business Results */}
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

            {/* Recent Activity Feed */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-emerald-600" />
                <div>
                  <h3 className="text-base font-bold text-slate-900">Recent Activity Feed</h3>
                  <p className="text-xs text-slate-500">
                    Live log of managed service deliveries for your business
                  </p>
                </div>
              </div>

              <div className="space-y-2.5">
                {!overview?.recent_activity || overview.recent_activity.length === 0 ? (
                  <p className="text-xs text-slate-400 py-6 text-center">
                    Recent service activity will appear here as automations run.
                  </p>
                ) : (
                  overview.recent_activity.slice(0, 6).map((act) => (
                    <div
                      key={act.id}
                      className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3.5 py-2.5 text-xs"
                    >
                      <div>
                        <span className="font-semibold text-slate-800">{act.action}</span>
                        <span className="ml-2 rounded bg-slate-200 px-1.5 py-0.5 text-[10px] uppercase text-slate-600">
                          {act.resource_type}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-400">
                        {new Date(act.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
