"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { Sidebar } from "@/components/shared/Sidebar";
import { apiRequest } from "@/lib/api";
import { getActiveTenant, getAuthToken } from "@/lib/auth";
import { ControlPanelTab } from "@/components/lead-hunter/ControlPanelTab";
import { LeadFinderTab } from "@/components/lead-hunter/LeadFinderTab";
import { HotCallListTab } from "@/components/lead-hunter/HotCallListTab";
import { DemoApprovalTab } from "@/components/lead-hunter/DemoApprovalTab";
import { FollowupHandoverTab } from "@/components/lead-hunter/FollowupHandoverTab";
import { KanbanPipelineTab } from "@/components/lead-hunter/KanbanPipelineTab";
import {
  HunterDemo,
  HunterFollowup,
  HunterLead,
  HunterOverviewData,
} from "@/components/lead-hunter/types";
import {
  Target,
  Sliders,
  Search,
  PhoneCall,
  Sparkles,
  Repeat,
  Columns,
  RefreshCw,
  AlertOctagon,
  CheckCircle,
  AlertCircle,
} from "lucide-react";

type HunterTab = "call_list" | "control" | "finder" | "demos" | "followups" | "kanban";

export default function LeadHunterPage() {
  const [activeTab, setActiveTab] = useState<HunterTab>("call_list");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [busyModule, setBusyModule] = useState<string | null>(null);
  const [busyLeadId, setBusyLeadId] = useState<string | null>(null);
  const [busyDemoId, setBusyDemoId] = useState<string | null>(null);
  const [busyFu, setBusyFu] = useState(false);
  const [banner, setBanner] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const [overview, setOverview] = useState<HunterOverviewData | null>(null);
  const [countries, setCountries] = useState<string[]>(["USA", "UK", "Canada", "Australia", "UAE", "Singapore"]);
  const [citiesByCountry, setCitiesByCountry] = useState<Record<string, string[]>>({
    USA: ["New York", "Los Angeles", "Houston", "Miami", "Chicago"],
    UK: ["London", "Manchester"],
    Canada: ["Toronto"],
    Australia: ["Sydney"],
    UAE: ["Dubai"],
    Singapore: ["Singapore"],
  });
  const [categories, setCategories] = useState<string[]>([
    "Dental Clinic",
    "Medical Clinic",
    "Law Firm",
    "Real Estate Agency",
  ]);
  const [leads, setLeads] = useState<HunterLead[]>([]);
  const [callList, setCallList] = useState<HunterLead[]>([]);
  const [demos, setDemos] = useState<HunterDemo[]>([]);
  const [followups, setFollowups] = useState<HunterFollowup[]>([]);

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    try {
      const [ovRes, catRes, leadsRes, callRes, demosRes, fuRes] = await Promise.all([
        apiRequest<HunterOverviewData>("/api/v1/lead-hunter/overview"),
        apiRequest<any>("/api/v1/lead-hunter/catalog"),
        apiRequest<HunterLead[]>("/api/v1/lead-hunter/leads"),
        apiRequest<HunterLead[]>("/api/v1/lead-hunter/call-list"),
        apiRequest<HunterDemo[]>("/api/v1/lead-hunter/demos"),
        apiRequest<HunterFollowup[]>("/api/v1/lead-hunter/followups"),
      ]);
      if (ovRes.data) setOverview(ovRes.data);
      if (catRes.data) {
        if (Array.isArray(catRes.data.countries)) setCountries(catRes.data.countries);
        if (catRes.data.cities_by_country) setCitiesByCountry(catRes.data.cities_by_country);
        if (Array.isArray(catRes.data.categories)) setCategories(catRes.data.categories);
      }
      if (Array.isArray(leadsRes.data)) setLeads(leadsRes.data);
      if (Array.isArray(callRes.data)) setCallList(callRes.data);
      if (Array.isArray(demosRes.data)) setDemos(demosRes.data);
      if (Array.isArray(fuRes.data)) setFollowups(fuRes.data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const tok = getAuthToken();
    const tenant = getActiveTenant();
    if (!tok) {
      window.location.href = "/login";
      return;
    }
    if (!tenant) {
      window.location.href = "/onboarding";
      return;
    }
    loadWorkspace();
  }, [loadWorkspace]);

  const handleToggleModule = async (moduleName: string, isOn: boolean) => {
    setBusyModule(moduleName);
    setBanner(null);
    try {
      const res = await apiRequest(`/api/v1/lead-hunter/settings/${moduleName}`, {
        method: "PATCH",
        body: JSON.stringify({ is_on: isOn }),
      });
      if (res.success) {
        await loadWorkspace();
      } else {
        setBanner({ type: "err", text: res.error?.message || "Failed to update switch." });
      }
    } finally {
      setBusyModule(null);
    }
  };

  const handleUpdateLimit = async (moduleName: string, dailyLimit: number) => {
    setBusyModule(moduleName);
    setBanner(null);
    try {
      const res = await apiRequest(`/api/v1/lead-hunter/settings/${moduleName}`, {
        method: "PATCH",
        body: JSON.stringify({ daily_limit: dailyLimit }),
      });
      if (res.success) await loadWorkspace();
    } finally {
      setBusyModule(null);
    }
  };

  const handleApplyBudgetMode = async (mode: "free" | "low_budget" | "full_auto") => {
    setBusyModule("budget_mode");
    setBanner(null);
    try {
      const res = await apiRequest("/api/v1/lead-hunter/settings/budget-mode", {
        method: "POST",
        body: JSON.stringify({ budget_mode: mode }),
      });
      if (res.success) {
        setBanner({ type: "ok", text: `Applied ${mode.replace("_", " ").toUpperCase()} preset cleanly.` });
        await loadWorkspace();
      } else {
        setBanner({ type: "err", text: res.error?.message || "Failed to apply budget preset." });
      }
    } finally {
      setBusyModule(null);
    }
  };

  const handleSearchLeads = async (payload: {
    country: string;
    city: string;
    category: string;
    source_mode: "openstreetmap_free" | "google_places" | "apollo" | "hybrid";
    max_results: number;
  }) => {
    setSearching(true);
    setBanner(null);
    try {
      const res = await apiRequest<any>("/api/v1/lead-hunter/search", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (res.success) {
        setBanner({
          type: "ok",
          text: `Discovered ${res.data?.count || 0} real lead(s). Apollo free credits used: ${res.data?.apollo_credits_used || 0}.`,
        });
        await loadWorkspace();
      } else {
        setBanner({ type: "err", text: res.error?.message || "Lead search failed." });
      }
    } finally {
      setSearching(false);
    }
  };

  const handleEnrichApollo = async (leadId: string) => {
    setBusyLeadId(leadId);
    setBanner(null);
    try {
      const res = await apiRequest(`/api/v1/lead-hunter/leads/${leadId}/enrich-apollo`, { method: "POST" });
      if (res.success) {
        setBanner({ type: "ok", text: "Enriched decision-maker details from Apollo Free Tier." });
        await loadWorkspace();
      } else {
        setBanner({ type: "err", text: res.error?.message || "Apollo enrichment failed." });
      }
    } finally {
      setBusyLeadId(null);
    }
  };

  const handleImportApolloCsv = async (payload: {
    csv_text: string;
    default_country: string;
    default_city: string;
    default_category: string;
  }) => {
    setBanner(null);
    const res = await apiRequest<any>("/api/v1/lead-hunter/import-apollo-csv", {
      method: "POST",
      body: JSON.stringify({ ...payload, inspect_websites: true }),
    });
    if (res.success) {
      setBanner({
        type: "ok",
        text: `Imported ${res.data?.imported || 0} & merged ${res.data?.updated || 0} Apollo Free leads (${res.data?.hot_leads_count || 0} Hot Leads 80+).`,
      });
      await loadWorkspace();
    } else {
      setBanner({ type: "err", text: res.error?.message || "Failed to import Apollo CSV." });
    }
  };

  const handleSaveManualOwner = async (
    leadId: string,
    payload: {
      owner_name?: string;
      owner_title?: string;
      email?: string;
      linkedin_url?: string;
      phone?: string;
    }
  ) => {
    setBusyLeadId(leadId);
    setBanner(null);
    try {
      const res = await apiRequest(`/api/v1/lead-hunter/leads/${leadId}/owner`, {
        method: "PATCH",
        body: JSON.stringify({ ...payload, email_verified: true }),
      });
      if (res.success) {
        setBanner({ type: "ok", text: "Saved Apollo Free decision-maker details & updated score!" });
        await loadWorkspace();
      } else {
        setBanner({ type: "err", text: res.error?.message || "Failed to save owner details." });
      }
    } finally {
      setBusyLeadId(null);
    }
  };

  const handleGenerateDemo = async (leadId: string) => {
    setBusyLeadId(leadId);
    setBanner(null);
    try {
      const res = await apiRequest(`/api/v1/lead-hunter/leads/${leadId}/generate-demo`, { method: "POST" });
      if (res.success) {
        setBanner({ type: "ok", text: "Personalized English AI Receptionist demo saved to Draft tab for approval." });
        await loadWorkspace();
        setActiveTab("demos");
      } else {
        setBanner({ type: "err", text: res.error?.message || "Failed to generate demo." });
      }
    } finally {
      setBusyLeadId(null);
    }
  };

  const handlePromoteHot = async (leadId: string) => {
    setBusyLeadId(leadId);
    try {
      const res = await apiRequest(`/api/v1/lead-hunter/leads/${leadId}/promote-hot`, { method: "POST" });
      if (res.success) {
        setBanner({ type: "ok", text: "Lead promoted to Hot Call List (Score 80+)." });
        await loadWorkspace();
      }
    } finally {
      setBusyLeadId(null);
    }
  };

  const handleCallOutcome = async (leadId: string, outcome: string, dealValueUsd?: number) => {
    setBusyLeadId(leadId);
    setBanner(null);
    try {
      const res = await apiRequest(`/api/v1/lead-hunter/leads/${leadId}/outcome`, {
        method: "POST",
        body: JSON.stringify({ outcome, deal_value_usd: dealValueUsd }),
      });
      if (res.success) {
        setBanner({
          type: "ok",
          text:
            outcome === "call_later"
              ? "Scheduled 24-hour Call Later reminder."
              : `Updated outreach outcome to "${outcome}".`,
        });
        await loadWorkspace();
      } else {
        setBanner({ type: "err", text: res.error?.message || "Failed to record outcome." });
      }
    } finally {
      setBusyLeadId(null);
    }
  };

  const handleAcknowledgeHandover = async (leadId: string) => {
    setBusyLeadId(leadId);
    try {
      await apiRequest(`/api/v1/lead-hunter/leads/${leadId}/acknowledge-handover`, { method: "POST" });
      await loadWorkspace();
    } finally {
      setBusyLeadId(null);
    }
  };

  const handleSaveDemoDraft = async (demoId: string, payload: Partial<HunterDemo>) => {
    setBusyDemoId(demoId);
    try {
      const res = await apiRequest(`/api/v1/lead-hunter/demos/${demoId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      if (res.success) {
        setBanner({ type: "ok", text: "Demo draft saved." });
        await loadWorkspace();
      }
    } finally {
      setBusyDemoId(null);
    }
  };

  const handleApproveDemo = async (demoId: string) => {
    setBusyDemoId(demoId);
    try {
      const res = await apiRequest(`/api/v1/lead-hunter/demos/${demoId}/approve`, { method: "POST" });
      if (res.success) {
        setBanner({ type: "ok", text: "Demo approved and moved to Approved tab." });
        await loadWorkspace();
      }
    } finally {
      setBusyDemoId(null);
    }
  };

  const handleApproveAndSendDemo = async (demoId: string, channel: "email" | "linkedin" | "whatsapp") => {
    setBusyDemoId(demoId);
    setBanner(null);
    try {
      const appRes = await apiRequest(`/api/v1/lead-hunter/demos/${demoId}/approve`, { method: "POST" });
      if (!appRes.success) {
        setBanner({ type: "err", text: appRes.error?.message || "Failed to approve demo." });
        return;
      }
      const sendRes = await apiRequest(`/api/v1/lead-hunter/demos/${demoId}/send`, {
        method: "POST",
        body: JSON.stringify({ channel }),
      });
      if (sendRes.success) {
        setBanner({ type: "ok", text: `Demo approved and sent via ${channel}!` });
        await loadWorkspace();
      } else {
        setBanner({ type: "err", text: sendRes.error?.message || "Approved, but send blocked." });
        await loadWorkspace();
      }
    } finally {
      setBusyDemoId(null);
    }
  };

  const handleSendApprovedDemo = async (demoId: string, channel: "email" | "linkedin" | "whatsapp") => {
    setBusyDemoId(demoId);
    setBanner(null);
    try {
      const res = await apiRequest(`/api/v1/lead-hunter/demos/${demoId}/send`, {
        method: "POST",
        body: JSON.stringify({ channel }),
      });
      if (res.success) {
        setBanner({ type: "ok", text: `Approved demo dispatched via ${channel}.` });
        await loadWorkspace();
      } else {
        setBanner({ type: "err", text: res.error?.message || "Failed to dispatch demo." });
      }
    } finally {
      setBusyDemoId(null);
    }
  };

  const handleRejectDemo = async (demoId: string) => {
    setBusyDemoId(demoId);
    try {
      await apiRequest(`/api/v1/lead-hunter/demos/${demoId}/reject`, { method: "POST" });
      await loadWorkspace();
    } finally {
      setBusyDemoId(null);
    }
  };

  const handleProcessFollowups = async () => {
    setBusyFu(true);
    try {
      const res = await apiRequest<any>("/api/v1/lead-hunter/followups/process-due", {
        method: "POST",
        body: JSON.stringify({ force_due_in_test: false }),
      });
      if (res.success) {
        setBanner({ type: "ok", text: `Processed due follow-ups: ${res.data?.sent || 0} sent.` });
        await loadWorkspace();
      }
    } finally {
      setBusyFu(false);
    }
  };

  const handleSimulateReply = async (leadId: string, message: string, channel: string) => {
    setBusyFu(true);
    setBanner(null);
    try {
      const res = await apiRequest<any>(`/api/v1/lead-hunter/leads/${leadId}/reply`, {
        method: "POST",
        body: JSON.stringify({ message, channel }),
      });
      if (res.success) {
        setBanner({
          type: res.data?.do_not_disturb ? "err" : "ok",
          text: res.data?.do_not_disturb
            ? `Opt-out recorded: marked Not Interested - DND & cancelled ${res.data?.cancelled_followups || 0} follow-ups.`
            : `Instant Human Handover triggered! Cancelled ${res.data?.cancelled_followups || 0} follow-ups and paused AI.`,
        });
        await loadWorkspace();
      }
    } finally {
      setBusyFu(false);
    }
  };

  const handleMoveStage = async (leadId: string, pipelineStage: string) => {
    await apiRequest(`/api/v1/lead-hunter/leads/${leadId}/stage`, {
      method: "PATCH",
      body: JSON.stringify({ pipeline_stage: pipelineStage }),
    });
    await loadWorkspace();
  };

  const kpis = overview?.kpis;
  const alerts = overview?.human_needed_alerts || [];
  const modMap = overview?.control_panel.module_map || {};

  return (
    <div className="min-h-screen bg-[#070B14] text-slate-100 flex flex-col">
      <Navbar />
      <div className="flex flex-1">
        <Sidebar currentPath="/lead-hunter" />

        <main className="flex-1 min-w-0 p-4 sm:p-6 md:p-8 max-w-7xl mx-auto w-full space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-5">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-2">
                  <Target className="h-6 w-6 text-blue-500" />
                  <span>TALOX International Lead Hunter</span>
                </h1>
                <span className="rounded-full border border-blue-500/40 bg-blue-600/20 px-2.5 py-0.5 text-xs font-bold text-blue-300">
                  Zero-Overage Guardrail
                </span>
              </div>
              <p className="mt-1 text-xs sm:text-sm text-slate-400">
                Google Places + Apollo Free Enrichment + AI Detector + English Demo Studio + Instant Human Handover CRM.
              </p>
            </div>

            <button
              type="button"
              onClick={loadWorkspace}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 hover:border-blue-500 px-3.5 py-2 text-xs font-semibold text-white"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>

          {/* CRITICAL HUMAN HANDOVER RED BANNER */}
          {alerts.length > 0 && (
            <div className="rounded-xl border border-rose-500 bg-rose-950/50 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 shadow-lg shadow-rose-950/40">
              <div className="flex items-start gap-3">
                <AlertOctagon className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
                <div className="text-xs">
                  <div className="text-sm font-extrabold text-rose-200">
                    Human Needed - Contact Now ({alerts.length} Hot Prospect Reply)
                  </div>
                  <p className="text-rose-200/90 mt-0.5">
                    {alerts[0].business_name} ({alerts[0].owner_name || alerts[0].city}) replied:{" "}
                    &ldquo;{alerts[0].last_reply || "Interested"}&rdquo; — all auto follow-ups stopped automatically.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setActiveTab("call_list")}
                className="shrink-0 rounded-lg bg-rose-600 hover:bg-rose-500 px-3.5 py-2 text-xs font-bold text-white"
              >
                Open Hot Call List
              </button>
            </div>
          )}

          {banner && (
            <div
              className={`flex items-center gap-2 rounded-xl border p-3.5 text-xs font-medium ${
                banner.type === "ok"
                  ? "border-emerald-500/40 bg-emerald-950/30 text-emerald-200"
                  : "border-rose-500/40 bg-rose-950/30 text-rose-200"
              }`}
            >
              {banner.type === "ok" ? (
                <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" />
              ) : (
                <AlertCircle className="h-4 w-4 text-rose-400 shrink-0" />
              )}
              <span>{banner.text}</span>
            </div>
          )}

          {/* Top 8 Dashboard KPI Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
            {[
              { label: "Total Leads", val: kpis?.total_leads ?? 0, accent: "text-white" },
              { label: "No-AI Hot (80+)", val: kpis?.no_ai_hot_leads ?? 0, accent: "text-emerald-400" },
              {
                label: "Apollo Today",
                val: `${kpis?.apollo_credits_used_today ?? 0}/${kpis?.apollo_daily_limit ?? 10}`,
                accent: "text-blue-400",
              },
              { label: "Demos Generated", val: kpis?.demos_generated ?? 0, accent: "text-cyan-400" },
              { label: "Demos Sent", val: kpis?.demos_sent ?? 0, accent: "text-blue-300" },
              { label: "Human Needed", val: kpis?.replied_human_needed ?? 0, accent: "text-rose-400" },
              { label: "Paid Clients", val: kpis?.paid_clients ?? 0, accent: "text-emerald-300" },
              { label: "Revenue ($)", val: `$${(kpis?.revenue_usd ?? 0).toLocaleString()}`, accent: "text-emerald-400" },
            ].map((card) => (
              <div key={card.label} className="rounded-xl border border-slate-800 bg-slate-900/90 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 truncate">
                  {card.label}
                </div>
                <div className={`mt-1 text-lg font-extrabold font-mono ${card.accent}`}>{card.val}</div>
              </div>
            ))}
          </div>

          {/* 6 Main Tabs */}
          <div className="flex flex-wrap gap-2">
            {[
              { id: "call_list", label: `Hot Call List (${callList.length})`, icon: PhoneCall },
              { id: "control", label: "Control Panel", icon: Sliders },
              { id: "finder", label: `Lead Finder (${leads.length})`, icon: Search },
              { id: "demos", label: `Demos & Approval (${demos.length})`, icon: Sparkles },
              { id: "followups", label: `Follow-ups & Handover (${followups.length})`, icon: Repeat },
              { id: "kanban", label: "Kanban CRM", icon: Columns },
            ].map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id as HunterTab)}
                  className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-bold border transition ${
                    activeTab === tab.id
                      ? "border-blue-500 bg-blue-600 text-white shadow-md shadow-blue-900/40"
                      : "border-slate-800 bg-slate-900 text-slate-300 hover:border-blue-500/40"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {activeTab === "control" && overview && (
            <ControlPanelTab
              budgetMode={overview.control_panel.budget_mode}
              modules={overview.control_panel.modules}
              busyModule={busyModule}
              onToggleModule={handleToggleModule}
              onUpdateLimit={handleUpdateLimit}
              onApplyBudgetMode={handleApplyBudgetMode}
            />
          )}

          {activeTab === "finder" && (
            <LeadFinderTab
              countries={countries}
              citiesByCountry={citiesByCountry}
              categories={categories}
              leads={leads}
              apiKeysStatus={
                overview?.api_keys_status || {
                  openstreetmap_free_ready: true,
                  google_places_configured: false,
                  apollo_configured: false,
                }
              }
              freeOsmOn={Boolean(modMap.free_osm_finder?.is_on)}
              onEnableFreeOsm={() => handleToggleModule("free_osm_finder", true)}
              searching={searching}
              busyLeadId={busyLeadId}
              onSearch={handleSearchLeads}
              onEnrichApollo={handleEnrichApollo}
              onImportApolloCsv={handleImportApolloCsv}
              onSaveManualOwner={handleSaveManualOwner}
              onGenerateDemo={handleGenerateDemo}
              onPromoteHot={handlePromoteHot}
              onJumpToCallList={() => setActiveTab("call_list")}
            />
          )}

          {activeTab === "call_list" && (
            <HotCallListTab
              callList={callList}
              busyLeadId={busyLeadId}
              onOutcome={handleCallOutcome}
              onGenerateDemo={handleGenerateDemo}
              onAcknowledgeHandover={handleAcknowledgeHandover}
            />
          )}

          {activeTab === "demos" && (
            <DemoApprovalTab
              demos={demos}
              moduleMap={modMap}
              busyDemoId={busyDemoId}
              onSaveDraft={handleSaveDemoDraft}
              onApprove={handleApproveDemo}
              onApproveAndSend={handleApproveAndSendDemo}
              onSendApproved={handleSendApprovedDemo}
              onReject={handleRejectDemo}
            />
          )}

          {activeTab === "followups" && (
            <FollowupHandoverTab
              followups={followups}
              leads={leads}
              followupEngineOn={Boolean(modMap.auto_followup_engine?.is_on)}
              busy={busyFu}
              onProcessDue={handleProcessFollowups}
              onSimulateReply={handleSimulateReply}
            />
          )}

          {activeTab === "kanban" && (
            <KanbanPipelineTab leads={leads} onMoveStage={handleMoveStage} />
          )}
        </main>
      </div>
    </div>
  );
}
