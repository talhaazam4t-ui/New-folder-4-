"use client";

import React, { useEffect, useState } from "react";
import { AdminNavbar } from "@/components/admin/AdminNavbar";
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
  Layers,
  Link2,
  Megaphone,
  CheckCheck,
  RefreshCw,
  ExternalLink,
  Lock,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Sparkles,
  MapPin,
  X,
  Radio,
  Sliders,
} from "lucide-react";

type AdminTab = "platform" | "agents" | "leads" | "integrations" | "monitoring";

const AVAILABLE_INDUSTRIES = [
  "Financing",
  "Clinics / Hospitals",
  "Real Estate / Property",
  "E-Commerce",
];

// Mapping of industry/package to tailored AI agent profiles
const INDUSTRY_AGENT_PROFILES: Record<string, string[]> = {
  "Financing": [
    "master_orchestrator",
    "finance_tracker_agent",
    "researcher_agent",
    "reviewer_agent",
    "campaign_strategist_agent",
  ],
  "Clinics / Hospitals": [
    "master_orchestrator",
    "whatsapp_concierge_agent",
    "researcher_agent",
    "reviewer_agent",
    "planner_agent",
  ],
  "Real Estate / Property": [
    "master_orchestrator",
    "whatsapp_concierge_agent",
    "finance_tracker_agent",
    "campaign_strategist_agent",
    "reviewer_agent",
  ],
  "E-Commerce": [
    "master_orchestrator",
    "whatsapp_concierge_agent",
    "campaign_strategist_agent",
    "executor_agent",
    "reviewer_agent",
  ],
};

export default function AdminDashboardPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>("platform");
  const [ops, setOps] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Global Client / Workspace Selection across tabs
  const [selectedTenantId, setSelectedTenantId] = useState<string>("");
  const [selectedTenantForLeadGen, setSelectedTenantForLeadGen] = useState<string>("");
  const [leadGenIndustry, setLeadGenIndustry] = useState<string>("Financing");
  const [leadGenLocation, setLeadGenLocation] = useState<string>("Dubai, UAE");

  // Integration Connect Modal
  const [integrationModalOpen, setIntegrationModalOpen] = useState(false);
  const [modalTenantId, setModalTenantId] = useState("");
  const [modalProvider, setModalProvider] = useState("");
  const [modalAccountIdentifier, setModalAccountIdentifier] = useState("");
  const [modalOAuthUrl, setModalOAuthUrl] = useState<string | null>(null);
  const [connectingIntegration, setConnectingIntegration] = useState(false);

  const fetchOperationsData = async () => {
    try {
      const res = await apiRequest("/api/v1/admin/operations");
      if (res.error?.code === "PERMISSION_DENIED") {
        window.location.href = "/dashboard";
        return;
      }
      if (res.data) {
        setOps(res.data);
        const tenants = res.data.tenants || [];
        if (tenants.length > 0) {
          // If no client selected or selected client no longer exists, default to first tenant
          const currentExists = tenants.some((t: any) => t.id === selectedTenantId);
          const activeId = currentExists ? selectedTenantId : tenants[0].id;
          if (!currentExists) {
            setSelectedTenantId(activeId);
            setSelectedTenantForLeadGen(activeId);
            const activeTenant = tenants.find((t: any) => t.id === activeId);
            if (activeTenant?.industry) {
              setLeadGenIndustry(activeTenant.industry);
            }
          }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Handle switching global client context
  const handleSelectClient = (tenantId: string) => {
    setSelectedTenantId(tenantId);
    setSelectedTenantForLeadGen(tenantId);
    const tenant = (ops?.tenants || []).find((t: any) => t.id === tenantId);
    if (tenant?.industry) {
      setLeadGenIndustry(tenant.industry);
    }
    setActionMessage(`Switched active management context to "${tenant?.name || tenantId}".`);
  };

  const handleUpdateTenantStatus = async (tenantId: string, newStatus: string) => {
    setActionMessage(`Updating tenant status to "${newStatus}"...`);
    const res = await apiRequest(`/api/v1/admin/tenants/${tenantId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: newStatus }),
    });
    if (res.success) {
      setActionMessage(
        newStatus === "active"
          ? "Account payment confirmed and workspace activated successfully."
          : `Tenant status set to "${newStatus}".`
      );
      fetchOperationsData();
    } else {
      setActionMessage(`Error: ${res.error?.message || "Failed to update status"}`);
    }
  };

  const handleAssignIndustry = async (tenantId: string, industry: string) => {
    setActionMessage(`Assigning industry "${industry}"...`);
    const res = await apiRequest(`/api/v1/admin/tenants/${tenantId}/assign`, {
      method: "PATCH",
      body: JSON.stringify({ industry }),
    });
    if (res.success) {
      setActionMessage(`Assigned industry "${industry}" to workspace.`);
      if (tenantId === selectedTenantId) {
        setLeadGenIndustry(industry);
      }
      fetchOperationsData();
    }
  };

  const handleToggleServiceActive = async (serviceId: string, active: boolean) => {
    const res = await apiRequest(`/api/v1/services/${serviceId}`, {
      method: "PATCH",
      body: JSON.stringify({ active: !active }),
    });
    if (res.id) {
      setActionMessage("Service availability updated.");
      fetchOperationsData();
    }
  };

  const handleToggleAgentActive = async (agentName: string, active: boolean) => {
    const res = await apiRequest(`/api/v1/admin/agents/${agentName}`, {
      method: "PATCH",
      body: JSON.stringify({ active: !active }),
    });
    if (res.success) {
      setActionMessage(`Agent "${agentName}" operational state updated.`);
      fetchOperationsData();
    }
  };

  const handleApprovePayment = async (tenantId: string) => {
    setActionMessage("Verifying bank transfer and activating client AI services...");
    const res = await apiRequest(`/api/v1/admin/tenants/${tenantId}/approve-payment`, {
      method: "POST",
      body: JSON.stringify({ notes: "Verified and approved by Platform Owner" }),
    });
    if (res.success) {
      setActionMessage("Bank transfer approved! Client AI services are now activated.");
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
    const targetId = selectedTenantForLeadGen || selectedTenantId;
    if (!targetId) return;

    const tenant = (ops?.tenants || []).find((t: any) => t.id === targetId);
    if (tenant?.status === "suspended") {
      setActionMessage("Error: Lead generation cannot execute on a suspended client workspace.");
      return;
    }

    setActionMessage(
      `Triggering live Google Maps lead generation in "${leadGenLocation}" for ${tenant?.name || "client"}...`
    );
    const res = await apiRequest(
      `/api/v1/admin/tenants/${targetId}/run-lead-gen`,
      {
        method: "POST",
        body: JSON.stringify({
          industry: leadGenIndustry,
          location: leadGenLocation,
          limit: 5,
        }),
      }
    );
    if (res.success) {
      setActionMessage(
        `Lead generation complete: ${res.data?.created_count || 0} verified leads generated in "${leadGenLocation}" (${res.data?.skipped_duplicates || 0} duplicates skipped).`
      );
      fetchOperationsData();
    } else {
      setActionMessage(`Lead generation failed: ${res.error?.message || "Error"}`);
    }
  };

  const handleOpenConnectIntegration = async (tenantId: string, provider: string) => {
    setModalTenantId(tenantId);
    setModalProvider(provider);
    setModalAccountIdentifier("");
    setModalOAuthUrl(null);
    setIntegrationModalOpen(true);
    setActionMessage(`Generating OAuth URL for ${provider.toUpperCase()}...`);

    try {
      const res = await apiRequest(
        `/api/v1/admin/tenants/${tenantId}/integrations/oauth-url?provider=${provider}`
      );
      if (res.data?.auth_url) {
        setModalOAuthUrl(res.data.auth_url);
        window.open(res.data.auth_url, "_blank", "width=600,height=700");
        setActionMessage(
          `Redirecting to ${provider.toUpperCase()} authentication. Complete sign-in or enter account identifier below to link.`
        );
      }
    } catch {
      // Continue to modal even if OAuth endpoint fails
    }
  };

  const handleConfirmConnectIntegration = async () => {
    if (!modalTenantId || !modalProvider) return;
    setConnectingIntegration(true);
    setActionMessage(`Linking and approving ${modalProvider.toUpperCase()} integration...`);

    try {
      const res = await apiRequest(
        `/api/v1/admin/tenants/${modalTenantId}/integrations/connect`,
        {
          method: "POST",
          body: JSON.stringify({
            provider: modalProvider,
            account_identifier: modalAccountIdentifier || `${modalProvider}_verified_account`,
            status: "connected",
          }),
        }
      );
      if (res.success) {
        setActionMessage(`Integration ${modalProvider.toUpperCase()} successfully linked and approved!`);
        setIntegrationModalOpen(false);
        fetchOperationsData();
      } else {
        setActionMessage(`Error: ${res.error?.message || "Failed to link integration"}`);
      }
    } finally {
      setConnectingIntegration(false);
    }
  };

  const handleIntegrationAction = async (
    integrationId: string,
    action: "revoke" | "reconnect" | "test" | "approve"
  ) => {
    if (integrationId.startsWith("unlinked_")) {
      const parts = integrationId.split("_");
      const tId = parts[1];
      const prov = parts[2];
      handleOpenConnectIntegration(tId, prov);
      return;
    }

    setActionMessage(`Executing integration action "${action}"...`);
    const res = await apiRequest(`/api/v1/admin/integrations/${integrationId}/action`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    if (res.success) {
      setActionMessage(`Integration action "${action}" completed successfully.`);
      fetchOperationsData();
    } else {
      setActionMessage(`Action failed: ${res.error?.message || "Error"}`);
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

  const tenants: any[] = ops?.tenants || [];
  const selectedTenant = tenants.find((t: any) => t.id === selectedTenantId) || tenants[0];

  // Dynamic filter for Tab 2 AI agents based on selected client's industry and subscribed packages
  const activeIndustry = selectedTenant?.industry || "Financing";
  const permittedAgentNames = INDUSTRY_AGENT_PROFILES[activeIndustry] || INDUSTRY_AGENT_PROFILES["Financing"];
  const clientAgents = (ops?.ai_agents?.agents || []).filter((ag: any) =>
    permittedAgentNames.includes(ag.name)
  );

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">
      <AdminNavbar />

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
                Complete operational control over client workspaces, industry assignments, bounded AI agents, managed lead generation, integrations, and audit logs.
              </p>
            </div>

            <div className="flex items-center gap-3">
              {/* Global Client Switcher in Header */}
              {tenants.length > 0 && (
                <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950 px-3 py-1.5 text-xs">
                  <Building2 className="h-4 w-4 text-emerald-400" />
                  <span className="text-slate-400 hidden md:inline">Client Context:</span>
                  <select
                    value={selectedTenantId}
                    onChange={(e) => handleSelectClient(e.target.value)}
                    className="bg-transparent font-semibold text-white focus:outline-none cursor-pointer"
                  >
                    {tenants.map((t: any) => (
                      <option key={t.id} value={t.id} className="bg-slate-900 text-white">
                        {t.name} ({t.industry})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <button
                onClick={fetchOperationsData}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 transition"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                <span>Refresh Telemetry</span>
              </button>
            </div>
          </div>

          {actionMessage && (
            <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs text-emerald-300 flex items-center justify-between">
              <span>{actionMessage}</span>
              <button
                onClick={() => setActionMessage(null)}
                className="text-slate-400 hover:text-white text-xs ml-4"
              >
                ✕
              </button>
            </div>
          )}

          {/* Global KPI Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Registered Clients"
              value={loading ? "..." : stats.total_tenants}
              icon={Building2}
              badge={{ text: `${stats.active_tenants} Active`, variant: "success" }}
              subtext={`${stats.suspended_tenants} Suspended / Pending`}
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
                      ? "bg-emerald-600 text-white shadow-md shadow-emerald-900/30"
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
              {/* Bank Transfer Payment Approvals Queue */}
              <div className="rounded-xl border border-emerald-500/30 bg-slate-950 p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400">
                      <CircleDollarSign className="h-5 w-5" />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-white">
                        Bank Transfer Payment Approvals & Service Activation
                      </h2>
                      <p className="text-xs text-slate-400">
                        Verify incoming bank transfers (Faysal Bank) and 1-click activate client managed AI services.
                      </p>
                    </div>
                  </div>
                  <span className="rounded-full bg-emerald-500/20 px-3 py-1 text-xs font-bold text-emerald-300 border border-emerald-500/30">
                    {ops?.pending_payments?.length || 0} Pending Approvals
                  </span>
                </div>

                {!ops?.pending_payments || ops.pending_payments.length === 0 ? (
                  <p className="text-xs text-slate-500 py-3 text-center border border-dashed border-slate-800 rounded-lg">
                    No pending bank transfer notifications awaiting verification. All client payments are up to date.
                  </p>
                ) : (
                  <div className="divide-y divide-slate-800 border border-slate-800 rounded-lg overflow-hidden">
                    {ops.pending_payments.map((p: any) => (
                      <div
                        key={p.id}
                        className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3.5 bg-slate-900/40 text-xs"
                      >
                        <div>
                          <p className="font-bold text-white text-sm">{p.tenant_name}</p>
                          <p className="text-slate-400 text-[11px] font-mono mt-0.5">
                            Reference: <strong className="text-emerald-400">{p.provider_reference}</strong> •{" "}
                            Method: {p.payment_method}
                          </p>
                          {p.created_at && (
                            <p className="text-[10px] text-slate-500 mt-0.5">
                              Submitted: {new Date(p.created_at).toLocaleString()}
                            </p>
                          )}
                        </div>

                        <div className="flex items-center gap-4">
                          <span className="font-mono text-sm font-extrabold text-white">
                            ${p.amount.toFixed(2)} {p.currency}
                          </span>
                          <button
                            onClick={() => handleApprovePayment(p.tenant_id)}
                            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-500 shadow-md shadow-emerald-600/20 transition"
                          >
                            <CheckCheck className="h-3.5 w-3.5" />
                            <span>Verify & Activate Services</span>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Registered Clients Table */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div>
                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                      <Building2 className="h-4 w-4 text-emerald-400" />
                      Registered Clients & Tenant Workspaces
                    </h2>
                    <p className="text-xs text-slate-400">
                      Click any client to switch management context. Control onboarding approvals, payment activation, industry assignment, and subscription tiers.
                    </p>
                  </div>
                  <span className="text-xs font-mono text-slate-400">
                    {tenants.length} Registered Companies
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 uppercase font-semibold">
                        <th className="py-3 px-3">Client / Workspace</th>
                        <th className="py-3 px-3">Industry Assignment</th>
                        <th className="py-3 px-3">Subscription & Spend</th>
                        <th className="py-3 px-3">Integrations Status</th>
                        <th className="py-3 px-3">Account Status</th>
                        <th className="py-3 px-3 text-right">Owner Control</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-900 text-slate-300">
                      {tenants.map((t: any) => {
                        const isSelected = t.id === selectedTenantId;
                        const activeSubs = t.active_subscriptions || [];
                        const hasActiveSub = activeSubs.length > 0;
                        const subName = hasActiveSub
                          ? activeSubs[0].service_name
                          : t.selected_service_name || "Business Automation Suite";
                        const planTier = hasActiveSub
                          ? activeSubs[0].plan_name
                          : t.selected_package_tier || "growth";

                        return (
                          <tr
                            key={t.id}
                            className={`transition cursor-pointer ${
                              isSelected
                                ? "bg-emerald-950/20 border-l-2 border-emerald-500"
                                : "hover:bg-slate-900/50"
                            }`}
                            onClick={() => handleSelectClient(t.id)}
                          >
                            {/* 1. Client / Workspace Selector */}
                            <td className="py-3 px-3">
                              <div className="flex items-center gap-2">
                                <div>
                                  <div className="flex items-center gap-1.5">
                                    <p className="font-bold text-white hover:text-emerald-400 transition">
                                      {t.name}
                                    </p>
                                    {isSelected && (
                                      <span className="rounded bg-emerald-500/20 text-emerald-300 text-[9px] px-1.5 py-0.2 font-mono uppercase">
                                        Active Context
                                      </span>
                                    )}
                                  </div>
                                  <p className="text-[10px] font-mono text-slate-500">
                                    /{t.slug} • {t.members_count || 1} seat(s)
                                  </p>
                                </div>
                              </div>
                            </td>

                            {/* 2. Industry Assignment */}
                            <td className="py-3 px-3" onClick={(e) => e.stopPropagation()}>
                              <select
                                value={t.industry}
                                onChange={(e) => handleAssignIndustry(t.id, e.target.value)}
                                className="rounded bg-slate-900 border border-slate-700 px-2.5 py-1 text-xs text-white focus:border-emerald-500 focus:outline-none"
                              >
                                {AVAILABLE_INDUSTRIES.map((ind) => (
                                  <option key={ind} value={ind}>
                                    {ind}
                                  </option>
                                ))}
                              </select>
                            </td>

                            {/* 3. Subscription & Spend */}
                            <td className="py-3 px-3">
                              <div className="space-y-0.5">
                                <div className="flex items-center gap-1.5">
                                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-bold uppercase text-emerald-300 border border-slate-700">
                                    {planTier}
                                  </span>
                                  <span className="font-mono font-bold text-emerald-400">
                                    ${t.monthly_spend?.toFixed(2) || "0.00"}/mo
                                  </span>
                                </div>
                                <p className="text-[10px] text-slate-400 truncate max-w-[180px]">
                                  {subName}
                                </p>
                              </div>
                            </td>

                            {/* 4. Integrations Status */}
                            <td className="py-3 px-3">
                              {t.integrations_connected > 0 ? (
                                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                                  <CheckCircle2 className="h-3 w-3" />
                                  {t.integrations_connected} connected & approved
                                </span>
                              ) : t.integrations_pending > 0 ? (
                                <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                                  <Clock className="h-3 w-3" />
                                  {t.integrations_pending} pending approval
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 border border-slate-700 px-2 py-0.5 text-[10px] font-medium text-slate-400">
                                  Disconnected / Pending
                                </span>
                              )}
                              {t.integrations_failed > 0 && (
                                <span className="ml-1 text-[10px] text-red-400 font-semibold">
                                  ({t.integrations_failed} failed)
                                </span>
                              )}
                            </td>

                            {/* 5. Account Status */}
                            <td className="py-3 px-3">
                              {t.status === "active" ? (
                                <span className="rounded-full bg-emerald-500/20 text-emerald-400 px-2.5 py-0.5 text-[10px] font-bold uppercase inline-flex items-center gap-1">
                                  <CheckCircle className="h-3 w-3" /> Active
                                </span>
                              ) : t.status === "pending_approval" ? (
                                <span className="rounded-full bg-amber-500/20 text-amber-300 px-2.5 py-0.5 text-[10px] font-bold uppercase inline-flex items-center gap-1">
                                  <Clock className="h-3 w-3" /> Pending Approval / Unpaid
                                </span>
                              ) : (
                                <span className="rounded-full bg-red-500/20 text-red-400 px-2.5 py-0.5 text-[10px] font-bold uppercase inline-flex items-center gap-1">
                                  <Ban className="h-3 w-3" /> Suspended
                                </span>
                              )}
                            </td>

                            {/* 6. Owner Control Actions */}
                            <td className="py-3 px-3 text-right" onClick={(e) => e.stopPropagation()}>
                              {t.status === "pending_approval" ? (
                                <button
                                  onClick={() => handleUpdateTenantStatus(t.id, "active")}
                                  className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-500 transition shadow-sm"
                                  title="Confirm payment receipt and activate all automated services"
                                >
                                  <CheckCircle className="h-3 w-3" />
                                  <span>Confirm Payment & Activate</span>
                                </button>
                              ) : t.status === "active" ? (
                                <button
                                  onClick={() => handleUpdateTenantStatus(t.id, "suspended")}
                                  className="inline-flex items-center gap-1 rounded bg-red-500/10 text-red-400 border border-red-500/20 px-2.5 py-1 text-xs font-semibold hover:bg-red-500/20 transition"
                                >
                                  <Ban className="h-3 w-3" />
                                  <span>Suspend</span>
                                </button>
                              ) : (
                                <button
                                  onClick={() => handleUpdateTenantStatus(t.id, "active")}
                                  className="inline-flex items-center gap-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-1 text-xs font-semibold hover:bg-emerald-500/20 transition"
                                >
                                  <CheckCircle className="h-3 w-3" />
                                  <span>Reactivate</span>
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
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
                    Control managed service availability, supported industry verticals, required integration dependencies, and package tiers.
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
                          <div className="flex flex-wrap gap-2 pt-1 text-[11px] font-mono text-slate-300">
                            {packages.map((p: any) => (
                              <span
                                key={p.plan_name}
                                className="rounded bg-slate-950 px-2 py-1 border border-slate-800"
                              >
                                {p.display_name || p.plan_name}: ${p.price}/mo
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
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-4">
                  <div>
                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                      <Cpu className="h-4 w-4 text-emerald-400" />
                      Client-Specific AI Agents, Model Selection & Execution Permissions
                    </h2>
                    <p className="text-xs text-slate-400">
                      Dynamically displays the active AI agents and model configurations tailored specifically to the selected client workspace ({selectedTenant?.name || "None"}).
                    </p>
                  </div>

                  {/* Client Context Switcher inside Tab 2 */}
                  <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs">
                    <span className="text-slate-400">Client:</span>
                    <select
                      value={selectedTenantId}
                      onChange={(e) => handleSelectClient(e.target.value)}
                      className="bg-transparent font-bold text-emerald-400 focus:outline-none"
                    >
                      {tenants.map((t: any) => (
                        <option key={t.id} value={t.id} className="bg-slate-900 text-white">
                          {t.name} ({t.industry})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="rounded-lg bg-slate-900/50 border border-slate-800 p-3 text-xs flex flex-wrap items-center gap-4 text-slate-300">
                  <span>
                    Industry Package:{" "}
                    <strong className="text-white font-mono">{activeIndustry}</strong>
                  </span>
                  <span>
                    Subscribed Tier:{" "}
                    <strong className="text-emerald-400 font-mono uppercase">
                      {selectedTenant?.selected_package_tier || "Growth Autonomous Suite"}
                    </strong>
                  </span>
                  <span>
                    Daily Token Budget:{" "}
                    <strong className="text-white font-mono">150,000 tokens</strong>
                  </span>
                  <span>
                    Status:{" "}
                    <strong
                      className={
                        selectedTenant?.status === "active" ? "text-emerald-400" : "text-amber-400"
                      }
                    >
                      {selectedTenant?.status?.toUpperCase()}
                    </strong>
                  </span>
                </div>

                {/* Dynamic Agents Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {clientAgents.map((ag: any) => {
                    const isReasoning = ag.tier === "reasoning";
                    const modelName = isReasoning ? "claude-3-5-sonnet" : "gpt-4o-mini";

                    return (
                      <div
                        key={ag.id}
                        className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-2.5"
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <span className="font-mono text-sm font-bold text-white">{ag.name}</span>
                            <span className="ml-2 rounded bg-slate-800 px-2 py-0.5 text-[10px] uppercase text-emerald-400 border border-slate-700">
                              {ag.tier || "fast"} tier ({modelName})
                            </span>
                          </div>
                          <button
                            onClick={() => handleToggleAgentActive(ag.name, ag.active)}
                            className={`rounded px-2.5 py-1 text-[10px] font-bold uppercase transition ${
                              ag.active
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : "bg-red-500/20 text-red-300 border border-red-500/30"
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
                    );
                  })}
                </div>
              </div>

              {/* Pending Human Approvals Gate */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <div className="flex items-center gap-2">
                  <CheckCheck className="h-5 w-5 text-amber-400" />
                  <h2 className="text-base font-bold text-white">
                    Human-in-the-Loop Approval Gate ({ops?.approvals?.length || 0})
                  </h2>
                </div>
                <div className="space-y-2">
                  {(ops?.approvals || []).length === 0 ? (
                    <p className="text-xs text-slate-500 italic py-2">
                      No pending human approval requests across client workspaces.
                    </p>
                  ) : (
                    (ops?.approvals || []).map((ap: any) => (
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
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: LEAD GENERATION & OUTREACH */}
          {activeTab === "leads" && (
            <div className="space-y-6">
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <Megaphone className="h-4 w-4 text-emerald-400" />
                    Managed Lead Generation (Google Maps / Places)
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Select a client to auto-sync their assigned industry. Enter any city/region worldwide in the Admin-Only Target Location field to trigger real-time Google Maps lead harvesting.
                  </p>
                </div>

                <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs text-emerald-300 flex items-center gap-2">
                  <MapPin className="h-4 w-4 shrink-0" />
                  <span>
                    <strong>Admin-Only Location Control:</strong> Target location is controlled exclusively here by the Super Admin based on client onboarding intake. Client dashboards have this setting hidden to keep client UI simple.
                  </span>
                </div>

                <form
                  onSubmit={handleTriggerLeadGen}
                  className="grid grid-cols-1 md:grid-cols-4 gap-3 pt-2"
                >
                  {/* 1. Client Workspace Dropdown */}
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                      Target Client Workspace
                    </label>
                    <select
                      value={selectedTenantForLeadGen}
                      onChange={(e) => {
                        setSelectedTenantForLeadGen(e.target.value);
                        setSelectedTenantId(e.target.value);
                        const t = tenants.find((x: any) => x.id === e.target.value);
                        if (t?.industry) {
                          setLeadGenIndustry(t.industry);
                        }
                      }}
                      className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
                    >
                      {tenants.map((t: any) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* 2. Synced Industry Display/Selector */}
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                      Assigned Industry (Synced)
                    </label>
                    <select
                      value={leadGenIndustry}
                      onChange={(e) => setLeadGenIndustry(e.target.value)}
                      className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
                    >
                      {AVAILABLE_INDUSTRIES.map((ind) => (
                        <option key={ind} value={ind}>
                          {ind}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* 3. Global Target Location Input (Admin-Only) */}
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                      Target Location (Worldwide City / Region)
                    </label>
                    <input
                      type="text"
                      value={leadGenLocation}
                      onChange={(e) => setLeadGenLocation(e.target.value)}
                      placeholder="e.g. Dubai, Riyadh, London, Toronto"
                      className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                      required
                    />
                  </div>

                  {/* 4. Trigger Execution */}
                  <div className="flex items-end">
                    <button
                      type="submit"
                      className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition shadow-md shadow-emerald-900/30 flex items-center justify-center gap-1.5"
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      <span>Generate & Qualify Leads</span>
                    </button>
                  </div>
                </form>
              </div>

              {/* Lead Qualification & Outreach Table */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-base font-bold text-white">
                    Tenant-Wide Lead Qualification & Outreach Activity
                  </h2>
                  <span className="text-xs text-slate-400 font-mono">
                    {ops?.lead_gen_outreach?.leads?.length || 0} Total Leads Captured
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 uppercase font-semibold">
                        <th className="py-2.5 px-3">Lead Name</th>
                        <th className="py-2.5 px-3">Contact</th>
                        <th className="py-2.5 px-3">Location & Industry</th>
                        <th className="py-2.5 px-3">Source</th>
                        <th className="py-2.5 px-3">Score</th>
                        <th className="py-2.5 px-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-900 text-slate-300">
                      {(ops?.lead_gen_outreach?.leads || []).length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-6 text-center text-slate-500 italic">
                            No leads generated yet. Run Google Maps lead generation above.
                          </td>
                        </tr>
                      ) : (
                        (ops?.lead_gen_outreach?.leads || []).map((l: any) => {
                          const meta = l.metadata || {};
                          return (
                            <tr key={l.id} className="hover:bg-slate-900/50">
                              <td className="py-2.5 px-3 font-semibold text-white">{l.name}</td>
                              <td className="py-2.5 px-3 text-slate-400">
                                {l.email || l.phone || "N/A"}
                              </td>
                              <td className="py-2.5 px-3 text-slate-400">
                                <span>{meta.location || "Global"}</span>
                                <span className="text-[10px] text-slate-500 block">
                                  {meta.industry || "General"}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 font-mono uppercase text-[10px] text-emerald-400">
                                {l.source}
                              </td>
                              <td className="py-2.5 px-3 font-mono font-bold text-emerald-400">
                                {l.qualification_score}%
                              </td>
                              <td className="py-2.5 px-3">
                                <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] uppercase font-bold text-slate-300 border border-slate-700">
                                  {l.status}
                                </span>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: INTEGRATION MANAGEMENT */}
          {activeTab === "integrations" && (
            <div className="space-y-6">
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-4">
                  <div>
                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                      <Link2 className="h-4 w-4 text-emerald-400" />
                      Client Integration Connections & Credential Governance
                    </h2>
                    <p className="text-xs text-slate-400">
                      Link and approve genuine OAuth credentials for Gmail, Google Calendar, WhatsApp Business, Google Business, and Booking providers.
                    </p>
                  </div>

                  {/* Client Selector for Integrations */}
                  <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs">
                    <span className="text-slate-400">Client:</span>
                    <select
                      value={selectedTenantId}
                      onChange={(e) => handleSelectClient(e.target.value)}
                      className="bg-transparent font-bold text-emerald-400 focus:outline-none"
                    >
                      {tenants.map((t: any) => (
                        <option key={t.id} value={t.id} className="bg-slate-900 text-white">
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Enforce Integration Dependency Warning */}
                <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3 text-xs text-amber-300 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>
                    <strong>Enforced Outreach Dependency:</strong> Client outreach workflows strictly require verified and Super Admin-approved Gmail and WhatsApp integrations before executing. Unconnected workspaces will have automated messaging blocked.
                  </span>
                </div>

                {/* Filter integrations for selected tenant */}
                <div className="space-y-3">
                  {(ops?.integrations || [])
                    .filter(
                      (integ: any) =>
                        !selectedTenantId || integ.tenant_id === selectedTenantId
                    )
                    .map((integ: any) => {
                      const isConnected = integ.status === "connected";
                      const isPending = integ.status === "pending_approval";
                      const isUnlinked = integ.status === "disconnected" || integ.id.startsWith("unlinked_");

                      return (
                        <div
                          key={integ.id}
                          className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900 p-4 text-xs"
                        >
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-white uppercase text-sm">
                                {integ.provider.replace("_", " ")}
                              </span>
                              <span className="text-slate-400 font-mono text-[11px]">
                                ({integ.integration_type})
                              </span>
                              <span className="text-slate-500">— Client: {integ.tenant_name}</span>
                              <span
                                className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase inline-flex items-center gap-1 ${
                                  isConnected
                                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                                    : isPending
                                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                    : "bg-slate-800 text-slate-400 border border-slate-700"
                                }`}
                              >
                                {isConnected ? (
                                  <>
                                    <CheckCircle2 className="h-3 w-3" /> Connected & Approved
                                  </>
                                ) : isPending ? (
                                  <>
                                    <Clock className="h-3 w-3" /> Pending Admin Approval
                                  </>
                                ) : (
                                  <>
                                    <Ban className="h-3 w-3" /> Disconnected
                                  </>
                                )}
                              </span>
                            </div>
                            <p className="text-[11px] font-mono text-slate-500 mt-1">
                              Account Identifier: {integ.external_account_id || "Unlinked / Not configured"}
                            </p>
                          </div>

                          <div className="flex items-center gap-2">
                            {/* Connect / Authorize Flow */}
                            {isUnlinked && (
                              <button
                                onClick={() =>
                                  handleOpenConnectIntegration(integ.tenant_id, integ.provider)
                                }
                                className="rounded bg-emerald-600 px-3.5 py-1.5 font-semibold text-white hover:bg-emerald-500 transition shadow-sm flex items-center gap-1"
                              >
                                <ExternalLink className="h-3 w-3" />
                                <span>Connect & Authorize</span>
                              </button>
                            )}

                            {/* Admin Approval for pending connections */}
                            {isPending && (
                              <button
                                onClick={() => handleIntegrationAction(integ.id, "approve")}
                                className="rounded bg-emerald-600 px-3.5 py-1.5 font-semibold text-white hover:bg-emerald-500 transition"
                              >
                                <CheckCircle className="h-3 w-3" />
                                <span>Approve Integration</span>
                              </button>
                            )}

                            {/* Connected actions */}
                            {isConnected && (
                              <>
                                <button
                                  onClick={() => handleIntegrationAction(integ.id, "test")}
                                  className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-slate-200 hover:bg-slate-700 transition"
                                >
                                  Test Live
                                </button>
                                <button
                                  onClick={() =>
                                    handleOpenConnectIntegration(integ.tenant_id, integ.provider)
                                  }
                                  className="rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-emerald-300 hover:bg-emerald-500/20 transition"
                                >
                                  Reconnect
                                </button>
                                <button
                                  onClick={() => handleIntegrationAction(integ.id, "revoke")}
                                  className="rounded border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-red-300 hover:bg-red-500/20 transition"
                                >
                                  Revoke
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: MONITORING, AI COSTS & IMMUTABLE AUDIT LOGS */}
          {activeTab === "monitoring" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Telemetry */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <Activity className="h-4 w-4 text-emerald-400" />
                    AI Model Usage & Token Cost Telemetry
                  </h2>
                  <span className="font-mono text-xs text-emerald-400">
                    Total: ${(ops?.ai_agents?.total_ai_cost_usd || 0).toFixed(4)}
                  </span>
                </div>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {(ops?.monitoring?.usage_records || []).length === 0 ? (
                    <p className="text-xs text-slate-500 italic py-4">
                      No model consumption recorded yet.
                    </p>
                  ) : (
                    (ops?.monitoring?.usage_records || []).map((u: any) => (
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
                          ${u.estimated_cost?.toFixed(6) || "0.000000"}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Immutable Audit Logs */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <ShieldAlert className="h-4 w-4 text-emerald-400" />
                    Immutable Platform Audit Logs
                  </h2>
                  <span className="text-xs text-slate-400 font-mono">
                    {ops?.monitoring?.audit_logs?.length || 0} Events
                  </span>
                </div>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {(ops?.monitoring?.audit_logs || []).length === 0 ? (
                    <p className="text-xs text-slate-500 italic py-4">
                      No audit events recorded yet.
                    </p>
                  ) : (
                    (ops?.monitoring?.audit_logs || []).map((al: any) => {
                      const isActivation =
                        al.action.includes("activated") || al.action.includes("approved");
                      const isSuspension = al.action.includes("suspended") || al.action.includes("revoked");

                      return (
                        <div
                          key={al.id}
                          className="flex items-start justify-between rounded-lg border border-slate-800 bg-slate-900 p-3 text-xs"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <span
                                className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase font-mono ${
                                  isActivation
                                    ? "bg-emerald-500/20 text-emerald-300"
                                    : isSuspension
                                    ? "bg-red-500/20 text-red-300"
                                    : "bg-slate-800 text-slate-300"
                                }`}
                              >
                                {al.action}
                              </span>
                              <span className="text-[10px] text-slate-400">by {al.actor_type}</span>
                            </div>
                            <p className="text-[10px] text-slate-400 font-mono">
                              Resource: {al.resource_type}
                              {al.metadata ? ` • ${JSON.stringify(al.metadata)}` : ""}
                            </p>
                          </div>
                          <span className="text-[10px] text-slate-500 whitespace-nowrap ml-2">
                            {al.created_at ? new Date(al.created_at).toLocaleString() : ""}
                          </span>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Integration Connect / OAuth Confirmation Modal */}
      {integrationModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-950 p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Link2 className="h-5 w-5 text-emerald-400" />
                <h3 className="font-bold text-white text-base">
                  Connect {modalProvider.toUpperCase()} Integration
                </h3>
              </div>
              <button
                onClick={() => setIntegrationModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-xs text-slate-400">
              Authenticate with {modalProvider.toUpperCase()} using the official OAuth pop-up, or confirm the client account identifier below to link credentials.
            </p>

            {modalOAuthUrl && (
              <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs text-emerald-300 flex items-center justify-between">
                <span>OAuth authentication launched in new tab.</span>
                <a
                  href={modalOAuthUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-bold underline flex items-center gap-1 text-emerald-400"
                >
                  Re-open OAuth <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-[11px] font-semibold text-slate-300">
                Client Account Identifier (Email / Phone / Account ID)
              </label>
              <input
                type="text"
                value={modalAccountIdentifier}
                onChange={(e) => setModalAccountIdentifier(e.target.value)}
                placeholder={
                  modalProvider === "whatsapp"
                    ? "+971501234567"
                    : "client.business@gmail.com"
                }
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setIntegrationModalOpen(false)}
                className="rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmConnectIntegration}
                disabled={connectingIntegration}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition shadow-sm"
              >
                {connectingIntegration ? "Linking & Approving..." : "Confirm & Connect Integration"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
