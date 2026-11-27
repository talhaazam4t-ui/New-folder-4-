"use client";

import React, { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import {
  ShieldAlert,
  Cpu,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  RefreshCw,
  Lock,
  Unlock,
  PlusCircle,
  FileCheck,
  Briefcase,
  Building2,
} from "lucide-react";

const CANONICAL_SERVICES = [
  { slug: "business-financial-tracking", label: "#1 Business Financial & Rent Tracking" },
  { slug: "ai-marketing-growth", label: "#2 AI Marketing & Growth Automation" },
  { slug: "whatsapp-business-concierge", label: "#3 WhatsApp Business Concierge" },
  { slug: "lead-crm-qualification", label: "#4 Lead CRM & Qualification" },
  { slug: "office-receptionist", label: "#5 AI Office Receptionist (Voice)" },
  { slug: "multi-agent-orchestration", label: "#6 Multi-Agent Orchestration" },
  { slug: "executive-analytics-compliance", label: "#7 Executive Analytics & Compliance" },
];

interface AdminEnterpriseGovernancePanelProps {
  selectedTenantId: string;
  selectedTenantName: string;
  tenants: any[];
  onSelectClient: (tenantId: string) => void;
  onStatusMessage: (msg: string, isError?: boolean) => void;
  onRefreshParent: () => void;
}

export function AdminEnterpriseGovernancePanel({
  selectedTenantId,
  selectedTenantName,
  tenants,
  onSelectClient,
  onStatusMessage,
  onRefreshParent,
}: AdminEnterpriseGovernancePanelProps) {
  const [loading, setLoading] = useState(false);
  const [uiConfig, setUiConfig] = useState<any>(null);
  const [tierQuota, setTierQuota] = useState<any>(null);
  const [circuitBreakers, setCircuitBreakers] = useState<any>(null);
  const [registry, setRegistry] = useState<any>(null);
  const [securityAudit, setSecurityAudit] = useState<any>(null);
  const [contractAudits, setContractAudits] = useState<any[]>([]);
  const [freelanceOrders, setFreelanceOrders] = useState<any[]>([]);
  const [togglingSlug, setTogglingSlug] = useState<string | null>(null);
  const [updatingTier, setUpdatingTier] = useState(false);

  // New DB-Driven Skill Form
  const [skillForm, setSkillForm] = useState({
    slug: "",
    name: "",
    service_slug: "multi-agent-orchestration",
    description: "",
    default_model_tier: "fast_free",
    token_budget: 1500,
    max_words: 130,
    requires_hitl: true,
  });
  const [savingSkill, setSavingSkill] = useState(false);

  // Contract Compliance Audit Form
  const [contractForm, setContractForm] = useState({
    contract_title: "Master Managed AI Services Agreement",
    counterparty: "Global Enterprise Client LLC",
    contract_text:
      "Provider agrees to deliver 99.9% uptime SLA with 30-day termination notice and capped liability.",
    promised_uptime_pct: 99.9,
    observed_uptime_pct: 99.95,
    milestone_status: "on_track",
  });
  const [runningContractAudit, setRunningContractAudit] = useState(false);

  // Automated Freelance Order Form
  const [freelanceForm, setFreelanceForm] = useState({
    client_name: "International Agency Partner",
    project_title: "Technical SEO & Conversion Audit",
    category: "seo_audit",
    budget_usd: 350,
    requirements: "Audit landing page speed, schema markup, CTA conversion funnel, and backlink profile.",
  });
  const [creatingFreelance, setCreatingFreelance] = useState(false);
  const [executingOrderId, setExecutingOrderId] = useState<string | null>(null);

  const tenantHeaders = selectedTenantId ? { "X-Tenant-ID": selectedTenantId } : undefined;

  const loadGovernanceData = async () => {
    if (!selectedTenantId) return;
    setLoading(true);
    try {
      const [uiRes, quotaRes, cbRes, regRes, secRes, conRes, freeRes] = await Promise.all([
        apiRequest("/api/v1/agents/ui-config", { headers: tenantHeaders }),
        apiRequest("/api/v1/analytics/tier-quota", { headers: tenantHeaders }),
        apiRequest("/api/v1/analytics/circuit-breakers", { headers: tenantHeaders }),
        apiRequest("/api/v1/agents/registry", { headers: tenantHeaders }),
        apiRequest("/api/v1/enterprise/security/audit", { headers: tenantHeaders }),
        apiRequest("/api/v1/enterprise/contracts/audits", { headers: tenantHeaders }),
        apiRequest("/api/v1/agents/freelance/orders", { headers: tenantHeaders }),
      ]);

      if (uiRes.data) setUiConfig(uiRes.data);
      if (quotaRes.data) setTierQuota(quotaRes.data);
      if (cbRes.data) setCircuitBreakers(cbRes.data);
      if (regRes.data) setRegistry(regRes.data);
      if (secRes.data) setSecurityAudit(secRes.data);
      if (Array.isArray(conRes.data)) setContractAudits(conRes.data);
      if (Array.isArray(freeRes.data)) setFreelanceOrders(freeRes.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGovernanceData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTenantId]);

  const handleToggleTenantService = async (serviceSlug: string, currentlyEnabled: boolean) => {
    if (!selectedTenantId) return;
    setTogglingSlug(serviceSlug);
    try {
      const res = await apiRequest(`/api/v1/agents/admin/tenants/${selectedTenantId}/services/toggle`, {
        method: "POST",
        headers: tenantHeaders,
        body: JSON.stringify({
          service_slug: serviceSlug,
          enabled: !currentlyEnabled,
        }),
      });
      if (res.success) {
        onStatusMessage(
          `Service "${serviceSlug}" ${!currentlyEnabled ? "ENABLED" : "DISABLED"} for ${selectedTenantName}.`
        );
        await loadGovernanceData();
        onRefreshParent();
      } else {
        onStatusMessage(`Error toggling service: ${res.error?.message || "Failed"}`, true);
      }
    } finally {
      setTogglingSlug(null);
    }
  };

  const handleUpgradeTenantTier = async (newTier: string) => {
    if (!selectedTenantId) return;
    setUpdatingTier(true);
    try {
      const res = await apiRequest("/api/v1/analytics/tier-quota/upgrade", {
        method: "POST",
        headers: tenantHeaders,
        body: JSON.stringify({ tier: newTier }),
      });
      if (res.success && res.data) {
        setTierQuota(res.data);
        onStatusMessage(
          `Updated ${selectedTenantName} to "${newTier.toUpperCase()}" tier and unlocked any 100% hard-locks!`
        );
        onRefreshParent();
      } else {
        onStatusMessage(`Error updating tier: ${res.error?.message || "Failed"}`, true);
      }
    } finally {
      setUpdatingTier(false);
    }
  };

  const handleRegisterSkill = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!skillForm.slug.trim() || !skillForm.name.trim()) return;
    setSavingSkill(true);
    try {
      const res = await apiRequest("/api/v1/agents/skills", {
        method: "POST",
        headers: tenantHeaders,
        body: JSON.stringify(skillForm),
      });
      if (res.success) {
        onStatusMessage(`DB-Driven Skill "${skillForm.slug}" registered into Central Orchestrator!`);
        setSkillForm({
          slug: "",
          name: "",
          service_slug: "multi-agent-orchestration",
          description: "",
          default_model_tier: "fast_free",
          token_budget: 1500,
          max_words: 130,
          requires_hitl: true,
        });
        await loadGovernanceData();
      } else {
        onStatusMessage(`Error registering skill: ${res.error?.message || "Failed"}`, true);
      }
    } finally {
      setSavingSkill(false);
    }
  };

  const handleRunContractAudit = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunningContractAudit(true);
    try {
      const res = await apiRequest("/api/v1/enterprise/contracts/audit", {
        method: "POST",
        headers: tenantHeaders,
        body: JSON.stringify({
          contract_title: contractForm.contract_title,
          counterparty: contractForm.counterparty,
          contract_text: contractForm.contract_text,
          sla_terms: {
            promised_uptime_pct: Number(contractForm.promised_uptime_pct),
            observed_uptime_pct: Number(contractForm.observed_uptime_pct),
          },
          milestone_status: contractForm.milestone_status,
        }),
      });
      if (res.success) {
        onStatusMessage(
          `Contract SLA Audit completed (Risk: ${res.data?.risk_level?.toUpperCase() || "LOW"}).`
        );
        await loadGovernanceData();
      } else {
        onStatusMessage(
          `Error running Contract Audit (ensure #7 Executive Analytics & Compliance is enabled): ${
            res.error?.message || "Failed"
          }`,
          true
        );
      }
    } finally {
      setRunningContractAudit(false);
    }
  };

  const handleCreateFreelanceOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreatingFreelance(true);
    try {
      const res = await apiRequest("/api/v1/agents/freelance/orders", {
        method: "POST",
        headers: tenantHeaders,
        body: JSON.stringify(freelanceForm),
      });
      if (res.success) {
        onStatusMessage(`Freelance order created and assigned to workforce agent!`);
        await loadGovernanceData();
      } else {
        onStatusMessage(`Error creating freelance order: ${res.error?.message || "Failed"}`, true);
      }
    } finally {
      setCreatingFreelance(false);
    }
  };

  const handleExecuteFreelanceOrder = async (orderId: string) => {
    setExecutingOrderId(orderId);
    try {
      const res = await apiRequest(`/api/v1/agents/freelance/orders/${orderId}/execute`, {
        method: "POST",
        headers: tenantHeaders,
      });
      if (res.success) {
        onStatusMessage("Workforce agent drafted deliverable, passed QC, and queued for HITL approval!");
        await loadGovernanceData();
      } else {
        onStatusMessage(`Error executing workforce agent: ${res.error?.message || "Failed"}`, true);
      }
    } finally {
      setExecutingOrderId(null);
    }
  };

  const handleApproveDeliverFreelanceOrder = async (orderId: string) => {
    setExecutingOrderId(orderId);
    try {
      const res = await apiRequest(`/api/v1/agents/freelance/orders/${orderId}/approve-deliver`, {
        method: "POST",
        headers: tenantHeaders,
      });
      if (res.success) {
        onStatusMessage("Freelance deliverable approved and auto-delivered to client!");
        await loadGovernanceData();
      } else {
        onStatusMessage(`Error delivering order: ${res.error?.message || "Failed"}`, true);
      }
    } finally {
      setExecutingOrderId(null);
    }
  };

  const provisionedSlugs: string[] = (uiConfig?.provisioned_services || []).map((s: any) =>
    typeof s === "string" ? s : s.slug
  );

  return (
    <div className="space-y-6">
      {/* Context Bar */}
      <div className="rounded-xl border border-emerald-500/30 bg-slate-950 p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-emerald-400" />
            Phases 1–5 Autonomous Governance, Per-Client Module Toggles &amp; Enterprise Controls
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Granularly toggle the 7 canonical services per tenant, manage 80%/100% tier quotas, inspect Free-First LLM circuit breakers, add DB-driven agent skills, and run Enterprise SLA/Security audits.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs">
            <Building2 className="h-3.5 w-3.5 text-emerald-400" />
            <span className="text-slate-400">Client:</span>
            <select
              value={selectedTenantId}
              onChange={(e) => onSelectClient(e.target.value)}
              className="bg-transparent font-bold text-white focus:outline-none"
            >
              {tenants.map((t: any) => (
                <option key={t.id} value={t.id} className="bg-slate-900 text-white">
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={loadGovernanceData}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin text-emerald-400" : ""}`} />
            <span>Sync</span>
          </button>
        </div>
      </div>

      {/* SECTION 1: Per-Tenant Granular Service Toggles & Phase 1 Tier Quota Metering */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Per-Tenant 7 Services Toggle Matrix */}
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Layers className="h-4 w-4 text-emerald-400" />
                Per-Client Module Toggles ({selectedTenantName})
              </h3>
              <p className="text-[11px] text-slate-400">
                Enable or disable specific services for this client. Disabled modules move to the client&apos;s Upgrade Marketplace.
              </p>
            </div>
            <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 text-[10px] font-bold text-emerald-300">
              {provisionedSlugs.length} / 7 Provisioned
            </span>
          </div>

          <div className="space-y-2">
            {CANONICAL_SERVICES.map((srv) => {
              const isEnabled = provisionedSlugs.includes(srv.slug);
              const isBusy = togglingSlug === srv.slug;
              return (
                <div
                  key={srv.slug}
                  className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 px-3.5 py-2.5 text-xs"
                >
                  <div>
                    <p className="font-semibold text-white">{srv.label}</p>
                    <p className="text-[10px] font-mono text-slate-400">{srv.slug}</p>
                  </div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => handleToggleTenantService(srv.slug, isEnabled)}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-[11px] font-bold uppercase transition ${
                      isEnabled
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/30"
                        : "bg-slate-800 text-slate-400 border border-slate-700 hover:text-white"
                    }`}
                  >
                    {isBusy
                      ? "Updating..."
                      : isEnabled
                      ? "✓ Enabled (Click to Disable)"
                      : "Disabled (Click to Enable)"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Phase 1 Tiered Usage & Token Metering + 80% Alert / 100% Hard-Lock Control */}
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Cpu className="h-4 w-4 text-emerald-400" />
                Tiered Usage &amp; Token Metering (80% Alert / 100% Hard-Lock)
              </h3>
              <p className="text-[11px] text-slate-400">
                Real-time monthly consumption for {selectedTenantName}. Switch tier to raise limits or unlock a 100% hard-locked workspace.
              </p>
            </div>
            {tierQuota && (
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                  tierQuota.hard_locked_100
                    ? "bg-red-500/20 text-red-300 border border-red-500/30"
                    : tierQuota.alert_80_triggered
                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                    : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                }`}
              >
                {tierQuota.hard_locked_100 ? (
                  <>
                    <Lock className="h-3 w-3" /> 100% Hard-Locked
                  </>
                ) : tierQuota.alert_80_triggered ? (
                  <>
                    <AlertTriangle className="h-3 w-3" /> 80% Alert Active
                  </>
                ) : (
                  <>
                    <Unlock className="h-3 w-3" /> Healthy ({tierQuota.tier?.toUpperCase()})
                  </>
                )}
              </span>
            )}
          </div>

          {tierQuota ? (
            <div className="space-y-4 text-xs">
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
                  <p className="text-[10px] uppercase text-slate-400">Tokens Metered</p>
                  <p className="text-sm font-bold text-white font-mono mt-1">
                    {Number(tierQuota.tokens_used || 0).toLocaleString()} /{" "}
                    {Number(tierQuota.tokens_limit || 0).toLocaleString()}
                  </p>
                  <p className="text-[10px] text-emerald-400 mt-0.5">{tierQuota.tokens_percent}% used</p>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
                  <p className="text-[10px] uppercase text-slate-400">API Calls</p>
                  <p className="text-sm font-bold text-white font-mono mt-1">
                    {Number(tierQuota.api_calls_used || 0).toLocaleString()} /{" "}
                    {Number(tierQuota.api_calls_limit || 0).toLocaleString()}
                  </p>
                  <p className="text-[10px] text-emerald-400 mt-0.5">{tierQuota.api_calls_percent}% used</p>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
                  <p className="text-[10px] uppercase text-slate-400">Voice Minutes</p>
                  <p className="text-sm font-bold text-white font-mono mt-1">
                    {tierQuota.voice_minutes_used} / {tierQuota.voice_minutes_limit}m
                  </p>
                  <p className="text-[10px] text-emerald-400 mt-0.5">
                    {tierQuota.voice_minutes_percent}% used
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800">
                <span className="text-[11px] text-slate-400">
                  Assign / Upgrade Subscription Tier:
                </span>
                <div className="flex items-center gap-2">
                  {(["starter", "growth", "enterprise"] as const).map((tierName) => (
                    <button
                      key={tierName}
                      type="button"
                      disabled={updatingTier}
                      onClick={() => handleUpgradeTenantTier(tierName)}
                      className={`rounded-lg px-3 py-1.5 text-xs font-bold uppercase transition ${
                        tierQuota.tier === tierName
                          ? "bg-emerald-600 text-white"
                          : "border border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
                      }`}
                    >
                      {tierName}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500">Loading tenant tier quota...</p>
          )}

          {/* Free-First Provider Circuit Breakers & Continuous Security Posture */}
          <div className="pt-3 border-t border-slate-800 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-300">
                Free-First AI &amp; Voice Circuit Breakers (Groq → Gemini → OpenRouter → DeepSeek)
              </span>
              {securityAudit && (
                <span className="rounded bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-mono text-emerald-300">
                  Security Score: {securityAudit.security_score ?? 100}/100 ({securityAudit.status})
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {circuitBreakers &&
                Object.entries(circuitBreakers).map(([prov, info]: [string, any]) => (
                  <span
                    key={prov}
                    className={`rounded-lg border px-2.5 py-1 text-[10px] font-mono ${
                      info?.state === "OPEN"
                        ? "border-red-500/40 bg-red-950/50 text-red-300"
                        : "border-slate-800 bg-slate-900 text-emerald-300"
                    }`}
                  >
                    {prov}: {info?.state || "CLOSED"}
                  </span>
                ))}
            </div>
          </div>
        </div>
      </div>

      {/* SECTION 2: Phase 2 DB-Driven Skills Registry & Phase 4 Contract SLA Compliance Auditor */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* DB-Driven Agent Skills Registry */}
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <PlusCircle className="h-4 w-4 text-emerald-400" />
                Database-Driven Agent Skills Registry ({registry?.skills_count || 0} Active Skills)
              </h3>
              <p className="text-[11px] text-slate-400">
                Add new skills directly to Supabase without touching code. The Central Orchestrator ingests them immediately.
              </p>
            </div>
          </div>

          <form onSubmit={handleRegisterSkill} className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
            <input
              type="text"
              required
              placeholder="Skill Slug (e.g. property_yield_analyzer)"
              value={skillForm.slug}
              onChange={(e) => setSkillForm({ ...skillForm, slug: e.target.value })}
              className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white font-mono"
            />
            <input
              type="text"
              required
              placeholder="Display Name (e.g. Property Yield Analyzer)"
              value={skillForm.name}
              onChange={(e) => setSkillForm({ ...skillForm, name: e.target.value })}
              className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
            />
            <select
              value={skillForm.service_slug}
              onChange={(e) => setSkillForm({ ...skillForm, service_slug: e.target.value })}
              className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
            >
              {CANONICAL_SERVICES.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.label}
                </option>
              ))}
            </select>
            <select
              value={skillForm.default_model_tier}
              onChange={(e) => setSkillForm({ ...skillForm, default_model_tier: e.target.value })}
              className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
            >
              <option value="fast_free">Fast Free Tier (Groq / Gemini / OpenRouter)</option>
              <option value="reasoning">Complex Reasoning Tier (DeepSeek Fallback)</option>
            </select>
            <textarea
              rows={2}
              required
              placeholder="Skill instructions & scope..."
              value={skillForm.description}
              onChange={(e) => setSkillForm({ ...skillForm, description: e.target.value })}
              className="sm:col-span-2 rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
            />
            <button
              type="submit"
              disabled={savingSkill}
              className="sm:col-span-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 py-2 font-bold text-white transition"
            >
              {savingSkill ? "Registering Skill in Supabase..." : "Register / Update DB-Driven Skill"}
            </button>
          </form>

          <div className="max-h-48 overflow-y-auto space-y-1.5 pt-2">
            {(registry?.skills || []).map((sk: any) => (
              <div
                key={sk.slug}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs"
              >
                <div>
                  <span className="font-bold text-white">{sk.name}</span>{" "}
                  <span className="font-mono text-[10px] text-emerald-400">({sk.slug})</span>
                  <p className="text-[10px] text-slate-400 truncate max-w-md">{sk.description}</p>
                </div>
                <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-slate-300">
                  {sk.default_model_tier} • ≤{sk.max_words}w
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Phase 4 Automated Contract SLA Compliance Agent */}
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
          <div className="border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <FileCheck className="h-4 w-4 text-emerald-400" />
              Phase 4 Automated Contract &amp; SLA Compliance Agent
            </h3>
            <p className="text-[11px] text-slate-400">
              Scan client contracts for SLA uptime breaches, unlimited liability clauses, or delayed milestones. Breaches automatically route to the HITL Approval Queue.
            </p>
          </div>

          <form onSubmit={handleRunContractAudit} className="space-y-2.5 text-xs">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <input
                type="text"
                required
                value={contractForm.contract_title}
                onChange={(e) => setContractForm({ ...contractForm, contract_title: e.target.value })}
                placeholder="Contract Title"
                className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
              />
              <input
                type="text"
                required
                value={contractForm.counterparty}
                onChange={(e) => setContractForm({ ...contractForm, counterparty: e.target.value })}
                placeholder="Counterparty Name"
                className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
              />
            </div>
            <div className="grid grid-cols-3 gap-2.5">
              <input
                type="number"
                step="0.1"
                value={contractForm.promised_uptime_pct}
                onChange={(e) =>
                  setContractForm({ ...contractForm, promised_uptime_pct: Number(e.target.value) })
                }
                placeholder="Promised SLA %"
                className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-1.5 text-white font-mono"
              />
              <input
                type="number"
                step="0.1"
                value={contractForm.observed_uptime_pct}
                onChange={(e) =>
                  setContractForm({ ...contractForm, observed_uptime_pct: Number(e.target.value) })
                }
                placeholder="Observed SLA %"
                className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-1.5 text-white font-mono"
              />
              <select
                value={contractForm.milestone_status}
                onChange={(e) => setContractForm({ ...contractForm, milestone_status: e.target.value })}
                className="rounded-lg bg-slate-900 border border-slate-700 px-2.5 py-1.5 text-white"
              >
                <option value="on_track">Milestone: On Track</option>
                <option value="delayed">Milestone: Delayed</option>
              </select>
            </div>
            <textarea
              rows={2}
              required
              value={contractForm.contract_text}
              onChange={(e) => setContractForm({ ...contractForm, contract_text: e.target.value })}
              className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
            />
            <button
              type="submit"
              disabled={runningContractAudit}
              className="w-full rounded-lg bg-indigo-600 hover:bg-indigo-500 py-2 font-bold text-white transition"
            >
              {runningContractAudit ? "Auditing Contract & SLAs..." : "Run Contract SLA Compliance Audit"}
            </button>
          </form>

          <div className="max-h-40 overflow-y-auto space-y-1.5">
            {contractAudits.map((ca) => (
              <div
                key={ca.id}
                className="rounded-lg border border-slate-800 bg-slate-900 p-2.5 text-xs flex items-center justify-between"
              >
                <div>
                  <p className="font-bold text-white">
                    {ca.contract_title} — <span className="text-slate-400">{ca.counterparty}</span>
                  </p>
                  <p className="text-[10px] text-slate-400 mt-0.5">{ca.ai_summary}</p>
                </div>
                <span
                  className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                    ca.risk_level === "high" || ca.risk_level === "critical"
                      ? "bg-red-500/20 text-red-300"
                      : "bg-emerald-500/20 text-emerald-300"
                  }`}
                >
                  {ca.risk_level}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* SECTION 3: Phase 3 Automated Freelancing Pipeline (Workforce Agent Execution + HITL Auto-Delivery) */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Briefcase className="h-4 w-4 text-emerald-400" />
              Phase 3 Automated Freelancing &amp; Agency Delivery Pipeline
            </h3>
            <p className="text-[11px] text-slate-400">
              Delegate client orders (SEO Audits, Content Packs, Bookkeeping Setups) to specialized workforce agents, run Self-Reflection QC, and approve for 1-click delivery.
            </p>
          </div>
        </div>

        <form onSubmit={handleCreateFreelanceOrder} className="grid grid-cols-1 md:grid-cols-5 gap-2.5 text-xs">
          <input
            type="text"
            required
            value={freelanceForm.client_name}
            onChange={(e) => setFreelanceForm({ ...freelanceForm, client_name: e.target.value })}
            placeholder="Client Name"
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
          />
          <input
            type="text"
            required
            value={freelanceForm.project_title}
            onChange={(e) => setFreelanceForm({ ...freelanceForm, project_title: e.target.value })}
            placeholder="Project Title"
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
          />
          <select
            value={freelanceForm.category}
            onChange={(e) => setFreelanceForm({ ...freelanceForm, category: e.target.value })}
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
          >
            <option value="seo_audit">SEO &amp; Technical Audit</option>
            <option value="content_pack">Omnichannel Content Pack</option>
            <option value="bookkeeping_setup">Zoho / Ledger Bookkeeping Setup</option>
          </select>
          <input
            type="text"
            required
            value={freelanceForm.requirements}
            onChange={(e) => setFreelanceForm({ ...freelanceForm, requirements: e.target.value })}
            placeholder="Brief requirements..."
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white"
          />
          <button
            type="submit"
            disabled={creatingFreelance}
            className="rounded-lg bg-emerald-600 hover:bg-emerald-500 px-4 py-2 font-bold text-white transition"
          >
            {creatingFreelance ? "Assigning..." : "+ Create Order"}
          </button>
        </form>

        {freelanceOrders.length > 0 && (
          <div className="space-y-2 pt-2">
            {freelanceOrders.map((ord) => (
              <div
                key={ord.id}
                className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900 p-3 text-xs"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white">{ord.project_title}</span>
                    <span className="text-slate-400">({ord.client_name})</span>
                    <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-emerald-300">
                      {ord.assigned_workforce_agent}
                    </span>
                    <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-[10px] font-bold uppercase text-indigo-300">
                      {ord.status}
                    </span>
                  </div>
                  {ord.deliverable_draft && (
                    <p className="text-[11px] text-slate-300 mt-1 line-clamp-2">
                      Draft: {ord.deliverable_draft}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {ord.status === "assigned" && (
                    <button
                      type="button"
                      disabled={executingOrderId === ord.id}
                      onClick={() => handleExecuteFreelanceOrder(ord.id)}
                      className="rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 font-bold text-white"
                    >
                      {executingOrderId === ord.id ? "Drafting..." : "Run Workforce Agent"}
                    </button>
                  )}
                  {ord.status === "pending_hitl_review" && (
                    <button
                      type="button"
                      disabled={executingOrderId === ord.id}
                      onClick={() => handleApproveDeliverFreelanceOrder(ord.id)}
                      className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 font-bold text-white"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      <span>Approve &amp; Auto-Deliver</span>
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
