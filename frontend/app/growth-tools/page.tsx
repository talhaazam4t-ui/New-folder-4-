"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { Sidebar } from "@/components/shared/Sidebar";
import { apiFetchResponse, apiRequest, getBackendUrl } from "@/lib/api";
import { getActiveTenant, getAuthToken } from "@/lib/auth";
import {
  Zap,
  Instagram,
  Star,
  ScanText,
  FileDown,
  Plus,
  Trash2,
  Send,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  ShieldAlert,
  ExternalLink,
  Copy,
  Check,
} from "lucide-react";

interface CommentRule {
  id: string;
  platform: string;
  keyword: string;
  post_id: string | null;
  dm_template: string;
  booking_url: string | null;
  is_active: boolean;
  trigger_count: number;
}

interface DmLogItem {
  id: string;
  platform: string;
  commenter_name: string | null;
  comment_text: string;
  matched_keyword: string | null;
  dm_text: string;
  booking_link: string | null;
  status: string;
  created_at: string | null;
}

interface ReviewRequestItem {
  id: string;
  customer_name: string | null;
  customer_phone: string;
  rating: number | null;
  status: string;
  routing_target: string | null;
  private_feedback: string | null;
  google_review_url: string | null;
  feedback_token: string;
  sent_at: string | null;
}

interface ExtractionItem {
  id: string;
  document_type: string;
  source_channel: string;
  sender_name: string | null;
  sender_phone: string | null;
  raw_summary: string | null;
  extracted_data: Record<string, any>;
  confidence: number;
  status: string;
  approval_id: string | null;
  created_at: string | null;
}

async function triggerBlobDownload(resp: Response, fallbackName: string): Promise<void> {
  if (!resp.ok) {
    throw new Error(`PDF download failed (${resp.status})`);
  }
  const blob = await resp.blob();
  const disp = resp.headers.get("content-disposition") || "";
  const match = disp.match(/filename="?([^"]+)"?/i);
  const filename = match ? match[1] : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function GrowthToolsPage() {
  const [activeTab, setActiveTab] = useState<"social_dm" | "reviews" | "ocr_pdf">("social_dm");
  const [loading, setLoading] = useState(true);
  const [banner, setBanner] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [copiedWebhook, setCopiedWebhook] = useState(false);

  // Tab 1: IG & FB Comment-to-DM
  const [rules, setRules] = useState<CommentRule[]>([]);
  const [dmLogs, setDmLogs] = useState<DmLogItem[]>([]);
  const [metaConnected, setMetaConnected] = useState(false);
  const [metaPageId, setMetaPageId] = useState("");
  const [metaIgId, setMetaIgId] = useState("");
  const [metaToken, setMetaToken] = useState("");
  const [newPlatform, setNewPlatform] = useState<"both" | "instagram" | "facebook">("both");
  const [newKeyword, setNewKeyword] = useState("PRICE");
  const [newDmTemplate, setNewDmTemplate] = useState(
    "Thanks for reaching out! Here is our instant booking link and pricing overview:"
  );
  const [newBookingUrl, setNewBookingUrl] = useState("");
  const [simCommentText, setSimCommentText] = useState("Hi please send PRICE and booking info");
  const [simCommenterName, setSimCommenterName] = useState("Amina Khan");

  // Tab 2: Google Review Booster
  const [rbEnabled, setRbEnabled] = useState(true);
  const [rbGoogleUrl, setRbGoogleUrl] = useState("");
  const [rbDelayMins, setRbDelayMins] = useState("60");
  const [reviewStats, setReviewStats] = useState({
    total_sent: 0,
    responded_count: 0,
    average_rating: 0,
    google_routed_count: 0,
    private_intercepted_count: 0,
  });
  const [reviewRows, setReviewRows] = useState<ReviewRequestItem[]>([]);
  const [promptPhone, setPromptPhone] = useState("+923001234567");
  const [promptName, setPromptName] = useState("Walk-In Patient");

  // Tab 3: Vision OCR & Auto-PDF
  const [extractions, setExtractions] = useState<ExtractionItem[]>([]);
  const [ocrFile, setOcrFile] = useState<File | null>(null);
  const [ocrCaption, setOcrCaption] = useState("");
  const [ocrPhone, setOcrPhone] = useState("");
  const [ocrBusy, setOcrBusy] = useState(false);

  const [pdfDocType, setPdfDocType] = useState("quote");
  const [pdfTitle, setPdfTitle] = useState("Dental Treatment Plan & Quote");
  const [pdfRecipient, setPdfRecipient] = useState("Sarah Jenkins");
  const [pdfItemDesc, setPdfItemDesc] = useState("AI Receptionist & CRM Monthly Plan");
  const [pdfItemQty, setPdfItemQty] = useState("1");
  const [pdfItemPrice, setPdfItemPrice] = useState("27500");
  const [pdfNotes, setPdfNotes] = useState("Valid for 14 days. Generated natively by TaloxTech.");
  const [pdfBusy, setPdfBusy] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [rulesRes, logsRes, rbCfgRes, rbReqRes, ocrRes, ckRes] = await Promise.all([
        apiRequest<CommentRule[]>("/api/v1/growth/comment-dm/rules"),
        apiRequest<DmLogItem[]>("/api/v1/growth/comment-dm/logs"),
        apiRequest<any>("/api/v1/growth/reviews/config"),
        apiRequest<any>("/api/v1/growth/reviews/requests"),
        apiRequest<ExtractionItem[]>("/api/v1/growth/ocr/extractions"),
        apiRequest<any>("/api/v1/integrations/handshake-checklist"),
      ]);
      if (Array.isArray(rulesRes.data)) setRules(rulesRes.data);
      if (Array.isArray(logsRes.data)) setDmLogs(logsRes.data);
      if (rbCfgRes.data) {
        setRbEnabled(Boolean(rbCfgRes.data.enabled));
        setRbGoogleUrl(rbCfgRes.data.google_review_url || "");
        setRbDelayMins(String(rbCfgRes.data.delay_minutes ?? 60));
      }
      if (rbReqRes.data) {
        if (rbReqRes.data.stats) setReviewStats(rbReqRes.data.stats);
        if (Array.isArray(rbReqRes.data.requests)) setReviewRows(rbReqRes.data.requests);
      }
      if (Array.isArray(ocrRes.data)) setExtractions(ocrRes.data);
      const ckItems: any[] = ckRes.data?.items || [];
      const metaItem = ckItems.find((i) => i.key === "meta_social");
      setMetaConnected(metaItem?.status === "connected");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = getAuthToken();
    const tenant = getActiveTenant();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    if (!tenant) {
      window.location.href = "/onboarding";
      return;
    }
    loadAll();
  }, [loadAll]);

  const webhookUrl = `${getBackendUrl() || (typeof window !== "undefined" ? window.location.origin : "https://teloxtech.stream")}/api/v1/growth/webhooks/meta`;

  const handleCopyWebhook = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(webhookUrl);
      setCopiedWebhook(true);
      setTimeout(() => setCopiedWebhook(false), 2000);
    }
  };

  const handleConnectMetaSocial = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!metaToken.trim() || !metaPageId.trim()) return;
    setBanner(null);
    const res = await apiRequest("/api/v1/integrations/meta_social/connect", {
      method: "POST",
      body: JSON.stringify({
        api_key: metaToken.trim(),
        account_identifier: metaPageId.trim(),
        configuration: {
          page_id: metaPageId.trim(),
          ...(metaIgId.trim() ? { ig_account_id: metaIgId.trim() } : {}),
        },
      }),
    });
    if (res.success) {
      setMetaToken("");
      setBanner({ type: "ok", text: "Meta Page & Instagram Comment-to-DM token encrypted and linked cleanly." });
      loadAll();
    } else {
      setBanner({ type: "err", text: res.error?.message || "Failed to connect Meta Social account." });
    }
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    const res = await apiRequest("/api/v1/growth/comment-dm/rules", {
      method: "POST",
      body: JSON.stringify({
        platform: newPlatform,
        keyword: newKeyword.trim(),
        dm_template: newDmTemplate.trim(),
        booking_url: newBookingUrl.trim() || null,
      }),
    });
    if (res.success) {
      setBanner({ type: "ok", text: `Keyword rule "${newKeyword.trim()}" created.` });
      loadAll();
    } else {
      setBanner({ type: "err", text: res.error?.message || "Failed to create rule." });
    }
  };

  const handleDeleteRule = async (id: string) => {
    await apiRequest(`/api/v1/growth/comment-dm/rules/${id}`, { method: "DELETE" });
    loadAll();
  };

  const handleSimulateComment = async () => {
    setBanner(null);
    const res = await apiRequest<any>("/api/v1/growth/comment-dm/simulate", {
      method: "POST",
      body: JSON.stringify({
        platform: newPlatform === "facebook" ? "facebook" : "instagram",
        comment_text: simCommentText,
        commenter_name: simCommenterName,
      }),
    });
    if (res.success && res.data?.processed) {
      setBanner({
        type: "ok",
        text: `Auto-DM matched "${res.data.log?.matched_keyword}" and synced CRM Lead + Live Inbox.`,
      });
      loadAll();
    } else {
      setBanner({
        type: "err",
        text: res.data?.reason === "no_matching_keyword_rule"
          ? "No active keyword rule matched that comment. Create a rule or use '*' wildcard."
          : res.error?.message || "Simulation failed.",
      });
    }
  };

  const handleSaveReviewConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    const res = await apiRequest("/api/v1/growth/reviews/config", {
      method: "PUT",
      body: JSON.stringify({
        enabled: rbEnabled,
        google_review_url: rbGoogleUrl.trim() || null,
        delay_minutes: Number(rbDelayMins) || 60,
      }),
    });
    if (res.success) {
      setBanner({ type: "ok", text: "Smart Google Review Booster settings saved." });
      loadAll();
    } else {
      setBanner({ type: "err", text: res.error?.message || "Failed to save Review Booster config." });
    }
  };

  const handleSendReviewPrompt = async (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    const res = await apiRequest("/api/v1/growth/reviews/send-prompt", {
      method: "POST",
      body: JSON.stringify({
        customer_phone: promptPhone.trim(),
        customer_name: promptName.trim() || null,
      }),
    });
    if (res.success) {
      setBanner({ type: "ok", text: `WhatsApp 1-5 Star rating prompt dispatched to ${promptPhone}.` });
      loadAll();
    } else {
      setBanner({ type: "err", text: res.error?.message || "Failed to send review prompt." });
    }
  };

  const handleOcrUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ocrFile) return;
    setOcrBusy(true);
    setBanner(null);
    try {
      const fd = new FormData();
      fd.append("file", ocrFile);
      if (ocrCaption.trim()) fd.append("caption", ocrCaption.trim());
      if (ocrPhone.trim()) fd.append("sender_phone", ocrPhone.trim());
      const resp = await apiFetchResponse("/api/v1/growth/ocr/extract", {
        method: "POST",
        body: fd,
      });
      const json = await resp.json();
      if (resp.ok && json.success) {
        setOcrFile(null);
        setOcrCaption("");
        setBanner({
          type: "ok",
          text: `OCR extracted "${json.data.document_type}"${json.data.status === "pending_approval" ? " — Receipt queued for Admin Approval." : "."}`,
        });
        loadAll();
      } else {
        setBanner({ type: "err", text: json?.error?.message || json?.detail || "Vision OCR failed." });
      }
    } finally {
      setOcrBusy(false);
    }
  };

  const handleDownloadWeeklyRoiPdf = async () => {
    setPdfBusy(true);
    setBanner(null);
    try {
      const resp = await apiFetchResponse("/api/v1/growth/pdf/weekly-roi?days=7");
      await triggerBlobDownload(resp, "weekly-ai-roi.pdf");
      setBanner({ type: "ok", text: "Weekly ROI Report PDF downloaded cleanly." });
    } catch (err: any) {
      setBanner({ type: "err", text: err?.message || "Failed to generate Weekly ROI PDF." });
    } finally {
      setPdfBusy(false);
    }
  };

  const handleGenerateCustomPdf = async (e: React.FormEvent) => {
    e.preventDefault();
    setPdfBusy(true);
    setBanner(null);
    try {
      const resp = await apiFetchResponse("/api/v1/growth/pdf/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_type: pdfDocType,
          title: pdfTitle,
          recipient_name: pdfRecipient,
          currency: "PKR",
          line_items: [
            {
              description: pdfItemDesc,
              quantity: Math.max(1, Number(pdfItemQty) || 1),
              unit_price: Math.max(0, Number(pdfItemPrice) || 0),
            },
          ],
          notes: pdfNotes,
        }),
      });
      await triggerBlobDownload(resp, `${pdfDocType}-document.pdf`);
      setBanner({ type: "ok", text: "Native ReportLab PDF generated & downloaded!" });
    } catch (err: any) {
      setBanner({ type: "err", text: err?.message || "Failed to generate PDF." });
    } finally {
      setPdfBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />
      <div className="flex flex-1">
        <Sidebar currentPath="/growth-tools" />

        <main className="flex-1 min-w-0 p-4 sm:p-6 md:p-8 max-w-7xl mx-auto w-full space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                  <Zap className="h-6 w-6 text-emerald-600" />
                  <span>Built-In Growth Upsells</span>
                </h1>
                <span className="rounded-full bg-emerald-100 text-emerald-800 px-2.5 py-0.5 text-xs font-semibold">
                  Zero Extra SaaS Cost
                </span>
              </div>
              <p className="mt-1 text-xs sm:text-sm text-slate-500">
                Native Meta Comment-to-DM, 1-5 Star Google Review Shield, Gemini Flash Vision OCR &amp; Auto-PDF Studio.
              </p>
            </div>

            <button
              type="button"
              onClick={loadAll}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>

          {banner && (
            <div
              className={`flex items-center gap-2 rounded-xl border p-3.5 text-xs font-medium ${
                banner.type === "ok"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : "border-red-200 bg-red-50 text-red-800"
              }`}
            >
              {banner.type === "ok" ? (
                <CheckCircle className="h-4 w-4 shrink-0 text-emerald-600" />
              ) : (
                <AlertCircle className="h-4 w-4 shrink-0 text-red-600" />
              )}
              <span>{banner.text}</span>
            </div>
          )}

          {/* Tab Switcher */}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("social_dm")}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-bold transition ${
                activeTab === "social_dm"
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-100"
              }`}
            >
              <Instagram className="h-4 w-4" />
              <span>IG &amp; FB Comment-to-DM</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("reviews")}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-bold transition ${
                activeTab === "reviews"
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-100"
              }`}
            >
              <Star className="h-4 w-4" />
              <span>Google Review Booster</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("ocr_pdf")}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-bold transition ${
                activeTab === "ocr_pdf"
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-100"
              }`}
            >
              <ScanText className="h-4 w-4" />
              <span>Vision OCR &amp; Auto-PDF Studio</span>
            </button>
          </div>

          {/* TAB 1: IG & FB COMMENT-TO-DM */}
          {activeTab === "social_dm" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-5 space-y-6">
                <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-bold text-slate-900">1. Meta Browser Auth &amp; Webhook Handshake</h2>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                        metaConnected ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {metaConnected ? "Connected" : "Setup Needed"}
                    </span>
                  </div>
                  <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 space-y-1.5 text-[11px] text-slate-600">
                    <div className="font-semibold text-slate-800">Webhook Callback URL (Meta App Dashboard):</div>
                    <div className="flex items-center justify-between gap-2 font-mono text-[10px] bg-white border border-slate-200 rounded px-2 py-1">
                      <span className="truncate">{webhookUrl}</span>
                      <button type="button" onClick={handleCopyWebhook} className="text-emerald-600 hover:text-emerald-700 shrink-0">
                        {copiedWebhook ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                  </div>
                  <form onSubmit={handleConnectMetaSocial} className="space-y-2.5 text-xs">
                    <input
                      type="text"
                      value={metaPageId}
                      onChange={(e) => setMetaPageId(e.target.value)}
                      placeholder="Facebook Page ID (e.g. 1029384756)"
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                      required
                    />
                    <input
                      type="text"
                      value={metaIgId}
                      onChange={(e) => setMetaIgId(e.target.value)}
                      placeholder="Instagram Business Account ID (optional)"
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    />
                    <input
                      type="password"
                      value={metaToken}
                      onChange={(e) => setMetaToken(e.target.value)}
                      placeholder="Meta Page Access Token (encrypted at rest)"
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                      required
                    />
                    <button
                      type="submit"
                      className="w-full rounded-lg bg-slate-900 hover:bg-slate-800 text-white py-2 text-xs font-semibold"
                    >
                      Save &amp; Connect Meta Social Credentials
                    </button>
                  </form>
                </div>

                <form onSubmit={handleCreateRule} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3 text-xs">
                  <h2 className="text-sm font-bold text-slate-900">2. Add Comment-to-DM Keyword Rule</h2>
                  <div className="grid grid-cols-2 gap-2">
                    <select
                      value={newPlatform}
                      onChange={(e) => setNewPlatform(e.target.value as any)}
                      className="rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
                    >
                      <option value="both">IG &amp; FB (Both)</option>
                      <option value="instagram">Instagram Only</option>
                      <option value="facebook">Facebook Only</option>
                    </select>
                    <input
                      type="text"
                      value={newKeyword}
                      onChange={(e) => setNewKeyword(e.target.value)}
                      placeholder="Keyword (or * for all)"
                      className="rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
                      required
                    />
                  </div>
                  <textarea
                    rows={3}
                    value={newDmTemplate}
                    onChange={(e) => setNewDmTemplate(e.target.value)}
                    placeholder="DM prompt or template..."
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    required
                  />
                  <input
                    type="url"
                    value={newBookingUrl}
                    onChange={(e) => setNewBookingUrl(e.target.value)}
                    placeholder="Custom Cal.com booking URL (uses workspace default if blank)"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                  />
                  <button
                    type="submit"
                    className="w-full inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white py-2 font-semibold"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Add Keyword Trigger Rule</span>
                  </button>
                </form>
              </div>

              <div className="lg:col-span-7 space-y-6">
                <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                  <h2 className="text-sm font-bold text-slate-900">Test Comment-to-DM Simulator</h2>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <input
                      type="text"
                      value={simCommenterName}
                      onChange={(e) => setSimCommenterName(e.target.value)}
                      placeholder="Commenter Name"
                      className="rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    />
                    <input
                      type="text"
                      value={simCommentText}
                      onChange={(e) => setSimCommentText(e.target.value)}
                      placeholder="Simulated IG/FB comment..."
                      className="sm:col-span-2 rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleSimulateComment}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 px-4 py-2 text-xs font-semibold text-white"
                  >
                    <Send className="h-3.5 w-3.5" />
                    <span>Simulate Comment Webhook</span>
                  </button>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                  <h2 className="text-sm font-bold text-slate-900">Active Keyword Rules ({rules.length})</h2>
                  {rules.length === 0 ? (
                    <p className="text-xs text-slate-400">No rules created yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {rules.map((r) => (
                        <div key={r.id} className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 p-3 text-xs">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="rounded bg-emerald-100 text-emerald-800 px-2 py-0.5 font-mono text-[10px] font-bold">
                                {r.keyword}
                              </span>
                              <span className="uppercase text-[10px] font-semibold text-slate-500">{r.platform}</span>
                              <span className="text-[10px] text-slate-400">{r.trigger_count} DMs sent</span>
                            </div>
                            <p className="mt-1 text-slate-700">{r.dm_template}</p>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleDeleteRule(r.id)}
                            className="text-slate-400 hover:text-red-600 p-1"
                            aria-label="Delete rule"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                  <h2 className="text-sm font-bold text-slate-900">Recent Auto-DM Dispatches ({dmLogs.length})</h2>
                  {dmLogs.length === 0 ? (
                    <p className="text-xs text-slate-400">No Comment-to-DM logs recorded yet.</p>
                  ) : (
                    <div className="space-y-2 max-h-72 overflow-y-auto">
                      {dmLogs.map((l) => (
                        <div key={l.id} className="rounded-lg border border-slate-100 bg-slate-50 p-3 text-xs space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-slate-900">
                              {l.commenter_name} ({l.platform})
                            </span>
                            <span className="rounded-full bg-emerald-100 text-emerald-800 px-2 py-0.5 text-[10px] font-bold">
                              {l.status}
                            </span>
                          </div>
                          <p className="text-slate-500">Comment: &ldquo;{l.comment_text}&rdquo;</p>
                          <p className="text-slate-800 font-medium">DM Sent: {l.dm_text}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: GOOGLE REVIEW BOOSTER */}
          {activeTab === "reviews" && (
            <div className="space-y-6">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <div className="text-[11px] font-semibold uppercase text-slate-400">Prompts Sent</div>
                  <div className="text-2xl font-extrabold text-slate-900 mt-1">{reviewStats.total_sent}</div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <div className="text-[11px] font-semibold uppercase text-slate-400">Avg Rating</div>
                  <div className="text-2xl font-extrabold text-amber-600 mt-1">{reviewStats.average_rating} / 5</div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <div className="text-[11px] font-semibold uppercase text-slate-400">4-5★ Google Routed</div>
                  <div className="text-2xl font-extrabold text-emerald-600 mt-1">{reviewStats.google_routed_count}</div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <div className="text-[11px] font-semibold uppercase text-slate-400">1-3★ Privately Caught</div>
                  <div className="text-2xl font-extrabold text-rose-600 mt-1">{reviewStats.private_intercepted_count}</div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-5 space-y-6">
                  <form onSubmit={handleSaveReviewConfig} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3 text-xs">
                    <h2 className="text-sm font-bold text-slate-900">Google Business Profile Routing</h2>
                    <label className="flex items-center gap-2 font-medium text-slate-700">
                      <input
                        type="checkbox"
                        checked={rbEnabled}
                        onChange={(e) => setRbEnabled(e.target.checked)}
                        className="rounded border-slate-300"
                      />
                      Auto-send rating prompt 1 hour after completed Cal.com appointments
                    </label>
                    <input
                      type="url"
                      value={rbGoogleUrl}
                      onChange={(e) => setRbGoogleUrl(e.target.value)}
                      placeholder="https://g.page/r/YOUR-PLACE-ID/review"
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    />
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500">Delay after appointment (mins):</span>
                      <input
                        type="number"
                        min={5}
                        max={1440}
                        value={rbDelayMins}
                        onChange={(e) => setRbDelayMins(e.target.value)}
                        className="w-24 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                    <button
                      type="submit"
                      className="w-full rounded-lg bg-slate-900 hover:bg-slate-800 text-white py-2 font-semibold"
                    >
                      Save Review Booster Settings
                    </button>
                  </form>

                  <form onSubmit={handleSendReviewPrompt} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3 text-xs">
                    <h2 className="text-sm font-bold text-slate-900">Send Manual Rating Prompt via WhatsApp</h2>
                    <input
                      type="text"
                      value={promptName}
                      onChange={(e) => setPromptName(e.target.value)}
                      placeholder="Customer Name"
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    />
                    <input
                      type="text"
                      value={promptPhone}
                      onChange={(e) => setPromptPhone(e.target.value)}
                      placeholder="+923001234567"
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                      required
                    />
                    <button
                      type="submit"
                      className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white py-2 font-semibold"
                    >
                      Dispatch 1-5 Star WhatsApp Prompt
                    </button>
                  </form>
                </div>

                <div className="lg:col-span-7 rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                  <h2 className="text-sm font-bold text-slate-900">Review Routing &amp; Private Feedback Log</h2>
                  {reviewRows.length === 0 ? (
                    <p className="text-xs text-slate-400">No review prompts dispatched yet.</p>
                  ) : (
                    <div className="space-y-2.5">
                      {reviewRows.map((rr) => (
                        <div key={rr.id} className="rounded-lg border border-slate-200 p-3 text-xs space-y-1">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-bold text-slate-900">
                              {rr.customer_name || rr.customer_phone} ({rr.customer_phone})
                            </span>
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                                rr.routing_target === "google_business"
                                  ? "bg-emerald-100 text-emerald-800"
                                  : rr.routing_target === "internal_feedback"
                                  ? "bg-rose-100 text-rose-800"
                                  : "bg-slate-100 text-slate-700"
                              }`}
                            >
                              {rr.rating ? `${rr.rating}★ ` : ""}
                              {rr.status}
                            </span>
                          </div>
                          {rr.private_feedback && (
                            <p className="rounded bg-rose-50 border border-rose-100 px-2.5 py-1.5 text-rose-900">
                              Private Feedback: {rr.private_feedback}
                            </p>
                          )}
                          {rr.routing_target === "internal_feedback" && !rr.private_feedback && (
                            <a
                              href={`/feedback?token=${rr.feedback_token}`}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 hover:underline"
                            >
                              <span>Preview Private Feedback Form</span>
                              <ExternalLink className="h-3 w-3" />
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: VISION OCR & AUTO-PDF STUDIO */}
          {activeTab === "ocr_pdf" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-6 space-y-6">
                <form onSubmit={handleOcrUpload} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3 text-xs">
                  <h2 className="text-sm font-bold text-slate-900">
                    WhatsApp &amp; Upload Gemini Flash Vision OCR
                  </h2>
                  <p className="text-slate-500">
                    Upload a payment receipt, clinic prescription, or lab report image. Receipts trigger Human-in-the-Loop Admin Approval cleanly.
                  </p>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => setOcrFile(e.target.files?.[0] || null)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs bg-slate-50"
                    required
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      value={ocrPhone}
                      onChange={(e) => setOcrPhone(e.target.value)}
                      placeholder="Lead Phone (optional)"
                      className="rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    />
                    <input
                      type="text"
                      value={ocrCaption}
                      onChange={(e) => setOcrCaption(e.target.value)}
                      placeholder="Caption/context (e.g. paid receipt)"
                      className="rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={ocrBusy || !ocrFile}
                    className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white py-2 font-semibold"
                  >
                    {ocrBusy ? "Extracting..." : "Extract Structured Data with Vision OCR"}
                  </button>
                </form>

                <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                  <h3 className="text-sm font-bold text-slate-900">Recent Vision OCR Extractions ({extractions.length})</h3>
                  {extractions.length === 0 ? (
                    <p className="text-xs text-slate-400">No documents extracted yet.</p>
                  ) : (
                    <div className="space-y-2.5 max-h-80 overflow-y-auto">
                      {extractions.map((ex) => (
                        <div key={ex.id} className="rounded-lg border border-slate-200 p-3 text-xs space-y-1.5">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-bold uppercase text-slate-900">
                              {ex.document_type.replace("_", " ")}
                            </span>
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                                ex.status === "pending_approval"
                                  ? "bg-amber-100 text-amber-800"
                                  : "bg-emerald-100 text-emerald-800"
                              }`}
                            >
                              {ex.status === "pending_approval" ? (
                                <span className="inline-flex items-center gap-1">
                                  <ShieldAlert className="h-3 w-3" /> Approval Queued
                                </span>
                              ) : (
                                ex.status
                              )}
                            </span>
                          </div>
                          {ex.raw_summary && <p className="text-slate-600">{ex.raw_summary}</p>}
                          <pre className="rounded bg-slate-900 text-emerald-300 p-2 text-[10px] overflow-x-auto">
                            {JSON.stringify(ex.extracted_data, null, 2)}
                          </pre>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="lg:col-span-6 space-y-6">
                <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                  <h2 className="text-sm font-bold text-slate-900">1-Click Native ReportLab Auto-PDF Downloads</h2>
                  <p className="text-xs text-slate-500">
                    Pure Python PDF rendering (zero external PDF API subscriptions).
                  </p>
                  <button
                    type="button"
                    disabled={pdfBusy}
                    onClick={handleDownloadWeeklyRoiPdf}
                    className="inline-flex items-center gap-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 text-xs font-semibold"
                  >
                    <FileDown className="h-4 w-4 text-emerald-400" />
                    <span>Download Weekly AI ROI Executive PDF</span>
                  </button>
                </div>

                <form onSubmit={handleGenerateCustomPdf} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3 text-xs">
                  <h2 className="text-sm font-bold text-slate-900">Generate Branded Quote, Invoice or Prescription PDF</h2>
                  <div className="grid grid-cols-2 gap-2">
                    <select
                      value={pdfDocType}
                      onChange={(e) => setPdfDocType(e.target.value)}
                      className="rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
                    >
                      <option value="quote">Service Quote</option>
                      <option value="invoice">Proforma Invoice</option>
                      <option value="prescription">Clinic Prescription / Plan</option>
                      <option value="summary">Executive Summary</option>
                    </select>
                    <input
                      type="text"
                      value={pdfRecipient}
                      onChange={(e) => setPdfRecipient(e.target.value)}
                      placeholder="Recipient / Patient Name"
                      className="rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    />
                  </div>
                  <input
                    type="text"
                    value={pdfTitle}
                    onChange={(e) => setPdfTitle(e.target.value)}
                    placeholder="Document Title"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    required
                  />
                  <div className="grid grid-cols-4 gap-2">
                    <input
                      type="text"
                      value={pdfItemDesc}
                      onChange={(e) => setPdfItemDesc(e.target.value)}
                      placeholder="Line item description"
                      className="col-span-2 rounded-lg border border-slate-300 px-3 py-2 text-xs"
                    />
                    <input
                      type="number"
                      min={1}
                      value={pdfItemQty}
                      onChange={(e) => setPdfItemQty(e.target.value)}
                      placeholder="Qty"
                      className="rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
                    />
                    <input
                      type="number"
                      min={0}
                      value={pdfItemPrice}
                      onChange={(e) => setPdfItemPrice(e.target.value)}
                      placeholder="PKR Price"
                      className="rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
                    />
                  </div>
                  <textarea
                    rows={2}
                    value={pdfNotes}
                    onChange={(e) => setPdfNotes(e.target.value)}
                    placeholder="Footer notes or instructions..."
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs"
                  />
                  <button
                    type="submit"
                    disabled={pdfBusy}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white py-2 font-semibold"
                  >
                    <FileDown className="h-4 w-4" />
                    <span>{pdfBusy ? "Rendering PDF..." : "Generate & Download PDF"}</span>
                  </button>
                </form>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
