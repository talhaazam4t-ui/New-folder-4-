"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  Globe,
  Mail,
  MessageSquare,
  Play,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { AdminNavbar } from "../../components/admin/AdminNavbar";
import { AdminSidebar } from "../../components/admin/AdminSidebar";
import { Navbar } from "../../components/shared/Navbar";
import { Sidebar } from "../../components/shared/Sidebar";
import { apiRequest } from "../../lib/api";
import {
  clearActiveTenant,
  getActiveTenant,
  getAuthToken,
  isSuperAdminUser,
  setActiveTenant,
} from "../../lib/auth";

interface TenantSummary {
  id: string;
  name: string;
  slug: string;
  industry?: string;
}

interface AgentItem {
  name: string;
  category: string;
  description: string;
  version: string;
  allowed_tools: string[];
  max_steps: number;
  enabled_for_tenant: boolean;
  execution_limit: number;
  budget_limit: number;
}

interface StageResult {
  agent_name: string;
  role: string;
  model: string;
  output: string;
  tokens_used: number;
  estimated_cost: number;
}

interface ApprovalItem {
  id: string;
  task_id: string | null;
  action_type: string;
  proposed_action: Record<string, unknown>;
  status: string;
  requested_by: string;
  expires_at: string;
}

interface ExecutionItem {
  id: string;
  task_id: string;
  status: string;
  tokens_used: number;
  estimated_cost: number;
  duration_ms: number | null;
  created_at: string;
}

interface AutopilotRunSummary {
  niche?: string;
  city?: string;
  data_source?: string;
  leads_discovered?: number;
  emails_enriched_from_websites?: number;
  drafts_saved_in_gmail?: number;
  drafts_saved_in_crm?: number;
  draft_errors?: number;
  contact_only_found?: number;
  synced_pending_drafts?: number;
  ran_at?: string;
}

interface AutopilotConfig {
  enabled: boolean;
  niches: string[];
  cities: string[];
  channels?: string[];
  require_human_approval?: boolean;
  daily_draft_limit: number;
  service_offer: string;
  sender_name: string;
  booking_url: string;
  run_hour_utc: number;
  rotation_index: number;
  last_run_at: string | null;
  last_run_summary: AutopilotRunSummary | null;
}

interface AutopilotQuota {
  plan_name: string;
  service_slug: string | null;
  monthly_lead_limit: number;
  leads_used_this_month: number;
  remaining_leads: number;
  quota_exhausted: boolean;
}

interface AutopilotGmailStatus {
  connected: boolean;
  account: string | null;
  oauth_ready: boolean;
  has_refresh_token: boolean;
  has_compose_scope: boolean;
  can_create_live_drafts: boolean;
  needs_oauth_authorize: boolean;
}

interface AutopilotStats {
  total_drafted: number;
  saved_in_gmail_count: number;
  pending_oauth_sync_count: number;
  contact_only_count: number;
  pending_approval_count?: number;
  approved_sent_count?: number;
}

interface AutopilotDraftItem {
  lead_id: string;
  company_name: string;
  email: string | null;
  phone: string | null;
  website: string | null;
  niche: string | null;
  city: string | null;
  subject: string | null;
  body: string | null;
  whatsapp_pitch?: string | null;
  whatsapp_url?: string | null;
  linkedin_note?: string | null;
  linkedin_dm?: string | null;
  linkedin_search_url?: string | null;
  draft_id: string | null;
  draft_status: string;
  approval_status?: string;
  gmail_sent_at?: string | null;
  whatsapp_status?: string | null;
  linkedin_status?: string | null;
  drafted_at: string;
  email_source: string | null;
  gmail_error: string | null;
}

interface AutopilotStatePayload {
  config: AutopilotConfig;
  quota?: AutopilotQuota;
  gmail_status: AutopilotGmailStatus;
  next_target: { niche: string; city: string };
  stats: AutopilotStats;
  drafted_leads: AutopilotDraftItem[];
}

const PRESET_NICHES = [
  "Clinics / Hospitals",
  "Dental & Aesthetic Clinics",
  "Real Estate / Property",
  "Enterprise & Software Companies",
  "Law & Accounting Firms",
  "Financing & Advisory",
  "E-Commerce",
];

function formatHourWithPkt(hourUtc: number): string {
  const pktHour = (hourUtc + 5) % 24;
  const format12 = (h: number) => {
    const suffix = h >= 12 ? "PM" : "AM";
    const h12 = h % 12 === 0 ? 12 : h % 12;
    return `${h12}:00 ${suffix}`;
  };
  return `${String(hourUtc).padStart(2, "0")}:00 UTC (${format12(pktHour)} PKT)`;
}

function toWhatsAppUrl(phone: string | null): string | null {
  if (!phone) return null;
  const digits = phone.replace(/[^\d]/g, "").replace(/^00/, "");
  if (digits.length < 7) return null;
  return `https://wa.me/${digits}`;
}

export default function AgentsPage() {
  const [tenants, setTenants] = useState<TenantSummary[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string>("");
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [executions, setExecutions] = useState<ExecutionItem[]>([]);
  const [selectedAgent, setSelectedAgent] = useState("master_orchestrator");
  const [objective, setObjective] = useState("");
  const [actionType, setActionType] = useState("");
  const [stages, setStages] = useState<StageResult[]>([]);
  const [finalOutput, setFinalOutput] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [isAdminView, setIsAdminView] = useState(false);

  // Phase 2 Dynamic Skills, Episodic Memories & QC Self-Reflection state
  const [dynamicSkills, setDynamicSkills] = useState<any[]>([]);
  const [selectedSkillSlug, setSelectedSkillSlug] = useState<string>("");
  const [episodicMemories, setEpisodicMemories] = useState<any[]>([]);
  const [dynamicQcResult, setDynamicQcResult] = useState<any | null>(null);
  const [runningDynamicSkill, setRunningDynamicSkill] = useState(false);

  // Daily Global Outreach & Gmail Draft Autopilot state
  const [apEnabled, setApEnabled] = useState(false);
  const [apNiches, setApNiches] = useState<string[]>(PRESET_NICHES);
  const [apChannels, setApChannels] = useState<string[]>(["gmail", "whatsapp", "linkedin"]);
  const [apRequireApproval, setApRequireApproval] = useState(true);
  const [apQuota, setApQuota] = useState<AutopilotQuota | null>(null);
  const [customNicheInput, setCustomNicheInput] = useState("");
  const [apCitiesInput, setApCitiesInput] = useState(
    "Dubai, London, Toronto, Riyadh, New York, Sydney, Singapore, Abu Dhabi, Manchester, Lahore"
  );
  const [apDailyLimit, setApDailyLimit] = useState(5);
  const [apRunHourUtc, setApRunHourUtc] = useState(6);
  const [apSenderName, setApSenderName] = useState("Teloxtech AI Automation");
  const [apBookingUrl, setApBookingUrl] = useState("https://cal.com/talha-azam-jhhqzd/30min");
  const [apServiceOffer, setApServiceOffer] = useState("");
  const [apGmailStatus, setApGmailStatus] = useState<AutopilotGmailStatus | null>(null);
  const [apNextTarget, setApNextTarget] = useState<{ niche: string; city: string } | null>(null);
  const [apStats, setApStats] = useState<AutopilotStats | null>(null);
  const [apLastRunAt, setApLastRunAt] = useState<string | null>(null);
  const [apLastRunSummary, setApLastRunSummary] = useState<AutopilotRunSummary | null>(null);
  const [apDrafts, setApDrafts] = useState<AutopilotDraftItem[]>([]);
  const [quickRunNiche, setQuickRunNiche] = useState("");
  const [quickRunCity, setQuickRunCity] = useState("");
  const [autopilotSaving, setAutopilotSaving] = useState(false);
  const [autopilotRunning, setAutopilotRunning] = useState(false);
  const [autopilotSyncing, setAutopilotSyncing] = useState(false);
  const [authorizingGmail, setAuthorizingGmail] = useState(false);
  const [expandedDraftId, setExpandedDraftId] = useState<string | null>(null);
  const [copiedLeadId, setCopiedLeadId] = useState<string | null>(null);
  const [channelTabByLead, setChannelTabByLead] = useState<Record<string, "gmail" | "whatsapp" | "linkedin">>({});
  const [dispatchingLeadKey, setDispatchingLeadKey] = useState<string | null>(null);

  const applyAutopilotState = useCallback((payload: AutopilotStatePayload) => {
    if (!payload) return;
    if (payload.config) {
      setApEnabled(Boolean(payload.config.enabled));
      setApNiches(
        Array.isArray(payload.config.niches) && payload.config.niches.length > 0
          ? payload.config.niches
          : PRESET_NICHES
      );
      setApChannels(
        Array.isArray(payload.config.channels) && payload.config.channels.length > 0
          ? payload.config.channels
          : ["gmail", "whatsapp", "linkedin"]
      );
      setApRequireApproval(payload.config.require_human_approval ?? true);
      setApCitiesInput(
        Array.isArray(payload.config.cities) && payload.config.cities.length > 0
          ? payload.config.cities.join(", ")
          : "Dubai, London, Toronto, Riyadh"
      );
      setApDailyLimit(payload.config.daily_draft_limit || 5);
      setApRunHourUtc(payload.config.run_hour_utc ?? 6);
      setApSenderName(payload.config.sender_name || "Teloxtech AI Automation");
      setApBookingUrl(payload.config.booking_url || "");
      setApServiceOffer(payload.config.service_offer || "");
      setApLastRunAt(payload.config.last_run_at || null);
      setApLastRunSummary(payload.config.last_run_summary || null);
    }
    if (payload.quota) setApQuota(payload.quota);
    if (payload.gmail_status) setApGmailStatus(payload.gmail_status);
    if (payload.next_target) setApNextTarget(payload.next_target);
    if (payload.stats) setApStats(payload.stats);
    if (Array.isArray(payload.drafted_leads)) {
      setApDrafts(payload.drafted_leads);
    }
  }, []);

  const loadAgentWorkspace = useCallback(
    async (tenantIdOverride?: string) => {
      const tId = tenantIdOverride || selectedTenantId || getActiveTenant()?.id;
      if (!tId) return;

      const reqHeaders = { "X-Tenant-ID": tId };
      const [agentsRes, approvalsRes, execsRes, autopilotRes, regRes, memRes] = await Promise.all([
        apiRequest("/api/v1/agents", { headers: reqHeaders }),
        apiRequest("/api/v1/approvals?status=pending", { headers: reqHeaders }),
        apiRequest("/api/v1/agents/executions?limit=25", { headers: reqHeaders }),
        apiRequest("/api/v1/agents/outreach-autopilot", { headers: reqHeaders }),
        apiRequest("/api/v1/agents/registry", { headers: reqHeaders }),
        apiRequest("/api/v1/agents/memories?limit=6", { headers: reqHeaders }),
      ]);

      if (regRes?.data?.skills && Array.isArray(regRes.data.skills)) {
        setDynamicSkills(regRes.data.skills);
      }
      if (Array.isArray(memRes?.data)) {
        setEpisodicMemories(memRes.data);
      }

      if (Array.isArray(agentsRes)) setAgents(agentsRes);
      else if (agentsRes.data) setAgents(agentsRes.data);
      else if (agentsRes.error) setErrorMessage(agentsRes.error.message);

      if (Array.isArray(approvalsRes)) setApprovals(approvalsRes);
      else if (approvalsRes.data) setApprovals(approvalsRes.data);
      else if (approvalsRes.error) setErrorMessage(approvalsRes.error.message);

      if (Array.isArray(execsRes)) setExecutions(execsRes);
      else if (execsRes.data) setExecutions(execsRes.data);

      if (autopilotRes?.success && autopilotRes.data) {
        applyAutopilotState(autopilotRes.data as AutopilotStatePayload);
      }
    },
    [applyAutopilotState, selectedTenantId]
  );

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }

    if (typeof window !== "undefined") {
      const urlParams = new URLSearchParams(window.location.search);
      const connected = urlParams.get("connected");
      const statusParam = urlParams.get("status");
      const oauthError = urlParams.get("error");
      if (connected === "gmail" && statusParam === "success") {
        setStatusMessage(
          "Gmail OAuth 2.0 authorized with Compose permission! Agents can now save drafts directly into your Gmail Drafts folder."
        );
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (oauthError) {
        setErrorMessage(`Gmail OAuth error: ${oauthError}`);
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }

    const adminMode = isSuperAdminUser();
    setIsAdminView(adminMode);

    (async () => {
      let currentTenant = getActiveTenant();
      if (!adminMode) {
        if (!currentTenant?.id) {
          const tenantsRes = await apiRequest("/api/v1/tenants");
          const list = Array.isArray(tenantsRes)
            ? tenantsRes
            : Array.isArray(tenantsRes?.data)
            ? tenantsRes.data
            : [];
          if (list.length > 0) {
            currentTenant = list[0];
            setActiveTenant(list[0], true);
          }
        }
        if (currentTenant?.id) {
          setSelectedTenantId(currentTenant.id);
          await loadAgentWorkspace(currentTenant.id);
        } else {
          window.location.href = "/onboarding";
        }
        return;
      }

      const tenantsRes = await apiRequest("/api/v1/admin/tenants");
      const list: TenantSummary[] = Array.isArray(tenantsRes?.data) ? tenantsRes.data : [];
      setTenants(list);

      const isValidStoredTenant =
        Boolean(currentTenant?.id) &&
        (list.length === 0 || list.some((t) => t.id === currentTenant!.id));

      if (!isValidStoredTenant) {
        if (list.length > 0) {
          currentTenant = list[0];
          setActiveTenant(list[0], false);
        } else {
          clearActiveTenant();
          currentTenant = null;
        }
      }

      if (currentTenant?.id) {
        setSelectedTenantId(currentTenant.id);
        await loadAgentWorkspace(currentTenant.id);
      } else {
        setErrorMessage("No client workspaces registered yet. Create or onboard a tenant first.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSwitchTenant = async (tenantId: string) => {
    setSelectedTenantId(tenantId);
    setErrorMessage(null);
    setStatusMessage(null);
    const chosen = tenants.find((t) => t.id === tenantId);
    if (chosen) {
      setActiveTenant(chosen, false);
    }
    await loadAgentWorkspace(tenantId);
  };

  const handleToggleNiche = (niche: string) => {
    setApNiches((prev) => {
      if (prev.includes(niche)) {
        if (prev.length <= 1) return prev;
        return prev.filter((item) => item !== niche);
      }
      return [...prev, niche];
    });
  };

  const handleAddCustomNiche = () => {
    const cleaned = customNicheInput.trim();
    if (!cleaned) return;
    if (!apNiches.some((item) => item.toLowerCase() === cleaned.toLowerCase())) {
      setApNiches((prev) => [...prev, cleaned]);
    }
    setCustomNicheInput("");
  };

  const handleAuthorizeGmailOAuth = async () => {
    const tId = selectedTenantId || getActiveTenant()?.id;
    if (!tId) return;
    setErrorMessage(null);
    setStatusMessage(null);
    setAuthorizingGmail(true);
    try {
      const chosen = tenants.find((t) => t.id === tId);
      if (chosen) {
        setActiveTenant(chosen, !isAdminView);
      }
      const res = await apiRequest(
        "/api/v1/integrations/oauth/gmail/authorize?return_to=/agents",
        { headers: { "X-Tenant-ID": tId } }
      );
      if (res.success && res.data?.authorization_url) {
        if (typeof window !== "undefined") {
          sessionStorage.setItem("talox_oauth_return_to", "/agents");
          window.location.href = res.data.authorization_url;
        }
      } else {
        setErrorMessage(
          res.error?.message || "Failed to generate Google OAuth URL for Gmail Drafts."
        );
      }
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to initiate Gmail OAuth.");
    } finally {
      setAuthorizingGmail(false);
    }
  };

  const handleToggleChannel = (channel: string) => {
    setApChannels((prev) => {
      if (prev.includes(channel)) {
        if (prev.length <= 1) return prev;
        return prev.filter((c) => c !== channel);
      }
      return [...prev, channel];
    });
  };

  const handleSaveAutopilot = async (e: React.FormEvent) => {
    e.preventDefault();
    const tId = selectedTenantId || getActiveTenant()?.id;
    if (!tId) return;

    setAutopilotSaving(true);
    setErrorMessage(null);
    setStatusMessage(null);

    const parsedCities = apCitiesInput
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean);

    const res = await apiRequest("/api/v1/agents/outreach-autopilot", {
      method: "PUT",
      headers: { "X-Tenant-ID": tId },
      body: JSON.stringify({
        enabled: apEnabled,
        niches: apNiches,
        cities: parsedCities.length > 0 ? parsedCities : ["Dubai", "London", "Toronto", "Riyadh"],
        channels: apChannels,
        require_human_approval: apRequireApproval,
        daily_draft_limit: apDailyLimit,
        run_hour_utc: apRunHourUtc,
        sender_name: apSenderName,
        booking_url: apBookingUrl,
        service_offer: apServiceOffer,
      }),
    });

    setAutopilotSaving(false);
    if (res.success && res.data) {
      applyAutopilotState(res.data as AutopilotStatePayload);
      setStatusMessage(
        apEnabled
          ? `Daily Global Autopilot is ACTIVE (${apDailyLimit} company drafts/day at ${formatHourWithPkt(apRunHourUtc)}).`
          : "Autopilot preferences saved (Daily auto-scheduler is paused; Run Now still works anytime)."
      );
    } else {
      setErrorMessage(res.error?.message || "Failed to save Daily Autopilot configuration.");
    }
  };

  const handleRunAutopilotNow = async () => {
    const tId = selectedTenantId || getActiveTenant()?.id;
    if (!tId) return;

    setAutopilotRunning(true);
    setErrorMessage(null);
    setStatusMessage(null);

    const res = await apiRequest("/api/v1/agents/outreach-autopilot/run", {
      method: "POST",
      headers: { "X-Tenant-ID": tId },
      body: JSON.stringify({
        niche: quickRunNiche || null,
        city: quickRunCity.trim() || null,
        limit: apDailyLimit,
        sync_pending_crm_drafts: Boolean(apGmailStatus?.can_create_live_drafts),
      }),
    });

    setAutopilotRunning(false);
    if (res.success && res.data) {
      const payload = res.data as {
        run_summary: AutopilotRunSummary;
        created_drafts: Array<{ lead_id: string }>;
        state: AutopilotStatePayload;
      };
      if (payload.state) {
        applyAutopilotState(payload.state);
      }
      if (payload.created_drafts?.[0]?.lead_id) {
        setExpandedDraftId(payload.created_drafts[0].lead_id);
      }
      const s = payload.run_summary || {};
      setStatusMessage(
        `Cycle complete (${s.niche || "Global"} in ${s.city || "World"}): ${s.leads_discovered || 0} new businesses found, ${s.drafts_saved_in_gmail || 0} saved directly to Gmail Drafts, ${s.drafts_saved_in_crm || 0} saved in CRM review queue${s.contact_only_found ? `, ${s.contact_only_found} phone/web-only leads added` : ""}. Nothing was auto-sent.`
      );
      await loadAgentWorkspace(tId);
    } else {
      setErrorMessage(res.error?.message || "Failed to run Global Lead-Finder & Draft cycle.");
    }
  };

  const handleSyncPendingDrafts = async () => {
    const tId = selectedTenantId || getActiveTenant()?.id;
    if (!tId) return;

    setAutopilotSyncing(true);
    setErrorMessage(null);
    setStatusMessage(null);

    const res = await apiRequest("/api/v1/agents/outreach-autopilot/sync-drafts", {
      method: "POST",
      headers: { "X-Tenant-ID": tId },
    });

    setAutopilotSyncing(false);
    if (res.success && res.data) {
      const payload = res.data as {
        synced_count: number;
        failed_count: number;
        state: AutopilotStatePayload;
      };
      if (payload.state) {
        applyAutopilotState(payload.state);
      }
      setStatusMessage(
        `Synced ${payload.synced_count || 0} CRM drafts into Gmail Drafts${payload.failed_count ? ` (${payload.failed_count} failed)` : ""}.`
      );
    } else {
      setErrorMessage(res.error?.message || "Failed to sync drafts into Gmail.");
    }
  };

  const handleCopyPitch = async (item: AutopilotDraftItem, textOverride?: string | null) => {
    const text = (textOverride || `Subject: ${item.subject || ""}\n\n${item.body || ""}`).trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedLeadId(item.lead_id);
      setTimeout(() => {
        setCopiedLeadId((curr) => (curr === item.lead_id ? null : curr));
      }, 2000);
    } catch {
      setErrorMessage("Browser clipboard permission denied. Expand the draft to copy manually.");
    }
  };

  const handleApproveSendLead = async (
    item: AutopilotDraftItem,
    channel: "gmail" | "whatsapp" | "linkedin",
    mode: "send" | "draft" = "send"
  ) => {
    const tId = selectedTenantId || getActiveTenant()?.id;
    if (!tId) return;

    const actionKey = `${item.lead_id}_${channel}_${mode}`;
    setDispatchingLeadKey(actionKey);
    setErrorMessage(null);
    setStatusMessage(null);

    const res = await apiRequest(`/api/v1/agents/outreach-autopilot/leads/${item.lead_id}/approve-send`, {
      method: "POST",
      headers: { "X-Tenant-ID": tId },
      body: JSON.stringify({ channel, mode }),
    });

    setDispatchingLeadKey(null);
    if (res.success && res.data) {
      const payload = res.data as {
        action_result?: {
          status?: string;
          whatsapp_url?: string;
          linkedin_search_url?: string;
          linkedin_note?: string;
        };
        state?: AutopilotStatePayload;
      };
      if (payload.state) applyAutopilotState(payload.state);
      const act = payload.action_result || {};

      if (channel === "whatsapp" && act.whatsapp_url && act.status === "approved_wa_me_ready") {
        window.open(act.whatsapp_url, "_blank", "noopener,noreferrer");
        setStatusMessage(`Approved WhatsApp pitch for ${item.company_name} — opened pre-filled WhatsApp chat.`);
      } else if (channel === "linkedin") {
        if (act.linkedin_note && navigator?.clipboard) {
          navigator.clipboard.writeText(act.linkedin_note).catch(() => {});
        }
        if (act.linkedin_search_url) {
          window.open(act.linkedin_search_url, "_blank", "noopener,noreferrer");
        }
        setStatusMessage(
          `Approved LinkedIn outreach for ${item.company_name} — copied invite note & opened LinkedIn people search.`
        );
      } else if (channel === "gmail" && mode === "draft") {
        setStatusMessage(`Gmail Draft synced for ${item.company_name}.`);
      } else {
        setStatusMessage(`Approved & dispatched ${channel.toUpperCase()} message to ${item.company_name}!`);
      }
    } else {
      setErrorMessage(res.error?.message || `Failed to dispatch ${channel} outreach.`);
    }
  };

  const handleRejectLead = async (item: AutopilotDraftItem) => {
    const tId = selectedTenantId || getActiveTenant()?.id;
    if (!tId) return;

    setDispatchingLeadKey(`${item.lead_id}_reject`);
    setErrorMessage(null);
    setStatusMessage(null);

    const res = await apiRequest(`/api/v1/agents/outreach-autopilot/leads/${item.lead_id}/reject`, {
      method: "POST",
      headers: { "X-Tenant-ID": tId },
      body: JSON.stringify({ reason: "Skipped by human reviewer" }),
    });

    setDispatchingLeadKey(null);
    if (res.success && res.data?.state) {
      applyAutopilotState(res.data.state as AutopilotStatePayload);
      setStatusMessage(`Skipped ${item.company_name} from outbound queue.`);
    } else {
      setErrorMessage(res.error?.message || "Failed to reject lead outreach.");
    }
  };

  const handleToggleAgent = async (agent: AgentItem) => {
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest(`/api/v1/agents/${agent.name}/configure`, {
      method: "POST",
      headers: selectedTenantId ? { "X-Tenant-ID": selectedTenantId } : undefined,
      body: JSON.stringify({
        enabled: !agent.enabled_for_tenant,
        execution_limit: agent.execution_limit,
        budget_limit: agent.budget_limit,
      }),
    });
    if (!res.error && (res.name || res.data?.name || res.success)) {
      setStatusMessage(`Updated configuration for ${agent.name}`);
      loadAgentWorkspace();
    } else {
      setErrorMessage(res.error?.message || `Failed to update configuration for ${agent.name}.`);
    }
  };

  const handleOrchestrate = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunning(true);
    setStatusMessage(null);
    setErrorMessage(null);
    setStages([]);
    setFinalOutput(null);

    const res = await apiRequest("/api/v1/agents/orchestrate", {
      method: "POST",
      headers: selectedTenantId ? { "X-Tenant-ID": selectedTenantId } : undefined,
      body: JSON.stringify({
        objective,
        agent_name: selectedAgent,
        action_type: actionType || null,
      }),
    });

    setRunning(false);
    const payload = res.data || res;
    if (!res.error && payload && payload.status) {
      setStages(payload.stages || []);
      setFinalOutput(payload.final_output || null);
      if (payload.requires_approval) {
        setStatusMessage("Action paused for Human-in-the-Loop Approval.");
      } else {
        setStatusMessage(`Orchestration completed (${payload.total_tokens || 0} tokens).`);
      }
      loadAgentWorkspace();
    } else {
      setErrorMessage(res.error?.message || "Agent orchestration failed.");
    }
  };

  const handleRunDynamicSkill = async () => {
    if (!objective.trim()) return;
    setRunningDynamicSkill(true);
    setStatusMessage(null);
    setErrorMessage(null);
    setDynamicQcResult(null);
    try {
      const res = await apiRequest("/api/v1/agents/orchestrate-dynamic", {
        method: "POST",
        headers: selectedTenantId ? { "X-Tenant-ID": selectedTenantId } : undefined,
        body: JSON.stringify({
          objective,
          skill_slug: selectedSkillSlug || null,
        }),
      });
      if (res.success && res.data) {
        setDynamicQcResult(res.data);
        setFinalOutput(res.data.final_output || null);
        setStatusMessage(
          `Dynamic Skill "${res.data.selected_skill?.name}" executed with Episodic Memory & QC Self-Reflection (${res.data.tokens_consumed || 0} tokens).`
        );
        loadAgentWorkspace();
      } else {
        setErrorMessage(res.error?.message || "Dynamic skill orchestration failed.");
      }
    } finally {
      setRunningDynamicSkill(false);
    }
  };

  const handleDecision = async (approvalId: string, decision: "approve" | "reject") => {
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest(`/api/v1/approvals/${approvalId}/${decision}`, {
      method: "POST",
      headers: selectedTenantId ? { "X-Tenant-ID": selectedTenantId } : undefined,
      body: JSON.stringify({ reason: `Reviewed via Agent Governance Console (${decision})` }),
    });
    if (!res.error && (res.success || res.id || res.data?.id)) {
      setStatusMessage(`Approval request ${decision}d.`);
      loadAgentWorkspace();
    } else {
      setErrorMessage(res.error?.message || `Failed to ${decision} approval request.`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {isAdminView ? <AdminNavbar /> : <Navbar />}
      <div className="flex flex-1">
        {isAdminView ? (
          <AdminSidebar currentPath="/agents" activeTab="" />
        ) : (
          <Sidebar currentPath="/agents" />
        )}
        <main className="flex-1 min-w-0 p-4 sm:p-6 md:p-8 space-y-8 overflow-y-auto">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-white">AI Agent Orchestration & Outreach Autopilot</h1>
              <p className="text-slate-400 text-sm mt-1">
                Daily global B2B lead discovery + personalized Gmail Draft composer (strictly review-before-send) and bounded multi-agent pipelines.
              </p>
            </div>
            {tenants.length > 0 && (
              <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs">
                <span className="text-slate-400">Workspace:</span>
                <select
                  value={selectedTenantId}
                  onChange={(e) => handleSwitchTenant(e.target.value)}
                  className="bg-transparent font-semibold text-emerald-400 focus:outline-none"
                >
                  {tenants.map((t) => (
                    <option key={t.id} value={t.id} className="bg-slate-900 text-white">
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {statusMessage && (
            <div className="flex items-start gap-2.5 p-4 rounded-lg bg-emerald-950/60 border border-emerald-700 text-emerald-200 text-sm">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400 mt-0.5" />
              <span>{statusMessage}</span>
            </div>
          )}

          {errorMessage && (
            <div className="flex items-start gap-2.5 p-4 rounded-lg bg-red-950/60 border border-red-700 text-red-200 text-sm">
              <AlertCircle className="h-4 w-4 shrink-0 text-red-400 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Daily Global Niche Lead-Finder & Gmail Draft Autopilot */}
          <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 sm:p-6 space-y-6">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-800 pb-5">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Globe className="h-5 w-5 text-emerald-400" />
                  <h2 className="text-lg font-bold text-white">
                    Daily Global Niche Lead-Finder & Gmail Draft Autopilot
                  </h2>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
                      apEnabled
                        ? "bg-emerald-950/80 text-emerald-300 border-emerald-600/60"
                        : "bg-slate-800 text-slate-300 border-slate-700"
                    }`}
                  >
                    {apEnabled ? "Daily Schedule ACTIVE" : "Schedule Paused (Manual Run Ready)"}
                  </span>
                </div>
                <p className="text-xs text-slate-400">
                  Har roz worldwide clinics, property agencies, enterprises & firms dhoondh kar har company ke naam se alag personalized email aap ke Gmail Drafts me save karta hai (khud kabhi send nahi karta).
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <a
                  href="https://mail.google.com/mail/#drafts"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-medium text-slate-200 hover:border-slate-500 transition"
                >
                  <Mail className="h-3.5 w-3.5 text-rose-400" />
                  Open Gmail Drafts
                  <ExternalLink className="h-3 w-3 opacity-70" />
                </a>
                <button
                  type="button"
                  onClick={handleAuthorizeGmailOAuth}
                  disabled={authorizingGmail}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-semibold transition ${
                    apGmailStatus?.can_create_live_drafts
                      ? "border border-emerald-700/70 bg-emerald-950/60 text-emerald-200 hover:bg-emerald-900/60"
                      : "bg-amber-500 hover:bg-amber-400 text-slate-950"
                  }`}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${authorizingGmail ? "animate-spin" : ""}`} />
                  {apGmailStatus?.can_create_live_drafts
                    ? "Re-authorize Gmail OAuth"
                    : "Authorize Gmail for Auto-Drafts (OAuth)"}
                </button>
              </div>
            </div>

            {/* Gmail Connection Readiness Banner */}
            {apGmailStatus && (
              <div
                className={`rounded-lg border p-4 text-xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 ${
                  apGmailStatus.can_create_live_drafts
                    ? "bg-emerald-950/30 border-emerald-700/60 text-emerald-200"
                    : "bg-amber-950/30 border-amber-600/50 text-amber-100"
                }`}
              >
                <div className="space-y-1">
                  {apGmailStatus.can_create_live_drafts ? (
                    <>
                      <p className="font-semibold text-emerald-300">
                        Live Gmail Drafts Ready: {apGmailStatus.account || "Connected Google Account"}
                      </p>
                      <p className="text-emerald-200/80">
                        Google OAuth token & Compose permission active hain. Har naya pitch seedha aap ke Gmail Drafts folder me save hoga.
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="font-semibold text-amber-300">
                        {apGmailStatus.account
                          ? `Gmail Email Linked (${apGmailStatus.account}) — One-Click Google OAuth Needed for Live Drafts`
                          : "Gmail Not Authorized Yet — Click 'Authorize Gmail for Auto-Drafts (OAuth)'"}
                      </p>
                      <p className="text-amber-100/80">
                        Abhi sirf email ID linked hai (live Google OAuth compose token save nahi hua). OAuth approve karne tak agents sari company drafts neeche Review Queue me save rakhenge; authorize ke baad 1 click se Gmail Drafts me push ho jayengi.
                      </p>
                    </>
                  )}
                </div>

                {apGmailStatus.can_create_live_drafts &&
                  (apStats?.pending_oauth_sync_count || 0) > 0 && (
                    <button
                      type="button"
                      onClick={handleSyncPendingDrafts}
                      disabled={autopilotSyncing}
                      className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-3.5 py-2 text-xs font-semibold text-white transition"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${autopilotSyncing ? "animate-spin" : ""}`} />
                      {autopilotSyncing
                        ? "Syncing to Gmail..."
                        : `Push ${apStats?.pending_oauth_sync_count} Pending Drafts to Gmail`}
                    </button>
                  )}
              </div>
            )}

            {/* Monthly Lead Tier Quota Banner */}
            {apQuota && (
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-3.5 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-400">Monthly Lead Tier Quota:</span>
                    <span className="px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-700/60 font-semibold uppercase text-[10px]">
                      {apQuota.plan_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-white font-semibold">
                      {apQuota.leads_used_this_month} / {apQuota.monthly_lead_limit} leads used ({apQuota.remaining_leads} remaining)
                    </span>
                    {!isAdminView && (
                      <a href="/billing" className="text-emerald-400 hover:underline font-medium">
                        Upgrade Tier ↗
                      </a>
                    )}
                  </div>
                </div>
                <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className={`h-full transition-all ${
                      apQuota.quota_exhausted ? "bg-rose-500" : "bg-emerald-500"
                    }`}
                    style={{
                      width: `${Math.min(
                        100,
                        Math.round(
                          (apQuota.leads_used_this_month / Math.max(1, apQuota.monthly_lead_limit)) * 100
                        )
                      )}%`,
                    }}
                  />
                </div>
              </div>
            )}

            {/* Stats & Next Target */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                <div className="text-[11px] text-slate-400">Next Daily Rotation</div>
                <div className="text-xs font-semibold text-emerald-300 mt-1 truncate">
                  {apNextTarget ? `${apNextTarget.niche} • ${apNextTarget.city}` : "Configured on save"}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                <div className="text-[11px] text-slate-400">Saved in Gmail Drafts</div>
                <div className="text-lg font-bold text-emerald-400 mt-0.5">
                  {apStats?.saved_in_gmail_count ?? 0}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                <div className="text-[11px] text-slate-400">Pending Gmail Sync (CRM)</div>
                <div className="text-lg font-bold text-amber-300 mt-0.5">
                  {apStats?.pending_oauth_sync_count ?? 0}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                <div className="text-[11px] text-slate-400">Phone / Web Only Leads</div>
                <div className="text-lg font-bold text-sky-300 mt-0.5">
                  {apStats?.contact_only_count ?? 0}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                <div className="text-[11px] text-slate-400">Last Auto/Manual Run</div>
                <div className="text-xs font-medium text-slate-200 mt-1">
                  {apLastRunAt ? new Date(apLastRunAt).toLocaleString() : "Not run yet"}
                </div>
                {apLastRunSummary?.city && (
                  <div className="text-[11px] text-slate-400 truncate">
                    {apLastRunSummary.niche} • {apLastRunSummary.city}
                  </div>
                )}
              </div>
            </div>

            {/* Schedule & Niche/City Targeting Form */}
            <form onSubmit={handleSaveAutopilot} className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-800 bg-slate-950/80 p-4">
                <div>
                  <div className="text-sm font-semibold text-white">Enable Automatic Daily Global Runs</div>
                  <p className="text-xs text-slate-400">
                    Rozana aik new Niche + City pair scan kar ke {apDailyLimit} fresh company drafts tayar karta hai.
                  </p>
                </div>
                <label className="inline-flex items-center gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={apEnabled}
                    onChange={(e) => setApEnabled(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-emerald-500 focus:ring-emerald-500"
                  />
                  <span className="text-xs font-semibold text-emerald-300">
                    {apEnabled ? "ON (Runs Daily)" : "OFF (Manual Only)"}
                  </span>
                </label>
              </div>

              {/* Multi-Channel Selection + HITL Gate */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 rounded-lg border border-slate-800 bg-slate-950/60 p-4 text-xs">
                <div className="space-y-2">
                  <div className="font-medium text-slate-300">
                    Outreach Channels (Pitches Generated Per Company)
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {[
                      { id: "gmail", label: "Gmail (Drafts + Approved Send)" },
                      { id: "whatsapp", label: "WhatsApp (Cloud API / wa.me)" },
                      { id: "linkedin", label: "LinkedIn (Invite Note & DM)" },
                    ].map((ch) => {
                      const active = apChannels.includes(ch.id);
                      return (
                        <button
                          key={ch.id}
                          type="button"
                          onClick={() => handleToggleChannel(ch.id)}
                          className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition ${
                            active
                              ? "bg-emerald-950/70 border-emerald-600 text-emerald-200"
                              : "bg-slate-950 border-slate-800 text-slate-400"
                          }`}
                        >
                          {active ? "✓ " : "+ "}
                          {ch.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3 md:border-l md:border-slate-800 md:pl-4">
                  <div>
                    <div className="font-medium text-slate-200">Mandatory Human-in-the-Loop Gate</div>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Drafts save for your approval first — zero unapproved cold messages leave automatically.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={apRequireApproval}
                    onChange={(e) => setApRequireApproval(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-emerald-500"
                  />
                </div>
              </div>

              {/* Target Niches Chips */}
              <div className="space-y-2">
                <label className="block text-xs font-medium text-slate-300">
                  Target Industries / Niches (Worldwide)
                </label>
                <div className="flex flex-wrap gap-2">
                  {Array.from(new Set([...PRESET_NICHES, ...apNiches])).map((niche) => {
                    const selected = apNiches.includes(niche);
                    return (
                      <button
                        key={niche}
                        type="button"
                        onClick={() => handleToggleNiche(niche)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition ${
                          selected
                            ? "bg-indigo-600/30 border-indigo-500 text-indigo-200"
                            : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
                        }`}
                      >
                        {selected ? "✓ " : "+ "}
                        {niche}
                      </button>
                    );
                  })}
                </div>
                <div className="flex gap-2 pt-1 max-w-md">
                  <input
                    type="text"
                    value={customNicheInput}
                    onChange={(e) => setCustomNicheInput(e.target.value)}
                    placeholder="Add custom niche (e.g. Logistics, Hotels, HVAC)"
                    className="flex-1 rounded-lg bg-slate-950 border border-slate-800 px-3 py-1.5 text-xs text-white"
                  />
                  <button
                    type="button"
                    onClick={handleAddCustomNiche}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs text-white"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="md:col-span-2">
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Worldwide Cities Rotation (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={apCitiesInput}
                    onChange={(e) => setApCitiesInput(e.target.value)}
                    placeholder="Dubai, London, Toronto, Riyadh, New York, Sydney, Singapore, Lahore"
                    className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-xs text-white"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Drafts / Day (1-15)
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={15}
                      value={apDailyLimit}
                      onChange={(e) =>
                        setApDailyLimit(Math.min(15, Math.max(1, Number(e.target.value) || 5)))
                      }
                      className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-xs text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Run Time Daily
                    </label>
                    <select
                      value={apRunHourUtc}
                      onChange={(e) => setApRunHourUtc(Number(e.target.value))}
                      className="w-full rounded-lg bg-slate-950 border border-slate-800 px-2.5 py-2 text-xs text-white"
                    >
                      {[4, 5, 6, 7, 8, 9, 10, 12, 14, 16].map((hr) => (
                        <option key={hr} value={hr}>
                          {formatHourWithPkt(hr)}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Sender / Agency Signature
                  </label>
                  <input
                    type="text"
                    value={apSenderName}
                    onChange={(e) => setApSenderName(e.target.value)}
                    className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-xs text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Demo Booking URL (Cal.com)
                  </label>
                  <input
                    type="text"
                    value={apBookingUrl}
                    onChange={(e) => setApBookingUrl(e.target.value)}
                    placeholder="https://cal.com/talha-azam-jhhqzd/30min"
                    className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-xs text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Core Service Pitch Used to Tailor Each Company&apos;s Draft
                </label>
                <textarea
                  rows={2}
                  value={apServiceOffer}
                  onChange={(e) => setApServiceOffer(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-xs text-white"
                />
              </div>

              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pt-1">
                <button
                  type="submit"
                  disabled={autopilotSaving}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 px-4 py-2.5 text-xs font-semibold text-white transition"
                >
                  <Check className="h-4 w-4" />
                  {autopilotSaving ? "Saving Schedule..." : "Save Daily Autopilot Schedule"}
                </button>

                {/* Instant On-Demand Run Bar */}
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-950 p-2">
                  <select
                    value={quickRunNiche}
                    onChange={(e) => setQuickRunNiche(e.target.value)}
                    className="rounded bg-slate-900 border border-slate-800 px-2.5 py-1.5 text-xs text-slate-200"
                  >
                    <option value="">Next Auto Niche ({apNextTarget?.niche || "Rotate"})</option>
                    {apNiches.map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    value={quickRunCity}
                    onChange={(e) => setQuickRunCity(e.target.value)}
                    placeholder={`City (${apNextTarget?.city || "Auto"})`}
                    className="w-36 rounded bg-slate-900 border border-slate-800 px-2.5 py-1.5 text-xs text-white"
                  />
                  <button
                    type="button"
                    onClick={handleRunAutopilotNow}
                    disabled={autopilotRunning}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-3.5 py-1.5 text-xs font-semibold text-white transition"
                  >
                    {autopilotRunning ? (
                      <>
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        Finding Companies & Drafting...
                      </>
                    ) : (
                      <>
                        <Play className="h-3.5 w-3.5" />
                        Run Now — Find Companies & Save Drafts
                      </>
                    )}
                  </button>
                </div>
              </div>
            </form>

            {/* Company-Specific Drafts Review Queue */}
            <div className="border-t border-slate-800 pt-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-emerald-400" />
                  Prepared Company Outreach Drafts ({apDrafts.length})
                </h3>
                <span className="text-[11px] text-slate-400">
                  Review each draft here or directly inside Gmail Drafts before clicking Send.
                </span>
              </div>

              {apDrafts.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-800 bg-slate-950/50 p-6 text-center text-xs text-slate-400">
                  No autopilot drafts generated yet for this workspace. Click{" "}
                  <span className="font-semibold text-emerald-300">Run Now — Find Companies & Save Drafts</span>{" "}
                  above to discover businesses and prepare tailored drafts!
                </div>
              ) : (
                <div className="space-y-2.5">
                  {apDrafts.map((item) => {
                    const isExpanded = expandedDraftId === item.lead_id;
                    const activeCh = channelTabByLead[item.lead_id] || "gmail";
                    const waUrl = item.whatsapp_url || toWhatsAppUrl(item.phone);
                    const statusBadgeClass =
                      item.draft_status === "sent_via_gmail" || item.draft_status === "saved_in_gmail"
                        ? "bg-emerald-950 text-emerald-300 border-emerald-700"
                        : item.draft_status === "contact_only_no_email"
                        ? "bg-sky-950 text-sky-300 border-sky-700"
                        : item.draft_status === "gmail_api_error"
                        ? "bg-rose-950 text-rose-300 border-rose-700"
                        : "bg-amber-950 text-amber-300 border-amber-700";

                    const statusLabel =
                      item.draft_status === "sent_via_gmail"
                        ? "Sent via Gmail"
                        : item.draft_status === "saved_in_gmail"
                        ? "Saved in Gmail Drafts"
                        : item.draft_status === "contact_only_no_email"
                        ? "Phone / Web Only (No Public Email)"
                        : item.draft_status === "gmail_api_error"
                        ? "Gmail Sync Needs Retry"
                        : "Saved in CRM (Pending Gmail OAuth)";

                    const approvalBadgeClass =
                      item.approval_status === "approved_sent"
                        ? "bg-emerald-950/90 text-emerald-300 border-emerald-600/70"
                        : item.approval_status === "rejected"
                        ? "bg-slate-800 text-slate-400 border-slate-700"
                        : "bg-amber-950/80 text-amber-300 border-amber-600/60";

                    const approvalLabel =
                      item.approval_status === "approved_sent"
                        ? "Human Approved & Sent"
                        : item.approval_status === "rejected"
                        ? "Skipped"
                        : "Pending Human Approval";

                    return (
                      <div
                        key={item.lead_id}
                        className="rounded-lg border border-slate-800 bg-slate-950 p-4 space-y-2.5"
                      >
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                          <div className="space-y-0.5 min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-semibold text-sm text-white">
                                {item.company_name}
                              </span>
                              {item.niche && (
                                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[11px]">
                                  {item.niche}
                                </span>
                              )}
                              {item.city && (
                                <span className="px-2 py-0.5 rounded bg-indigo-950/70 text-indigo-300 text-[11px]">
                                  {item.city}
                                </span>
                              )}
                              <span
                                className={`px-2 py-0.5 rounded border text-[11px] font-medium ${statusBadgeClass}`}
                              >
                                {statusLabel}
                              </span>
                              <span
                                className={`px-2 py-0.5 rounded border text-[11px] font-medium ${approvalBadgeClass}`}
                              >
                                {approvalLabel}
                              </span>
                            </div>
                            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                              {item.email && (
                                <span className="text-emerald-300">
                                  {item.email}
                                  {item.email_source === "public_website" ? " (from website)" : ""}
                                </span>
                              )}
                              {item.phone && <span>Tel: {item.phone}</span>}
                              {item.website && !item.website.includes("openstreetmap.org") && (
                                <a
                                  href={
                                    item.website.startsWith("http")
                                      ? item.website
                                      : `https://${item.website}`
                                  }
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-sky-400 hover:underline inline-flex items-center gap-1"
                                >
                                  Website <ExternalLink className="h-3 w-3" />
                                </a>
                              )}
                            </div>
                          </div>

                          <div className="flex flex-wrap items-center gap-2 shrink-0">
                            {item.email && (
                              <button
                                type="button"
                                disabled={dispatchingLeadKey === `${item.lead_id}_gmail_send`}
                                onClick={() => handleApproveSendLead(item, "gmail", "send")}
                                className="inline-flex items-center gap-1 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-2.5 py-1 text-xs font-semibold text-white"
                              >
                                <Send className="h-3 w-3" />
                                {dispatchingLeadKey === `${item.lead_id}_gmail_send`
                                  ? "Sending..."
                                  : "Approve & Send Gmail"}
                              </button>
                            )}
                            {waUrl && (
                              <button
                                type="button"
                                disabled={dispatchingLeadKey === `${item.lead_id}_whatsapp_send`}
                                onClick={() => handleApproveSendLead(item, "whatsapp", "send")}
                                className="inline-flex items-center gap-1 rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 px-2.5 py-1 text-xs font-medium text-white"
                              >
                                <MessageSquare className="h-3 w-3" />
                                {dispatchingLeadKey === `${item.lead_id}_whatsapp_send`
                                  ? "Sending..."
                                  : "Approve WhatsApp"}
                              </button>
                            )}
                            {item.linkedin_search_url && (
                              <button
                                type="button"
                                disabled={dispatchingLeadKey === `${item.lead_id}_linkedin_send`}
                                onClick={() => handleApproveSendLead(item, "linkedin", "send")}
                                className="inline-flex items-center gap-1 rounded bg-sky-700 hover:bg-sky-600 disabled:opacity-50 px-2.5 py-1 text-xs font-medium text-white"
                              >
                                <ExternalLink className="h-3 w-3" />
                                Approve LinkedIn
                              </button>
                            )}
                            {item.approval_status !== "rejected" && (
                              <button
                                type="button"
                                disabled={dispatchingLeadKey === `${item.lead_id}_reject`}
                                onClick={() => handleRejectLead(item)}
                                className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-900 hover:bg-rose-950/70 hover:border-rose-700 px-2 py-1 text-xs text-slate-300"
                              >
                                <X className="h-3 w-3" />
                                Skip
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedDraftId(isExpanded ? null : item.lead_id)
                              }
                              className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-900 hover:bg-slate-800 px-2.5 py-1 text-xs text-slate-200"
                            >
                              {isExpanded ? (
                                <>
                                  Hide <ChevronUp className="h-3 w-3" />
                                </>
                              ) : (
                                <>
                                  Pitches <ChevronDown className="h-3 w-3" />
                                </>
                              )}
                            </button>
                          </div>
                        </div>

                        {item.subject && (
                          <div className="text-xs text-slate-300">
                            <span className="text-slate-500">Subject: </span>
                            <span className="font-medium text-white">{item.subject}</span>
                          </div>
                        )}

                        {item.gmail_error && (
                          <div className="text-[11px] text-rose-300 bg-rose-950/40 border border-rose-800/50 rounded px-2.5 py-1.5">
                            Gmail API Note: {item.gmail_error}
                          </div>
                        )}

                        {isExpanded && (
                          <div className="space-y-2.5 rounded-lg border border-slate-800 bg-slate-900/90 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
                              <div className="flex items-center gap-1.5">
                                {(["gmail", "whatsapp", "linkedin"] as const).map((tabKey) => (
                                  <button
                                    key={tabKey}
                                    type="button"
                                    onClick={() =>
                                      setChannelTabByLead((prev) => ({
                                        ...prev,
                                        [item.lead_id]: tabKey,
                                      }))
                                    }
                                    className={`px-2.5 py-1 rounded text-xs font-medium capitalize ${
                                      activeCh === tabKey
                                        ? "bg-indigo-600 text-white"
                                        : "bg-slate-950 text-slate-400 hover:text-white"
                                    }`}
                                  >
                                    {tabKey}
                                  </button>
                                ))}
                              </div>
                              <div className="flex items-center gap-2">
                                {activeCh === "gmail" && item.email && (
                                  <button
                                    type="button"
                                    onClick={() => handleApproveSendLead(item, "gmail", "draft")}
                                    className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
                                  >
                                    Save Gmail Draft
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => {
                                    const txt =
                                      activeCh === "whatsapp"
                                        ? item.whatsapp_pitch
                                        : activeCh === "linkedin"
                                        ? `Invite Note:\n${item.linkedin_note || ""}\n\nFollow-up DM:\n${item.linkedin_dm || ""}`
                                        : null;
                                    handleCopyPitch(item, txt);
                                  }}
                                  className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-950 hover:bg-slate-800 px-2.5 py-1 text-xs text-slate-200"
                                >
                                  {copiedLeadId === item.lead_id ? (
                                    <>
                                      <Check className="h-3 w-3 text-emerald-400" />
                                      Copied
                                    </>
                                  ) : (
                                    <>
                                      <Copy className="h-3 w-3" />
                                      Copy {activeCh.toUpperCase()}
                                    </>
                                  )}
                                </button>
                              </div>
                            </div>

                            {activeCh === "gmail" && (
                              <pre className="whitespace-pre-wrap font-sans text-xs text-slate-200 leading-relaxed">
                                {item.body || "No email draft generated."}
                              </pre>
                            )}
                            {activeCh === "whatsapp" && (
                              <pre className="whitespace-pre-wrap font-sans text-xs text-emerald-200 leading-relaxed">
                                {item.whatsapp_pitch || "No WhatsApp pitch available."}
                              </pre>
                            )}
                            {activeCh === "linkedin" && (
                              <div className="space-y-2 text-xs">
                                <div>
                                  <div className="text-[11px] font-semibold text-sky-300">
                                    Connection Invite Note (&le; 300 chars)
                                  </div>
                                  <p className="text-slate-200 mt-0.5 whitespace-pre-wrap">
                                    {item.linkedin_note || "No LinkedIn note available."}
                                  </p>
                                </div>
                                <div>
                                  <div className="text-[11px] font-semibold text-sky-300">
                                    Post-Connect Follow-Up DM
                                  </div>
                                  <p className="text-slate-200 mt-0.5 whitespace-pre-wrap">
                                    {item.linkedin_dm || "No LinkedIn DM available."}
                                  </p>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </section>

          {/* Interactive Orchestrator Console + Pending Approvals */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                <h2 className="text-lg font-semibold text-white">
                  Run Multi-Agent Orchestrator (Live DB Grounded)
                </h2>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
                    apGmailStatus?.connected
                      ? "bg-emerald-950/80 border-emerald-700 text-emerald-300"
                      : "bg-amber-950/80 border-amber-700 text-amber-300"
                  }`}
                >
                  {apGmailStatus?.connected
                    ? "● LIVE EXTERNAL DELIVERY READY"
                    : "● SANDBOX DRAFT MODE (Connect Gmail/WhatsApp in /settings)"}
                </span>
              </div>
              <form onSubmit={handleOrchestrate} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Target Agent</label>
                    <select
                      value={selectedAgent}
                      onChange={(e) => setSelectedAgent(e.target.value)}
                      className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                    >
                      {agents.map((a) => (
                        <option key={a.name} value={a.name}>
                          {a.name} ({a.category})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">DB-Driven Skill (Phase 2)</label>
                    <select
                      value={selectedSkillSlug}
                      onChange={(e) => setSelectedSkillSlug(e.target.value)}
                      className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                    >
                      <option value="">Auto-Select Best Skill</option>
                      {dynamicSkills.map((sk) => (
                        <option key={sk.slug} value={sk.slug}>
                          {sk.name} (≤{sk.max_words}w)
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Action Classification (Optional)</label>
                    <select
                      value={actionType}
                      onChange={(e) => setActionType(e.target.value)}
                      className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                    >
                      <option value="">Standard Bounded Task</option>
                      <option value="publish_marketing_campaign">Publish Campaign (Requires Approval)</option>
                      <option value="send_bulk_whatsapp">Bulk WhatsApp Broadcast (Requires Approval)</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Business or Operational Objective</label>
                  <textarea
                    required
                    rows={3}
                    value={objective}
                    onChange={(e) => setObjective(e.target.value)}
                    placeholder="e.g. Analyze this month's rent collection rate and draft polite follow-up reminders for overdue units."
                    className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <button
                    type="submit"
                    disabled={running || runningDynamicSkill}
                    className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium transition"
                  >
                    {running ? "Orchestrating 4-Stage Pipeline..." : "Execute 4-Stage Agent Pipeline"}
                  </button>
                  <button
                    type="button"
                    onClick={handleRunDynamicSkill}
                    disabled={running || runningDynamicSkill || !objective.trim()}
                    className="w-full py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-semibold transition"
                  >
                    {runningDynamicSkill
                      ? "Running Skill + QC Reflection..."
                      : "Run Phase 2 Skill + QC Reflection"}
                  </button>
                </div>
              </form>

              {dynamicQcResult && (
                <div className="mt-4 p-3.5 rounded-lg bg-slate-950 border border-emerald-800/60 text-xs space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-emerald-300">
                      Skill: {dynamicQcResult.selected_skill?.name} ({dynamicQcResult.selected_skill?.service_slug})
                    </span>
                    <span className="font-mono text-[11px] text-slate-400">
                      QC Words: {dynamicQcResult.qc_report?.word_count_after}/
                      {dynamicQcResult.qc_report?.max_words_limit} • HITL: {dynamicQcResult.hitl_status}
                    </span>
                  </div>
                  <p className="text-slate-200 whitespace-pre-wrap">{dynamicQcResult.final_output}</p>
                </div>
              )}

              {episodicMemories.length > 0 && (
                <div className="mt-4 pt-3 border-t border-slate-800 space-y-1.5">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Proactive Episodic Memory ({episodicMemories.length} Recent Learnings Injected)
                  </div>
                  <div className="max-h-32 overflow-y-auto space-y-1">
                    {episodicMemories.map((m) => (
                      <div
                        key={m.id}
                        className="rounded bg-slate-950 border border-slate-800/80 px-2.5 py-1.5 text-[11px] text-slate-300 flex items-center justify-between gap-2"
                      >
                        <span className="truncate">
                          <strong className="text-indigo-300">[{m.memory_type}]</strong> {m.summary}
                        </span>
                        <span className="shrink-0 font-mono text-[10px] text-emerald-400">
                          {m.outcome_score}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {stages.length > 0 && (
                <div className="mt-6 space-y-3 border-t border-slate-800 pt-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Pipeline Execution Trace
                  </h3>
                  {stages.map((st, idx) => (
                    <div key={idx} className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs space-y-1">
                      <div className="flex justify-between text-indigo-300 font-medium">
                        <span>
                          Stage {idx + 1}: {st.role} ({st.agent_name})
                        </span>
                        <span className="text-slate-400">
                          {st.model} • {st.tokens_used} tok
                        </span>
                      </div>
                      <p className="text-slate-300 whitespace-pre-wrap">{st.output}</p>
                    </div>
                  ))}
                </div>
              )}
              {finalOutput && stages.length === 0 && (
                <div className="mt-4 p-3 rounded-lg bg-amber-950/40 border border-amber-800 text-amber-200 text-xs">
                  {finalOutput}
                </div>
              )}
            </div>

            {/* Human-in-the-Loop Approval Queue */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-white mb-4">
                Pending Human Approvals ({approvals.length})
              </h2>
              {approvals.length === 0 ? (
                <p className="text-sm text-slate-500">
                  No sensitive actions awaiting human verification.
                </p>
              ) : (
                <div className="space-y-3">
                  {approvals.map((app) => (
                    <div
                      key={app.id}
                      className="p-4 rounded-lg bg-slate-950 border border-amber-800/60 space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-900/50 text-amber-300">
                          {app.action_type}
                        </span>
                        <span className="text-xs text-slate-400">
                          Requested by {app.requested_by}
                        </span>
                      </div>
                      <pre className="text-xs text-slate-300 bg-slate-900 p-2 rounded overflow-x-auto">
                        {JSON.stringify(app.proposed_action, null, 2)}
                      </pre>
                      <div className="flex gap-2 pt-1">
                        <button
                          onClick={() => handleDecision(app.id, "approve")}
                          className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium"
                        >
                          Approve & Execute
                        </button>
                        <button
                          onClick={() => handleDecision(app.id, "reject")}
                          className="px-3 py-1.5 rounded bg-rose-700 hover:bg-rose-600 text-white text-xs font-medium"
                        >
                          Reject & Cancel
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Registered Agents Matrix */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-5 border-b border-slate-800">
              <h2 className="text-lg font-semibold text-white">Bounded Agent Registry & Tool Permissions</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-950 text-slate-400 text-xs uppercase">
                  <tr>
                    <th className="py-3 px-4">Agent</th>
                    <th className="py-3 px-4">Category</th>
                    <th className="py-3 px-4">Explicit Allowed Tools</th>
                    <th className="py-3 px-4">Max Steps</th>
                    <th className="py-3 px-4">Budget Cap</th>
                    <th className="py-3 px-4">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {agents.map((ag) => (
                    <tr key={ag.name} className="hover:bg-slate-800/40">
                      <td className="py-3 px-4">
                        <div className="font-medium text-white">{ag.name}</div>
                        <div className="text-xs text-slate-400">{ag.description}</div>
                      </td>
                      <td className="py-3 px-4 text-xs uppercase text-indigo-300">{ag.category}</td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1">
                          {ag.allowed_tools.map((t) => (
                            <span
                              key={t}
                              className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-xs"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-slate-300">{ag.max_steps}</td>
                      <td className="py-3 px-4 text-slate-300">${ag.budget_limit.toFixed(2)}</td>
                      <td className="py-3 px-4">
                        <button
                          onClick={() => handleToggleAgent(ag)}
                          className={`px-2.5 py-1 rounded text-xs font-medium ${
                            ag.enabled_for_tenant
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-700"
                              : "bg-slate-800 text-slate-400 border border-slate-700"
                          }`}
                        >
                          {ag.enabled_for_tenant ? "Enabled" : "Disabled"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Execution Telemetry */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-5 border-b border-slate-800">
              <h2 className="text-lg font-semibold text-white">Recent Execution Telemetry</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-950 text-slate-400 text-xs uppercase">
                  <tr>
                    <th className="py-3 px-4">Execution ID</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Tokens</th>
                    <th className="py-3 px-4">Est. Cost (USD)</th>
                    <th className="py-3 px-4">Duration</th>
                    <th className="py-3 px-4">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {executions.map((ex) => (
                    <tr key={ex.id}>
                      <td className="py-3 px-4 font-mono text-xs text-slate-300">{ex.id.slice(0, 12)}...</td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-xs bg-emerald-950 text-emerald-300">
                          {ex.status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-300">{ex.tokens_used}</td>
                      <td className="py-3 px-4 text-slate-300">${ex.estimated_cost.toFixed(5)}</td>
                      <td className="py-3 px-4 text-slate-400">{ex.duration_ms ?? 0} ms</td>
                      <td className="py-3 px-4 text-xs text-slate-400">
                        {new Date(ex.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
