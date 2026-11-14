"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { StatCard } from "@/components/dashboard/StatCard";
import { apiRequest } from "@/lib/api";
import { getAuthToken, isSuperAdminUser } from "@/lib/auth";
import {
  ShieldAlert,
  Building2,
  CircleDollarSign,
  Cpu,
  Activity,
  Ban,
  CheckCircle,
  Users,
  Layers,
  Link2,
  Megaphone,
  CheckCheck,
  RefreshCw,
} from "lucide-react";

type AdminTab = "platform" | "agents" | "leads" | "integrations" | "monitoring";

export default function AdminDashboardPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>("platform");
  const [ops, setOps] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [selectedTenantForLeadGen, setSelectedTenantForLeadGen] = useState<string>("");
  const [leadGenIndustry, setLeadGenIndustry] = useState<string>("Clinics / Hospitals");
  const [leadGenLocation, setLeadGenLocation] = useState<string>("Riyadh & Dubai");

  const fetchOperationsData = async () => {
    try {
      const res = await apiRequest("/api/v1/admin/operations");
      if (res.error?.code === "PERMISSION_DENIED") {
        window.location.href = "/dashboard";
        return;
      }
      if (res.data) {
        setOps(res.data);
        if (!selectedTenantForLeadGen && res.data.tenants?.length > 0) {
          setSelectedTenantForLeadGen(res.data.tenants[0].id);
        }
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
    if (!isSuperAdminUser()) {
      window.location.href = "/dashboard";
      return;
    }
    fetchOperationsData();
  }, []);

  const handleToggleTenantStatus = async (tenantId: string, currentStatus: string) => {
    const nextStatus = currentStatus === "active" ? "suspended" : "active";
    setActionMessage(`Updating tenant status to ${nextStatus}...`);
    const res = await apiRequest(`/api/v1/admin/tenants/${tenantId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: nextStatus }),
    });
    if (res.success) {
      setActionMessage(`Tenant status updated to ${nextStatus}.`);
      fetchOperationsData();
    }
  };

  const handleAssignIndustry = async (tenantId: string, industry: string) => {
    setActionMessage(`Assigning industry ${industry}...`);
    const res = await apiRequest(`/api/v1/admin/tenants/${tenantId}/assign`, {
      method: "PATCH",
      body: JSON.stringify({ industry }),
    });
    if (res.success) {
      setActionMessage(`Assigned industry "${industry}" to client.`);
      fetchOperationsData();
    }
  };

  const handleToggleServiceActive = async (serviceId: string, active: boolean) => {
    const res = await apiRequest(`/api/v1/services/${serviceId}`, {
      method: "PATCH",
      body: JSON.stringify({ active: !active }),
    });
    if (res.id) {
      setActionMessage(`Service availability updated.`);
      fetchOperationsData();
    }
  };

  const handleToggleAgentActive = async (agentName: string, active: boolean) => {
    const res = await apiRequest(`/api/v1/admin/agents/${agentName}`, {
      method: "PATCH",
      body: JSON.stringify({ active: !active }),
    });
    if (res.success) {
      setActionMessage(`Agent ${agentName} status updated.`);
      fetchOperationsData();
    }
  };

  const handleReviewApproval = async (approvalId: string, decision: "approved" | "rejected") => {
    const res = await apiRequest(`/api/v1/admin/approvals/${approvalId}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, reason: `Reviewed by Platform Owner (${decision})` }),
    });
    if (res.success) {
      setActionMessage(`Approval ${decision}.`);
      fetchOperationsData();
    }
  };

  const handleTriggerLeadGen = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTenantForLeadGen) return;
    setActionMessage("Executing backend Google Maps lead generation...");
    const res = await apiRequest(
      `/api/v1/admin/tenants/${selectedTenantForLeadGen}/run-lead-gen`,
      {
        method: "POST",
        body: JSON.stringify({
          industry: leadGenIndustry,
          location: leadGenLocation,
          limit: 3,
        }),
      }
    );
    if (res.success) {
      setActionMessage(
        `Lead generation complete: ${res.data?.created_count || 0} new leads created (${res.data?.skipped_duplicates || 0} duplicates skipped).`
      );
      fetchOperationsData();
    }
  };

  const handleIntegrationAction = async (
    integrationId: string,
    action: "revoke" | "reconnect" | "test"
  ) => {
    const res = await apiRequest(`/api/v1/admin/integrations/${integrationId}/action`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    if (res.success) {
      setActionMessage(`Integration action "${action}" completed.`);
      fetchOperationsData();
    }
  };

  const stats = ops?.stats || {
    total_tenants: 0,
    active_tenants: 0,
    suspended_tenants: 0,
    monthly_recurring_revenue: 0,
    total_collected_payments: 0,
    total_agent_executions: 0,
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col">
      <Navbar />

      <div className="flex flex-1">
        <AdminSidebar currentPath="/admin" />

        <main className="flex-1 p-6 sm:p-8 space-y-8 max-w-7xl mx-auto w-full">
          {/* Header Banner */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-6">
            <div>
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-6 w-6 text-emerald-400" />
                <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                  Owner / Super Admin Operations Console
                </h1>
              </div>
              <p className="mt-1 text-xs sm:text-sm text-slate-400">
                Complete operational control over clients, industry packages, AI agents, lead generation, integrations, and monitoring.
              </p>
            </div>

            <button
              onClick={fetchOperationsData}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 transition"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Refresh Telemetry</span>
            </button>
          </div>

          {actionMessage && (
            <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs text-emerald-300">
              {actionMessage}
            </div>
          )}

          {/* Global KPI Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Registered Clients"
              value={loading ? "..." : stats.total_tenants}
              icon={Building2}
              badge={{ text: `${stats.active_tenants} Active`, variant: "success" }}
              subtext={`${stats.suspended_tenants} Suspended`}
            />
            <StatCard
              title="Monthly Recurring (MRR)"
              value={loading ? "..." : `$${stats.monthly_recurring_revenue.toLocaleString()}`}
              icon={CircleDollarSign}
              badge={{ text: "Active Subscriptions", variant: "success" }}
              subtext={`Collected: $${stats.total_collected_payments.toLocaleString()}`}
            />
            <StatCard
              title="AI Agent Executions"
              value={loading ? "..." : stats.total_agent_executions}
              icon={Cpu}
              badge={{
                text: `${ops?.ai_agents?.total_tokens_consumed || 0} Tokens`,
                variant: "neutral",
              }}
              subtext={`AI Cost: $${(ops?.ai_agents?.total_ai_cost_usd || 0).toFixed(4)}`}
            />
            <StatCard
              title="Leads & Meetings"
              value={loading ? "..." : ops?.lead_gen_outreach?.summary?.total_leads || 0}
              icon={Activity}
              badge={{
                text: `${ops?.lead_gen_outreach?.summary?.meetings_booked || 0} Meetings`,
                variant: "success",
              }}
              subtext={`Conversion: ${ops?.lead_gen_outreach?.summary?.conversion_rate || 0}%`}
            />
          </div>

          {/* 5 Operational Control Tabs */}
          <div className="flex flex-wrap gap-2 border-b border-slate-800 pb-3">
            {[
              { id: "platform", label: "1. Platform & Clients", icon: Layers },
              { id: "agents", label: "2. AI Agent Management", icon: Cpu },
              { id: "leads", label: "3. Lead Gen & Outreach", icon: Megaphone },
              { id: "integrations", label: "4. Integration Management", icon: Link2 },
              { id: "monitoring", label: "5. Monitoring & Audit Logs", icon: Activity },
            ].map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id as AdminTab)}
                  className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition ${
                    activeTab === t.id
                      ? "bg-emerald-600 text-white"
                      : "bg-slate-950 text-slate-400 hover:text-white border border-slate-800"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{t.label}</span>
                </button>
              );
            })}
          </div>

          {/* TAB 1: PLATFORM & CLIENTS MANAGEMENT */}
          {activeTab === "platform" && (
            <div className="space-y-6">
              {/* Registered Clients Table */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-base font-bold text-white">
                      Registered Clients & Tenant Workspaces
                    </h2>
                    <p className="text-xs text-slate-400">
                      Manage client activation/suspension, industry assignments, and active service subscriptions.
                    </p>
                  </div>
                  <span className="text-xs font-mono text-slate-400">
                    {ops?.tenants?.length || 0} Clients
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 uppercase font-semibold">
                        <th className="py-3 px-3">Client / Workspace</th>
                        <th className="py-3 px-3">Industry Assignment</th>
                        <th className="py-3 px-3">Subscriptions & Spend</th>
                        <th className="py-3 px-3">Integrations</th>
                        <th className="py-3 px-3">Status</th>
                        <th className="py-3 px-3 text-right">Owner Control</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-900 text-slate-300">
                      {(ops?.tenants || []).map((t: any) => (
                        <tr key={t.id} className="hover:bg-slate-900/50">
                          <td className="py-3 px-3">
                            <p className="font-bold text-white">{t.name}</p>
                            <p className="text-[10px] font-mono text-slate-500">/{t.slug}</p>
                          </td>
                          <td className="py-3 px-3">
                            <select
                              value={t.industry}
                              onChange={(e) => handleAssignIndustry(t.id, e.target.value)}
                              className="rounded bg-slate-900 border border-slate-700 px-2 py-1 text-xs text-white"
                            >
                              {[
                                "Financing",
                                "Clinics / Hospitals",
                                "Real Estate / Property",
                                "E-Commerce",
                              ].map((ind) => (
                                <option key={ind} value={ind}>
                                  {ind}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="py-3 px-3">
                            <span className="font-mono font-bold text-emerald-400">
                              ${t.monthly_spend?.toFixed(2) || "0.00"}/mo
                            </span>
                            <span className="ml-2 text-slate-500">
                              ({t.active_subscriptions?.length || 0} active)
                            </span>
                          </td>
                          <td className="py-3 px-3">
                            <span className="text-emerald-400 font-semibold">
                              {t.integrations_connected} connected
                            </span>
                            {t.integrations_failed > 0 && (
                              <span className="ml-2 text-red-400 font-semibold">
                                ({t.integrations_failed} failed)
                              </span>
                            )}
                          </td>
                          <td className="py-3 px-3">
                            <span
                              className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                                t.status === "active"
                                  ? "bg-emerald-500/20 text-emerald-400"
                                  : "bg-red-500/20 text-red-400"
                              }`}
                            >
                              {t.status}
                            </span>
                          </td>
                          <td className="py-3 px-3 text-right">
                            <button
                              onClick={() => handleToggleTenantStatus(t.id, t.status)}
                              className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-semibold ${
                                t.status === "active"
                                  ? "bg-red-500/10 text-red-400 border border-red-500/20"
                                  : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              }`}
                            >
                              {t.status === "active" ? (
                                <>
                                  <Ban className="h-3 w-3" /> Suspend
                                </>
                              ) : (
                                <>
                                  <CheckCircle className="h-3 w-3" /> Activate
                                </>
                              )}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Dynamic Industry Service Catalog & Pricing Control */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <div>
                  <h2 className="text-base font-bold text-white">
                    Industry Service Catalog, Packages & Pricing Control
                  </h2>
                  <p className="text-xs text-slate-400">
                    Control service availability, supported industries, required integrations, and package pricing tiers.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {(ops?.services || []).map((srv: any) => {
                    const schema = srv.configuration_schema || {};
                    const packages = schema.packages || [];
                    return (
                      <div
                        key={srv.id}
                        className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-2.5"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-bold text-white">{srv.name}</span>
                          <button
                            onClick={() => handleToggleServiceActive(srv.id, srv.active)}
                            className={`rounded px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                              srv.active
                                ? "bg-emerald-500/20 text-emerald-300"
                                : "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {srv.active ? "Active (Click to Disable)" : "Disabled (Click to Enable)"}
                          </button>
                        </div>
                        <p className="text-xs text-slate-400">{srv.description}</p>
                        <div className="flex flex-wrap gap-1.5 text-[10px]">
                          {(schema.industries || []).map((ind: string) => (
                            <span
                              key={ind}
                              className="rounded bg-slate-800 px-2 py-0.5 text-emerald-300"
                            >
                              {ind}
                            </span>
                          ))}
                        </div>
                        {packages.length > 0 && (
                          <div className="flex gap-2 pt-1 text-[11px] font-mono text-slate-300">
                            {packages.map((p: any) => (
                              <span
                                key={p.plan_name}
                                className="rounded bg-slate-950 px-2 py-1 border border-slate-800"
                              >
                                {p.plan_name}: ${p.price}/mo
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: AI AGENT MANAGEMENT & PENDING APPROVALS */}
          {activeTab === "agents" && (
            <div className="space-y-6">
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <h2 className="text-base font-bold text-white">
                  Managed AI Agents, Model Selection & Execution Permissions
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {(ops?.ai_agents?.agents || []).map((ag: any) => (
                    <div
                      key={ag.id}
                      className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="font-mono text-sm font-bold text-white">{ag.name}</span>
                          <span className="ml-2 rounded bg-slate-800 px-2 py-0.5 text-[10px] uppercase text-emerald-400">
                            {ag.tier} tier
                          </span>
                        </div>
                        <button
                          onClick={() => handleToggleAgentActive(ag.name, ag.active)}
                          className={`rounded px-2.5 py-1 text-[10px] font-bold uppercase ${
                            ag.active
                              ? "bg-emerald-500/20 text-emerald-300"
                              : "bg-red-500/20 text-red-300"
                          }`}
                        >
                          {ag.active ? "Operational" : "Paused"}
                        </button>
                      </div>
                      <p className="text-xs text-slate-400">{ag.description}</p>
                      <div className="flex flex-wrap gap-1 pt-1">
                        {(ag.allowed_tools || []).map((tool: string) => (
                          <span
                            key={tool}
                            className="rounded bg-slate-950 px-2 py-0.5 text-[10px] font-mono text-slate-400 border border-slate-800"
                          >
                            {tool}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Pending Human Approvals */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <div className="flex items-center gap-2">
                  <CheckCheck className="h-5 w-5 text-amber-400" />
                  <h2 className="text-base font-bold text-white">
                    Human-in-the-Loop Approval Gate ({ops?.approvals?.length || 0})
                  </h2>
                </div>
                <div className="space-y-2">
                  {(ops?.approvals || []).map((ap: any) => (
                    <div
                      key={ap.id}
                      className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4 text-xs"
                    >
                      <div>
                        <span className="font-bold text-white uppercase">{ap.action_type}</span>
                        <span className="ml-2 text-slate-400">by {ap.requested_by}</span>
                        <p className="text-[11px] font-mono text-slate-400 mt-1">
                          {JSON.stringify(ap.proposed_action)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {ap.status === "pending" ? (
                          <>
                            <button
                              onClick={() => handleReviewApproval(ap.id, "approved")}
                              className="rounded bg-emerald-600 px-3 py-1.5 font-semibold text-white hover:bg-emerald-500"
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => handleReviewApproval(ap.id, "rejected")}
                              className="rounded bg-red-600 px-3 py-1.5 font-semibold text-white hover:bg-red-500"
                            >
                              Reject
                            </button>
                          </>
                        ) : (
                          <span className="rounded bg-slate-800 px-2.5 py-1 uppercase font-bold text-slate-300">
                            {ap.status}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: LEAD GENERATION & OUTREACH */}
          {activeTab === "leads" && (
            <div className="space-y-6">
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <h2 className="text-base font-bold text-white">
                  Execute Managed Lead Generation (Google Maps / Places)
                </h2>
                <form
                  onSubmit={handleTriggerLeadGen}
                  className="grid grid-cols-1 md:grid-cols-4 gap-3"
                >
                  <select
                    value={selectedTenantForLeadGen}
                    onChange={(e) => setSelectedTenantForLeadGen(e.target.value)}
                    className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-xs text-white"
                  >
                    {(ops?.tenants || []).map((t: any) => (
                      <option key={t.id} value={t.id}>
                        Client: {t.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={leadGenIndustry}
                    onChange={(e) => setLeadGenIndustry(e.target.value)}
                    className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-xs text-white"
                  >
                    {[
                      "Financing",
                      "Clinics / Hospitals",
                      "Real Estate / Property",
                      "E-Commerce",
                    ].map((ind) => (
                      <option key={ind} value={ind}>
                        {ind}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    value={leadGenLocation}
                    onChange={(e) => setLeadGenLocation(e.target.value)}
                    placeholder="Target Location"
                    className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-xs text-white"
                  />
                  <button
                    type="submit"
                    className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500"
                  >
                    Generate & Qualify Leads
                  </button>
                </form>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <h2 className="text-base font-bold text-white">
                  Platform-Wide Lead Qualification & Outreach Activity
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 uppercase">
                        <th className="py-2.5 px-3">Lead Name</th>
                        <th className="py-2.5 px-3">Contact</th>
                        <th className="py-2.5 px-3">Source</th>
                        <th className="py-2.5 px-3">Score</th>
                        <th className="py-2.5 px-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-900 text-slate-300">
                      {(ops?.lead_gen_outreach?.leads || []).map((l: any) => (
                        <tr key={l.id}>
                          <td className="py-2.5 px-3 font-semibold text-white">{l.name}</td>
                          <td className="py-2.5 px-3 text-slate-400">
                            {l.email || l.phone || "N/A"}
                          </td>
                          <td className="py-2.5 px-3 font-mono uppercase text-[10px]">
                            {l.source}
                          </td>
                          <td className="py-2.5 px-3 font-mono font-bold text-emerald-400">
                            {l.qualification_score}%
                          </td>
                          <td className="py-2.5 px-3 uppercase text-[10px] font-bold">
                            {l.status}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: INTEGRATION MANAGEMENT */}
          {activeTab === "integrations" && (
            <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
              <div>
                <h2 className="text-base font-bold text-white">
                  Client Integration Connections & Credential Governance
                </h2>
                <p className="text-xs text-slate-400">
                  Monitor WhatsApp, Google Business/Maps, Gmail, Google Calendar, and booking connections. Raw secrets are strictly masked.
                </p>
              </div>

              <div className="space-y-3">
                {(ops?.integrations || []).map((integ: any) => (
                  <div
                    key={integ.id}
                    className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900 p-4 text-xs"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white uppercase">{integ.provider}</span>
                        <span className="text-slate-400">— Client: {integ.tenant_name}</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                            integ.status === "connected"
                              ? "bg-emerald-500/20 text-emerald-400"
                              : "bg-red-500/20 text-red-400"
                          }`}
                        >
                          {integ.status}
                        </span>
                      </div>
                      <p className="text-[11px] font-mono text-slate-500 mt-1">
                        Account ID: {integ.external_account_id || "N/A"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleIntegrationAction(integ.id, "test")}
                        className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-slate-200 hover:bg-slate-700"
                      >
                        Test
                      </button>
                      <button
                        onClick={() => handleIntegrationAction(integ.id, "reconnect")}
                        className="rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-emerald-300 hover:bg-emerald-500/20"
                      >
                        Reconnect
                      </button>
                      <button
                        onClick={() => handleIntegrationAction(integ.id, "revoke")}
                        className="rounded border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-red-300 hover:bg-red-500/20"
                      >
                        Revoke
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 5: MONITORING, AI COSTS & AUDIT LOGS */}
          {activeTab === "monitoring" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <h2 className="text-base font-bold text-white">
                  AI Model Usage & Token Cost Telemetry
                </h2>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {(ops?.monitoring?.usage_records || []).map((u: any) => (
                    <div
                      key={u.id}
                      className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 p-3 text-xs"
                    >
                      <div>
                        <p className="font-mono font-bold text-white">{u.model}</p>
                        <p className="text-[10px] text-slate-400">
                          In: {u.input_tokens} • Out: {u.output_tokens} tokens
                        </p>
                      </div>
                      <span className="font-mono text-emerald-400">
                        ${u.estimated_cost.toFixed(6)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <h2 className="text-base font-bold text-white">Immutable Platform Audit Logs</h2>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {(ops?.monitoring?.audit_logs || []).map((al: any) => (
                    <div
                      key={al.id}
                      className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 p-3 text-xs"
                    >
                      <div>
                        <p className="font-semibold text-white">{al.action}</p>
                        <p className="text-[10px] text-slate-400">
                          Actor: {al.actor_type} • Resource: {al.resource_type}
                        </p>
                      </div>
                      <span className="text-[10px] text-slate-500">
                        {al.created_at ? new Date(al.created_at).toLocaleTimeString() : ""}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
