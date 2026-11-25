"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { Sidebar } from "@/components/shared/Sidebar";
import { StatCard } from "@/components/dashboard/StatCard";
import { apiFetchResponse, apiRequest } from "@/lib/api";
import { getActiveTenant, getAuthToken, setActiveTenant } from "@/lib/auth";
import {
  PhoneCall,
  CalendarCheck2,
  PhoneForwarded,
  Clock,
  Copy,
  Check,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  FileText,
  AlertCircle,
  CheckCircle2,
  Play,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  KeyRound,
  PhoneIncoming,
  Globe,
  Upload,
  Search,
  Trash2,
  BellRing,
} from "lucide-react";

interface CallForwardingGuide {
  business_name?: string;
  assigned_ai_number?: string;
  fallback_human_number?: string;
  quick_dial_codes?: Record<string, string>;
  steps?: string[];
  ios_android_menu_tip?: string;
}

interface ReceptionistConfig {
  id: string;
  tenant_id: string;
  business_name: string;
  operating_hours: string;
  fallback_phone_number: string;
  greeting_message: string;
  faqs_knowledge_base: string;
  calcom_booking_url: string | null;
  calcom_event_type_id: string | null;
  calcom_api_key_configured: boolean;
  telnyx_phone_number: string | null;
  retell_agent_id: string | null;
  voice_id: string;
  provisioning_status: string;
  provisioning_notes: string | null;
  call_forwarding_guide: CallForwardingGuide;
  updated_at: string;
}

interface ReceptionistCallLog {
  id: string;
  tenant_id: string;
  external_call_id: string;
  caller_phone: string;
  caller_name: string | null;
  to_number: string | null;
  direction: string;
  duration_seconds: number;
  status: string;
  booking_status: string;
  booked_appointment_at: string | null;
  calcom_booking_uid: string | null;
  transferred_to_human: boolean;
  summary: string | null;
  transcript: string | null;
  recording_url: string | null;
  sentiment?: string | null;
  lead_tier?: string | null;
  lead_score?: number | null;
  reminder_sent_at?: string | null;
  created_at: string;
}

interface KnowledgeDocumentItem {
  id: string;
  title: string;
  source_type: string;
  source_url: string | null;
  chunk_count: number;
  char_count: number;
  created_at: string | null;
}

interface KnowledgeSearchMatch {
  chunk_id: string;
  document_title: string;
  content: string;
  score: number;
}

interface CallsSummary {
  total_calls: number;
  appointments_booked: number;
  human_transfers: number;
  avg_duration_seconds: number;
}

function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds || 0));
  const mins = Math.floor(s / 60);
  const rem = s % 60;
  return mins > 0 ? `${mins}m ${rem}s` : `${rem}s`;
}

export default function OfficeReceptionistPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [provisioning, setProvisioning] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [config, setConfig] = useState<ReceptionistConfig | null>(null);
  const [paymentApproved, setPaymentApproved] = useState<boolean>(false);
  const [hasSubscription, setHasSubscription] = useState<boolean>(false);
  const [calls, setCalls] = useState<ReceptionistCallLog[]>([]);
  const [bookedAppointments, setBookedAppointments] = useState<ReceptionistCallLog[]>([]);
  const [summary, setSummary] = useState<CallsSummary>({
    total_calls: 0,
    appointments_booked: 0,
    human_transfers: 0,
    avg_duration_seconds: 0,
  });

  // Editable config & FAQs form
  const [businessName, setBusinessName] = useState("");
  const [operatingHours, setOperatingHours] = useState("Mon-Fri 9:00 AM - 6:00 PM");
  const [fallbackPhone, setFallbackPhone] = useState("");
  const [greetingMessage, setGreetingMessage] = useState(
    "Hello! Thank you for calling. I'm the AI Receptionist — how can I assist you today?"
  );
  const [faqsKnowledgeBase, setFaqsKnowledgeBase] = useState("");
  const [calcomBookingUrl, setCalcomBookingUrl] = useState("");
  const [calcomEventTypeId, setCalcomEventTypeId] = useState("");
  const [calcomApiKey, setCalcomApiKey] = useState("");
  const [voiceId, setVoiceId] = useState("11labs-Adrian");

  // UI state
  const [activeLogTab, setActiveLogTab] = useState<"all" | "appointments">("all");
  const [expandedCallId, setExpandedCallId] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [simScenario, setSimScenario] = useState<
    "appointment_booking" | "faq_inquiry" | "emergency_transfer"
  >("appointment_booking");
  const [simCallerName, setSimCallerName] = useState("Sarah Jenkins");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // 1-Click RAG Knowledge Base states
  const [knowledgeDocs, setKnowledgeDocs] = useState<KnowledgeDocumentItem[]>([]);
  const [crawlUrl, setCrawlUrl] = useState("");
  const [indexingUrl, setIndexingUrl] = useState(false);
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const [ragQuery, setRagQuery] = useState("");
  const [searchingRag, setSearchingRag] = useState(false);
  const [ragMatches, setRagMatches] = useState<KnowledgeSearchMatch[]>([]);
  const [remindingCallId, setRemindingCallId] = useState<string | null>(null);

  const hydrateFormFromConfig = useCallback((cfg: ReceptionistConfig, fallbackTenantName?: string) => {
    setBusinessName(cfg.business_name || fallbackTenantName || "");
    setOperatingHours(cfg.operating_hours || "Mon-Fri 9:00 AM - 6:00 PM");
    setFallbackPhone(cfg.fallback_phone_number || "");
    setGreetingMessage(
      cfg.greeting_message ||
        `Hello! Thank you for calling ${cfg.business_name || fallbackTenantName || "our office"}. How can I help you today?`
    );
    setFaqsKnowledgeBase(cfg.faqs_knowledge_base || "");
    setCalcomBookingUrl(cfg.calcom_booking_url || "");
    setCalcomEventTypeId(cfg.calcom_event_type_id || "");
    setVoiceId(cfg.voice_id || "11labs-Adrian");
    setCalcomApiKey("");
  }, []);

  const loadReceptionistData = useCallback(async () => {
    setErrorMessage(null);
    let currentTenant = getActiveTenant();
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
      } else {
        window.location.href = "/onboarding";
        return;
      }
    }

    const [cfgRes, callsRes, docsRes] = await Promise.all([
      apiRequest("/api/v1/receptionist/config"),
      apiRequest("/api/v1/receptionist/calls?limit=100"),
      apiRequest<KnowledgeDocumentItem[]>("/api/v1/knowledge/documents"),
    ]);
    if (docsRes.success && Array.isArray(docsRes.data)) {
      setKnowledgeDocs(docsRes.data);
    }

    setPaymentApproved(Boolean(cfgRes.payment_approved));
    setHasSubscription(Boolean(cfgRes.has_subscription));
    if (cfgRes.success && cfgRes.data) {
      setConfig(cfgRes.data);
      hydrateFormFromConfig(cfgRes.data, currentTenant?.name);
    } else {
      setConfig(null);
      if (currentTenant?.name && !businessName) {
        setBusinessName(currentTenant.name);
        setGreetingMessage(
          `Hello! Thank you for calling ${currentTenant.name}. I'm your AI receptionist — how may I help you today?`
        );
      }
    }

    if (callsRes.success && callsRes.data) {
      setCalls(callsRes.data.calls || []);
      setBookedAppointments(callsRes.data.booked_appointments || []);
      setSummary(
        callsRes.data.summary || {
          total_calls: 0,
          appointments_booked: 0,
          human_transfers: 0,
          avg_duration_seconds: 0,
        }
      );
    }

    setLoading(false);
  }, [businessName, hydrateFormFromConfig]);

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    loadReceptionistData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCopyText = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    } catch {
      setStatusMessage(`Copied value: ${text}`);
    }
  };

  const handleIngestUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!crawlUrl.trim()) return;
    setIndexingUrl(true);
    setErrorMessage(null);
    try {
      const res = await apiRequest<KnowledgeDocumentItem>("/api/v1/knowledge/ingest/url", {
        method: "POST",
        body: JSON.stringify({ url: crawlUrl.trim() }),
      });
      if (res.success && res.data) {
        setCrawlUrl("");
        setStatusMessage(`Indexed "${res.data.title}" (${res.data.chunk_count} RAG chunks) cleanly.`);
        await loadReceptionistData();
      } else {
        setErrorMessage(res.error?.message || "Failed to index website URL.");
      }
    } finally {
      setIndexingUrl(false);
    }
  };

  const handleUploadPdf = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingPdf(true);
    setErrorMessage(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", file.name);
      const rawRes = await apiFetchResponse("/api/v1/knowledge/ingest/pdf", {
        method: "POST",
        body: formData,
      });
      const parsed = await rawRes.json();
      if (rawRes.ok && parsed?.success && parsed?.data) {
        setStatusMessage(
          `PDF "${parsed.data.title}" indexed into ${parsed.data.chunk_count} vector chunks.`
        );
        await loadReceptionistData();
      } else {
        setErrorMessage(parsed?.error?.message || parsed?.detail || "Failed to index PDF file.");
      }
    } catch (err: any) {
      setErrorMessage(err?.message || "PDF upload failed.");
    } finally {
      e.target.value = "";
      setUploadingPdf(false);
    }
  };

  const handleDeleteKnowledgeDoc = async (docId: string) => {
    const res = await apiRequest(`/api/v1/knowledge/documents/${docId}`, { method: "DELETE" });
    if (res.success) {
      setKnowledgeDocs((prev) => prev.filter((d) => d.id !== docId));
    }
  };

  const handleSearchRag = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ragQuery.trim()) return;
    setSearchingRag(true);
    try {
      const res = await apiRequest<KnowledgeSearchMatch[]>("/api/v1/knowledge/search", {
        method: "POST",
        body: JSON.stringify({ query: ragQuery.trim(), top_k: 3 }),
      });
      if (res.success && Array.isArray(res.data)) {
        setRagMatches(res.data);
      }
    } finally {
      setSearchingRag(false);
    }
  };

  const handleTriggerReminder = async (callLogId: string) => {
    setRemindingCallId(callLogId);
    setErrorMessage(null);
    try {
      const res = await apiRequest(`/api/v1/receptionist/appointments/${callLogId}/trigger-reminder`, {
        method: "POST",
      });
      if (res.success) {
        setStatusMessage("WhatsApp Confirm/Reschedule reminder sent to attendee.");
        await loadReceptionistData();
      } else {
        setErrorMessage(res.error?.message || "Could not dispatch WhatsApp reminder.");
      }
    } finally {
      setRemindingCallId(null);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setStatusMessage(null);

    if (!businessName.trim() || !fallbackPhone.trim()) {
      setErrorMessage("Business Name and Personal / Fallback Phone Number are required.");
      return;
    }

    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        business_name: businessName.trim(),
        operating_hours: operatingHours.trim() || "Mon-Fri 9:00 AM - 6:00 PM",
        fallback_phone_number: fallbackPhone.trim(),
        greeting_message: greetingMessage.trim(),
        faqs_knowledge_base: faqsKnowledgeBase.trim(),
        calcom_booking_url: calcomBookingUrl.trim() || null,
        calcom_event_type_id: calcomEventTypeId.trim() || null,
        voice_id: voiceId,
        auto_provision: true,
      };
      if (calcomApiKey.trim()) {
        payload.calcom_api_key = calcomApiKey.trim();
      }

      const res = await apiRequest("/api/v1/receptionist/config", {
        method: "PUT",
        body: JSON.stringify(payload),
      });

      if (res.success && res.data) {
        setConfig(res.data);
        hydrateFormFromConfig(res.data);
        if (typeof res.payment_approved === "boolean") {
          setPaymentApproved(res.payment_approved);
        }
        if (typeof res.has_subscription === "boolean") {
          setHasSubscription(res.has_subscription);
        }
        setStatusMessage(
          res.data.provisioning_status === "awaiting_payment"
            ? "Office Receptionist draft saved! Complete your bank transfer payment on the Dashboard to unlock your live Telnyx AI phone number and Retell AI voice agent."
            : "Office Receptionist settings, FAQs, and Cal.com tools saved and synced to your AI Voice Agent!"
        );
      } else {
        setErrorMessage(
          res.error?.message || res.message || "Failed to save Office Receptionist configuration."
        );
      }
    } finally {
      setSaving(false);
    }
  };

  const handleQuickSyncFaqs = async () => {
    if (!config) return;
    setErrorMessage(null);
    setStatusMessage(null);
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        faqs_knowledge_base: faqsKnowledgeBase.trim(),
        greeting_message: greetingMessage.trim(),
        operating_hours: operatingHours.trim(),
        fallback_phone_number: fallbackPhone.trim(),
        calcom_booking_url: calcomBookingUrl.trim() || null,
        calcom_event_type_id: calcomEventTypeId.trim() || null,
      };
      if (calcomApiKey.trim()) {
        payload.calcom_api_key = calcomApiKey.trim();
      }

      const res = await apiRequest("/api/v1/receptionist/faqs", {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      if (res.success && res.data) {
        setConfig(res.data);
        hydrateFormFromConfig(res.data);
        setStatusMessage("FAQs & Knowledge Base updated and pushed live to Retell AI!");
      } else {
        setErrorMessage(res.error?.message || "Could not update FAQs.");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleProvisionVoiceStack = async () => {
    setErrorMessage(null);
    setStatusMessage(null);
    setProvisioning(true);
    try {
      const res = await apiRequest("/api/v1/receptionist/provision", { method: "POST" });
      if (res.success && res.data) {
        setConfig(res.data);
        hydrateFormFromConfig(res.data);
        setStatusMessage(
          "Telnyx phone number, TeXML Voice Webhooks, and Retell AI Voice Agent synced successfully."
        );
      } else {
        setErrorMessage(res.error?.message || "Failed to provision voice agent.");
      }
    } finally {
      setProvisioning(false);
    }
  };

  const handleSimulateCall = async () => {
    if (!config) {
      setErrorMessage("Please save your Office Receptionist setup below before running a test call.");
      return;
    }
    setErrorMessage(null);
    setStatusMessage(null);
    setSimulating(true);
    try {
      const res = await apiRequest("/api/v1/receptionist/calls/simulate", {
        method: "POST",
        body: JSON.stringify({
          caller_name: simCallerName.trim() || "Sarah Jenkins",
          caller_phone: "+14155550199",
          scenario: simScenario,
        }),
      });
      if (res.success) {
        setStatusMessage(res.message || "Simulated AI voice call logged cleanly.");
        await loadReceptionistData();
      } else {
        setErrorMessage(res.error?.message || "Failed to simulate test call.");
      }
    } finally {
      setSimulating(false);
    }
  };

  const guide = config?.call_forwarding_guide;
  const displayedLogs = activeLogTab === "appointments" ? bookedAppointments : calls;

  const statusBadge =
    config?.provisioning_status === "active"
      ? {
          label: "Live AI Voice Receptionist",
          cls: "bg-emerald-50 text-emerald-700 border-emerald-200",
        }
      : config?.provisioning_status === "awaiting_payment"
      ? {
          label: "Draft Saved — Awaiting Payment Approval",
          cls: "bg-amber-50 text-amber-700 border-amber-200",
        }
      : config?.provisioning_status === "sandbox_ready"
      ? {
          label: "Sandbox Ready (Awaiting Master Voice Keys)",
          cls: "bg-amber-50 text-amber-700 border-amber-200",
        }
      : {
          label: "Setup Needed",
          cls: "bg-slate-100 text-slate-600 border-slate-200",
        };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <Navbar />
      <div className="flex">
        <Sidebar currentPath="/receptionist" />
        <main className="flex-1 p-4 sm:p-6 lg:p-8 space-y-6 max-w-7xl mx-auto w-full">
          {/* Header Banner */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-sm flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-sm">
                  <PhoneCall className="h-5 w-5" />
                </div>
                <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">
                  Office Receptionist (AI Voice Agent)
                </h1>
                <span
                  className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statusBadge.cls}`}
                >
                  {statusBadge.label}
                </span>
              </div>
              <p className="text-sm text-slate-500">
                24/7 Retell AI + Telnyx phone answering, live Cal.com appointment scheduling, and
                instant human call transfers to your fallback number.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleProvisionVoiceStack}
                disabled={provisioning || !paymentApproved || !hasSubscription}
                title={
                  !paymentApproved
                    ? "Unlocks after Admin approves your bank transfer payment"
                    : !hasSubscription
                    ? "Subscribe to Office Receptionist in Onboarding or Billing first"
                    : "Provision or re-sync Telnyx + Retell AI voice agent"
                }
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-emerald-500 disabled:opacity-50 transition"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${provisioning ? "animate-spin" : ""}`} />
                <span>{provisioning ? "Syncing Voice Stack..." : "Provision / Sync Voice Agent"}</span>
              </button>
              <a
                href="/onboarding"
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
              >
                <Sparkles className="h-3.5 w-3.5 text-emerald-600" />
                <span>Onboarding Wizard</span>
              </a>
            </div>
          </div>

          {errorMessage && (
            <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {statusMessage && (
            <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
              <span>{statusMessage}</span>
            </div>
          )}

          {!loading && !paymentApproved && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="space-y-1">
                <p className="text-sm font-bold text-amber-900">
                  Payment Approval Required to Activate Live Voice Line
                </p>
                <p className="text-xs text-amber-800 leading-relaxed">
                  Save or edit your Office Receptionist draft below anytime. Live Telnyx number
                  provisioning, Retell AI voice calls, and test simulations unlock automatically once
                  Admin confirms your bank transfer payment.
                </p>
              </div>
              <a
                href="/dashboard"
                className="shrink-0 inline-flex items-center justify-center rounded-lg bg-amber-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-amber-500 transition"
              >
                View Bank Details &amp; Submit Payment →
              </a>
            </div>
          )}

          {/* Assigned Phone & Retell Agent Identity Strip */}
          {config && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
                    Assigned Telnyx AI Number
                  </p>
                  <p className="text-lg font-bold font-mono text-slate-900 mt-0.5">
                    {config.telnyx_phone_number || "Pending Assignment"}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Forward your office line here for 24/7 AI coverage
                  </p>
                </div>
                {config.telnyx_phone_number && (
                  <button
                    type="button"
                    onClick={() => handleCopyText("ai-num", config.telnyx_phone_number!)}
                    className="rounded-lg border border-emerald-200 bg-white p-2 text-emerald-700 hover:bg-emerald-100 transition"
                    title="Copy assigned Telnyx AI number"
                  >
                    {copiedKey === "ai-num" ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </button>
                )}
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  Retell AI Agent ID
                </p>
                <p className="text-sm font-bold font-mono text-slate-900 mt-1 truncate">
                  {config.retell_agent_id || "Pending Creation"}
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Voice: <span className="font-mono">{config.voice_id}</span>
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  Emergency / Human Transfer Number
                </p>
                <p className="text-lg font-bold font-mono text-slate-900 mt-0.5">
                  {config.fallback_phone_number}
                </p>
                <p className="text-[11px] text-slate-500">
                  Instant live call transfer when caller asks for staff
                </p>
              </div>
            </div>
          )}

          {/* 4 KPI Stat Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Total Calls Handled"
              value={summary.total_calls}
              subtext="Inbound calls answered by AI"
              icon={PhoneIncoming}
              badge={{ text: "24/7 Active", variant: "success" }}
            />
            <StatCard
              title="Appointments Booked"
              value={summary.appointments_booked}
              subtext="Scheduled directly into Cal.com"
              icon={CalendarCheck2}
              badge={{
                text: config?.calcom_booking_url ? "Cal.com Linked" : "Setup Cal.com",
                variant: config?.calcom_booking_url ? "success" : "warning",
              }}
            />
            <StatCard
              title="Live Human Transfers"
              value={summary.human_transfers}
              subtext="Emergency / staff escalations"
              icon={PhoneForwarded}
              badge={{ text: "Fallback Active", variant: "neutral" }}
            />
            <StatCard
              title="Avg Call Duration"
              value={formatDuration(summary.avg_duration_seconds)}
              subtext="Average AI conversation time"
              icon={Clock}
            />
          </div>

          {config?.provisioning_notes && (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-600 shrink-0" />
              <span>
                <strong>Sync Details:</strong> {config.provisioning_notes}
              </span>
            </div>
          )}

          {/* Call Forwarding Setup Guide */}
          {guide?.assigned_ai_number && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-100 pb-3">
                <div>
                  <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <PhoneForwarded className="h-4 w-4 text-emerald-600" />
                    Call Forwarding Setup Guide
                  </h2>
                  <p className="text-xs text-slate-500">
                    Forward calls from your existing business phone ({guide.fallback_human_number}) to
                    your assigned Telnyx AI number ({guide.assigned_ai_number}).
                  </p>
                </div>
              </div>

              {guide.quick_dial_codes && (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  {[
                    {
                      key: "all",
                      label: "Forward All Calls (GSM)",
                      code: guide.quick_dial_codes.forward_all_calls_gsm,
                    },
                    {
                      key: "unanswered",
                      label: "Forward Missed Calls Only",
                      code: guide.quick_dial_codes.forward_when_unanswered_gsm,
                    },
                    {
                      key: "verizon",
                      label: "US Verizon Forward All",
                      code: guide.quick_dial_codes.us_verizon_forward_all,
                    },
                    {
                      key: "disable",
                      label: "Turn Off Forwarding",
                      code: guide.quick_dial_codes.disable_forwarding_gsm,
                    },
                  ]
                    .filter((item) => Boolean(item.code))
                    .map((item) => (
                      <div
                        key={item.key}
                        className="rounded-xl border border-slate-200 bg-slate-50 p-3 flex items-center justify-between gap-2"
                      >
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                            {item.label}
                          </p>
                          <p className="font-mono text-sm font-bold text-slate-900 mt-0.5">
                            {item.code}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleCopyText(item.key, item.code!)}
                          className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-600 hover:text-emerald-700 hover:border-emerald-300 transition"
                          title="Copy dial code"
                        >
                          {copiedKey === item.key ? (
                            <Check className="h-3.5 w-3.5 text-emerald-600" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </div>
                    ))}
                </div>
              )}

              {Array.isArray(guide.steps) && guide.steps.length > 0 && (
                <ol className="space-y-1.5 text-xs text-slate-700 bg-slate-50 rounded-xl p-4 border border-slate-100">
                  {guide.steps.map((stepText, idx) => (
                    <li key={idx} className="leading-relaxed">
                      {stepText}
                    </li>
                  ))}
                </ol>
              )}

              {guide.ios_android_menu_tip && (
                <p className="text-xs text-slate-500 bg-emerald-50/60 border border-emerald-100 rounded-lg px-3.5 py-2.5">
                  <strong className="text-emerald-800">Phone Menu Shortcut:</strong>{" "}
                  {guide.ios_android_menu_tip}
                </p>
              )}
            </div>
          )}

          {/* Main Grid: FAQs & Settings Editor + Call Logs / Appointments */}
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
            {/* Left Column: FAQs, Greeting & Cal.com Settings */}
            <div className="xl:col-span-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-sm space-y-4">
              <div className="border-b border-slate-100 pb-3">
                <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <FileText className="h-4 w-4 text-emerald-600" />
                  Receptionist Script, FAQs &amp; Cal.com Settings
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Update your business hours, FAQs, greeting, transfer phone, or Cal.com booking
                  details anytime. Saving immediately re-syncs your Retell AI agent.
                </p>
              </div>

              <form onSubmit={handleSaveConfig} className="space-y-3.5 text-xs">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    Business Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={businessName}
                    onChange={(e) => setBusinessName(e.target.value)}
                    placeholder="e.g. Al Noor Dental Clinic"
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">
                      Operating Hours *
                    </label>
                    <input
                      type="text"
                      required
                      value={operatingHours}
                      onChange={(e) => setOperatingHours(e.target.value)}
                      placeholder="Mon-Fri 9:00 AM - 6:00 PM"
                      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">
                      Personal / Fallback Phone *
                    </label>
                    <input
                      type="tel"
                      required
                      value={fallbackPhone}
                      onChange={(e) => setFallbackPhone(e.target.value)}
                      placeholder="+14155550100"
                      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-mono text-slate-900 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    AI Voice Persona
                  </label>
                  <select
                    value={voiceId}
                    onChange={(e) => setVoiceId(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none"
                  >
                    <option value="11labs-Adrian">Adrian (Professional Warm Male)</option>
                    <option value="11labs-Myra">Myra (Friendly Concierge Female)</option>
                    <option value="openai-Alloy">Alloy (Neutral Modern)</option>
                    <option value="openai-Nova">Nova (Upbeat Receptionist)</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    Custom Greeting Message
                  </label>
                  <textarea
                    rows={2}
                    value={greetingMessage}
                    onChange={(e) => setGreetingMessage(e.target.value)}
                    placeholder="Hello! Thank you for calling..."
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    FAQs &amp; Business Knowledge Base
                  </label>
                  <textarea
                    rows={5}
                    value={faqsKnowledgeBase}
                    onChange={(e) => setFaqsKnowledgeBase(e.target.value)}
                    placeholder={
                      "Q: Where are you located?\nA: 120 Main St, Suite 400 (free parking behind building).\n\nQ: Do you accept walk-ins?\nA: Yes, though booking via Cal.com guarantees zero wait time."
                    }
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none leading-relaxed"
                  />
                </div>

                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-800 flex items-center gap-1.5">
                      <CalendarCheck2 className="h-3.5 w-3.5 text-emerald-600" />
                      Cal.com Live Appointment Booking (Private Account)
                    </span>
                    {config?.calcom_api_key_configured && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                        <KeyRound className="h-2.5 w-2.5" /> API Key Encrypted
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-600 leading-relaxed">
                    For live automated Cal.com bookings (100% private to your calendar), create a
                    free Cal.com account and enter both your Event Type ID and API Key. If left
                    blank, appointments are logged inside your Teloxtech dashboard for manual
                    follow-up.
                  </p>

                  <div>
                    <label className="block text-[11px] font-medium text-slate-600 mb-1">
                      Cal.com Booking Link
                    </label>
                    <input
                      type="url"
                      value={calcomBookingUrl}
                      onChange={(e) => setCalcomBookingUrl(e.target.value)}
                      placeholder="https://cal.com/your-business/consultation"
                      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    <div>
                      <label className="block text-[11px] font-medium text-slate-600 mb-1">
                        Event Type ID (for live sync)
                      </label>
                      <input
                        type="text"
                        value={calcomEventTypeId}
                        onChange={(e) => setCalcomEventTypeId(e.target.value)}
                        placeholder="e.g. 123456"
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-mono text-slate-900 focus:border-emerald-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-slate-600 mb-1">
                        Cal.com API Key (encrypted)
                      </label>
                      <input
                        type="password"
                        value={calcomApiKey}
                        onChange={(e) => setCalcomApiKey(e.target.value)}
                        placeholder={
                          config?.calcom_api_key_configured
                            ? "•••••••• (leave blank to keep)"
                            : "cal_live_..."
                        }
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-mono text-slate-900 focus:border-emerald-500 focus:outline-none"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 pt-2">
                  <button
                    type="submit"
                    disabled={saving}
                    className="flex-1 rounded-lg bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-emerald-500 disabled:opacity-50 transition"
                  >
                    {saving
                      ? "Saving & Syncing..."
                      : !paymentApproved
                      ? "Save Receptionist Draft (Unlocks After Payment)"
                      : config
                      ? "Save Settings & Re-Sync AI Agent"
                      : "Activate & Provision Office Receptionist"}
                  </button>
                  {config && (
                    <button
                      type="button"
                      disabled={saving}
                      onClick={handleQuickSyncFaqs}
                      className="rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition"
                    >
                      Quick-Update FAQs
                    </button>
                  )}
                </div>
              </form>
            </div>

            {/* Right Column: 1-Click RAG Knowledge Base, Call Logs, Booked Appointments & Test Simulator */}
            <div className="xl:col-span-7 space-y-4">
              {/* 1-Click RAG Knowledge Base */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                      <FileText className="h-4 w-4 text-emerald-600" />
                      1-Click RAG Knowledge Base (Retell AI &amp; WhatsApp)
                    </h3>
                    <p className="text-xs text-slate-500">
                      Paste your business URL or upload PDF brochures/menus so AI answers with exact facts.
                    </p>
                  </div>
                  <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-bold text-emerald-800">
                    {knowledgeDocs.length} Indexed
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
                  <form onSubmit={handleIngestUrl} className="md:col-span-2 flex gap-2">
                    <div className="relative flex-1">
                      <Globe className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-2.5" />
                      <input
                        type="url"
                        value={crawlUrl}
                        onChange={(e) => setCrawlUrl(e.target.value)}
                        placeholder="https://yourbusiness.com/services"
                        className="w-full rounded-lg border border-slate-300 pl-8 pr-3 py-2 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={indexingUrl || !crawlUrl.trim()}
                      className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 transition shrink-0"
                    >
                      {indexingUrl ? "Indexing..." : "Index URL"}
                    </button>
                  </form>

                  <label className="flex items-center justify-center gap-1.5 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-emerald-500 cursor-pointer transition">
                    <Upload className="h-3.5 w-3.5 text-emerald-600" />
                    <span>{uploadingPdf ? "Uploading PDF..." : "Upload PDF"}</span>
                    <input
                      type="file"
                      accept="application/pdf,.pdf"
                      onChange={handleUploadPdf}
                      disabled={uploadingPdf}
                      className="hidden"
                    />
                  </label>
                </div>

                {knowledgeDocs.length > 0 && (
                  <div className="space-y-1.5 max-h-36 overflow-y-auto">
                    {knowledgeDocs.map((doc) => (
                      <div
                        key={doc.id}
                        className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs"
                      >
                        <div className="min-w-0 pr-2">
                          <span className="font-semibold text-slate-900 truncate block">{doc.title}</span>
                          <span className="text-[10px] text-slate-500 uppercase">
                            {doc.source_type} • {doc.chunk_count} chunks
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleDeleteKnowledgeDoc(doc.id)}
                          className="text-slate-400 hover:text-red-600 p-1"
                          title="Delete document"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <form onSubmit={handleSearchRag} className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      value={ragQuery}
                      onChange={(e) => setRagQuery(e.target.value)}
                      placeholder="Test AI knowledge retrieval (e.g. pricing or consultation hours)..."
                      className="w-full rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-3 py-1.5 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={searchingRag || !ragQuery.trim()}
                    className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  >
                    {searchingRag ? "Searching..." : "Test Search"}
                  </button>
                </form>

                {ragMatches.length > 0 && (
                  <div className="space-y-1.5">
                    {ragMatches.map((m) => (
                      <div
                        key={m.chunk_id}
                        className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-2.5 text-[11px] text-slate-700"
                      >
                        <div className="font-bold text-emerald-900 mb-0.5">
                          {m.document_title} (Score: {(m.score * 100).toFixed(0)}%)
                        </div>
                        <p className="line-clamp-2">{m.content}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Interactive Test Call Simulator */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                      <Play className="h-4 w-4 text-emerald-600" />
                      Test Call Simulator
                    </h3>
                    <p className="text-xs text-slate-500">
                      Verify Cal.com booking flow, FAQ responses, or emergency live human transfer
                      in one click.
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                  <input
                    type="text"
                    value={simCallerName}
                    onChange={(e) => setSimCallerName(e.target.value)}
                    placeholder="Caller Name"
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none"
                  />
                  <select
                    value={simScenario}
                    onChange={(e) =>
                      setSimScenario(
                        e.target.value as
                          | "appointment_booking"
                          | "faq_inquiry"
                          | "emergency_transfer"
                      )
                    }
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none"
                  >
                    <option value="appointment_booking">Cal.com Appointment Booking</option>
                    <option value="faq_inquiry">FAQ / Business Hours Inquiry</option>
                    <option value="emergency_transfer">Emergency Live Human Transfer</option>
                  </select>
                  <button
                    type="button"
                    disabled={simulating || !config || !paymentApproved}
                    title={
                      !paymentApproved
                        ? "Test call simulator unlocks after payment approval"
                        : "Run test call simulation"
                    }
                    onClick={handleSimulateCall}
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50 transition"
                  >
                    <Play className="h-3.5 w-3.5 text-emerald-400" />
                    <span>{simulating ? "Simulating..." : "Run Test Call"}</span>
                  </button>
                </div>
              </div>

              {/* Call Logs & Booked Appointments Panel */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setActiveLogTab("all")}
                      className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                        activeLogTab === "all"
                          ? "bg-emerald-600 text-white"
                          : "bg-slate-100 text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      All Call Logs ({calls.length})
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveLogTab("appointments")}
                      className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                        activeLogTab === "appointments"
                          ? "bg-emerald-600 text-white"
                          : "bg-slate-100 text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      Booked Appointments ({bookedAppointments.length})
                    </button>
                  </div>

                  {config?.calcom_booking_url && (
                    <a
                      href={config.calcom_booking_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:underline"
                    >
                      <span>Open Cal.com Calendar</span>
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>

                {loading ? (
                  <p className="text-sm text-slate-500 py-8 text-center">
                    Loading Office Receptionist activity...
                  </p>
                ) : displayedLogs.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center space-y-2">
                    <PhoneCall className="h-8 w-8 text-slate-400 mx-auto" />
                    <p className="text-sm font-semibold text-slate-700">
                      {activeLogTab === "appointments"
                        ? "No Cal.com appointments booked via voice yet"
                        : "No calls logged yet"}
                    </p>
                    <p className="text-xs text-slate-500 max-w-md mx-auto">
                      Once your office line forwards to your assigned Telnyx AI number — or when
                      you click &ldquo;Run Test Call&rdquo; above — call summaries, transcripts, and
                      booked appointments will appear here in real time.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {displayedLogs.map((log) => {
                      const isExpanded = expandedCallId === log.id;
                      return (
                        <div
                          key={log.id}
                          className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-2"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-sm font-bold text-slate-900">
                                  {log.caller_name || "Inbound Caller"}
                                </span>
                                <span className="font-mono text-xs text-slate-500">
                                  {log.caller_phone}
                                </span>
                                <span className="rounded-full bg-slate-200/80 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                                  {formatDuration(log.duration_seconds)}
                                </span>
                              </div>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                {new Date(log.created_at).toLocaleString()}
                              </p>
                            </div>

                            <div className="flex flex-wrap items-center gap-1.5">
                              {log.lead_tier && (
                                <span
                                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                                    log.lead_tier === "hot"
                                      ? "bg-rose-100 text-rose-800 border border-rose-200"
                                      : log.lead_tier === "warm"
                                      ? "bg-amber-100 text-amber-800 border border-amber-200"
                                      : "bg-slate-200 text-slate-700"
                                  }`}
                                >
                                  {log.lead_tier} ({log.lead_score ?? 0})
                                </span>
                              )}
                              {log.sentiment && (
                                <span className="rounded-full bg-slate-100 border border-slate-200 px-2 py-0.5 text-[10px] font-semibold capitalize text-slate-700">
                                  {log.sentiment}
                                </span>
                              )}
                              {(log.booking_status === "booked" || log.booking_status === "confirmed") && (
                                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 border border-emerald-200 px-2.5 py-0.5 text-[10px] font-bold text-emerald-800">
                                  <CalendarCheck2 className="h-3 w-3" />
                                  {log.booking_status === "confirmed" ? "Confirmed" : "Booked"}
                                </span>
                              )}
                              {log.booking_status === "booked" && (
                                <button
                                  type="button"
                                  disabled={remindingCallId === log.id}
                                  onClick={() => handleTriggerReminder(log.id)}
                                  className="inline-flex items-center gap-1 rounded-full border border-emerald-300 bg-white px-2.5 py-0.5 text-[10px] font-semibold text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                                >
                                  <BellRing className="h-3 w-3" />
                                  <span>
                                    {remindingCallId === log.id
                                      ? "Sending..."
                                      : log.reminder_sent_at
                                      ? "Resend Reminder"
                                      : "No-Show Reminder"}
                                  </span>
                                </button>
                              )}
                              {log.transferred_to_human && (
                                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 border border-amber-200 px-2.5 py-0.5 text-[10px] font-bold text-amber-800">
                                  <PhoneForwarded className="h-3 w-3" />
                                  Transferred to Human
                                </span>
                              )}
                              <span className="rounded-full bg-white border border-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-600">
                                {log.status}
                              </span>
                            </div>
                          </div>

                          {log.summary && (
                            <p className="text-xs text-slate-700 leading-relaxed">{log.summary}</p>
                          )}

                          {log.booked_appointment_at && (
                            <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-900 flex flex-wrap items-center justify-between gap-2">
                              <span>
                                <strong>Appointment:</strong>{" "}
                                {new Date(log.booked_appointment_at).toLocaleString()}
                              </span>
                              {log.calcom_booking_uid && (
                                <span className="font-mono text-[11px] text-emerald-700">
                                  Ref: {log.calcom_booking_uid}
                                </span>
                              )}
                            </div>
                          )}

                          {log.transcript && (
                            <div className="pt-1">
                              <button
                                type="button"
                                onClick={() => setExpandedCallId(isExpanded ? null : log.id)}
                                className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 hover:text-emerald-800"
                              >
                                {isExpanded ? (
                                  <>
                                    <ChevronUp className="h-3.5 w-3.5" />
                                    Hide Call Transcript
                                  </>
                                ) : (
                                  <>
                                    <ChevronDown className="h-3.5 w-3.5" />
                                    View Call Transcript
                                  </>
                                )}
                              </button>
                              {isExpanded && (
                                <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-900 text-slate-100 p-3 text-[11px] font-mono leading-relaxed">
                                  {log.transcript}
                                </pre>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
