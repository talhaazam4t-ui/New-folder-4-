"use client";

import React, { useState } from "react";
import { HunterDemo, HunterModuleSetting } from "./types";
import { apiRequest } from "@/lib/api";
import {
  CheckCircle,
  Send,
  XCircle,
  MessageSquare,
  Mail,
  PhoneCall,
  Copy,
  Check,
  Sparkles,
} from "lucide-react";

interface Props {
  demos: HunterDemo[];
  moduleMap: Record<string, HunterModuleSetting>;
  busyDemoId: string | null;
  onSaveDraft: (demoId: string, payload: Partial<HunterDemo>) => void;
  onApprove: (demoId: string) => void;
  onApproveAndSend: (demoId: string, channel: "email" | "linkedin" | "whatsapp") => void;
  onSendApproved: (demoId: string, channel: "email" | "linkedin" | "whatsapp") => void;
  onReject: (demoId: string) => void;
}

export function DemoApprovalTab({
  demos,
  moduleMap,
  busyDemoId,
  onSaveDraft,
  onApprove,
  onApproveAndSend,
  onSendApproved,
  onReject,
}: Props) {
  const [statusTab, setStatusTab] = useState<"draft" | "approved" | "sent">("draft");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftEdits, setDraftEdits] = useState<Record<string, Partial<HunterDemo>>>({});
  const [chatInput, setChatInput] = useState("What are your hours and pricing?");
  const [chatLog, setChatLog] = useState<Array<{ from: string; text: string }>>([]);
  const [copiedLi, setCopiedLi] = useState(false);

  const filtered = demos.filter((d) => d.status === statusTab);
  const active = filtered.find((d) => d.id === selectedId) || filtered[0] || null;

  const getField = (demo: HunterDemo, field: keyof HunterDemo): string => {
    const edited = draftEdits[demo.id]?.[field];
    if (typeof edited === "string") return edited;
    const raw = demo[field];
    return typeof raw === "string" ? raw : "";
  };

  const setField = (demoId: string, field: keyof HunterDemo, value: string) => {
    setDraftEdits((prev) => ({
      ...prev,
      [demoId]: {
        ...(prev[demoId] || {}),
        [field]: value,
      },
    }));
  };

  const handleChatTest = async (demo: HunterDemo) => {
    if (!chatInput.trim()) return;
    const msg = chatInput.trim();
    setChatLog((prev) => [...prev, { from: "Visitor", text: msg }]);
    setChatInput("");
    const res = await apiRequest<{ ai_receptionist_reply: string }>(
      `/api/v1/lead-hunter/demos/${demo.id}/chat-preview`,
      { method: "POST", body: JSON.stringify({ visitor_message: msg }) }
    );
    if (res.success && res.data?.ai_receptionist_reply) {
      setChatLog((prev) => [...prev, { from: "AI Receptionist", text: res.data!.ai_receptionist_reply }]);
    }
  };

  const handleCopyLinkedin = (demo: HunterDemo) => {
    const note = `Hi ${demo.lead?.owner_name || "there"} — built a free 24/7 AI Receptionist demo for ${demo.lead?.business_name || "your team"}: ${demo.whatsapp_copy}`;
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(note);
      setCopiedLi(true);
      setTimeout(() => setCopiedLi(false), 2000);
    }
  };

  const emailOn = Boolean(moduleMap.auto_email_sender?.is_on);
  const waOn = Boolean(moduleMap.auto_whatsapp_sender?.is_on);
  const liOn = Boolean(moduleMap.auto_linkedin_sender?.is_on);
  const isUae =
    (active?.lead?.country || "").toLowerCase().includes("uae") ||
    (active?.lead?.city || "").toLowerCase().includes("dubai");

  return (
    <div className="space-y-4">
      {/* Draft / Approved / Sent Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2 text-xs">
          {(["draft", "approved", "sent"] as const).map((tab) => {
            const cnt = demos.filter((d) => d.status === tab).length;
            return (
              <button
                key={tab}
                type="button"
                onClick={() => {
                  setStatusTab(tab);
                  setSelectedId(null);
                  setChatLog([]);
                }}
                className={`rounded-lg px-4 py-2 font-bold capitalize border transition ${
                  statusTab === tab
                    ? "border-blue-500 bg-blue-600 text-white"
                    : "border-slate-800 bg-slate-900 text-slate-300 hover:border-blue-500/40"
                }`}
              >
                {tab} ({cnt})
              </button>
            );
          })}
        </div>
        <span className="text-xs text-slate-400">
          Human-in-the-Loop Guardrail: Generated demos ALWAYS enter Draft first and never auto-send.
        </span>
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-10 text-center text-xs text-slate-400">
          No demos in &ldquo;{statusTab}&rdquo;. Click &ldquo;Generate Demo&rdquo; on any lead in Lead Finder or Hot Call List.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Left Demo List */}
          <div className="lg:col-span-4 space-y-2 max-h-[680px] overflow-y-auto">
            {filtered.map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => {
                  setSelectedId(d.id);
                  setChatLog([]);
                }}
                className={`w-full text-left rounded-xl border p-3.5 transition ${
                  active?.id === d.id
                    ? "border-blue-500 bg-blue-950/30"
                    : "border-slate-800 bg-slate-900/90 hover:border-slate-700"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    {d.lead?.favicon_url && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={d.lead.favicon_url} alt="" className="h-4 w-4 rounded-sm shrink-0" />
                    )}
                    <span className="font-bold text-white text-xs truncate">
                      {d.lead?.business_name || "Prospect Demo"}
                    </span>
                  </div>
                  <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-bold uppercase text-blue-300">
                    {d.status}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-1 truncate">
                  {d.lead?.owner_name || "Decision Maker"} • {d.lead?.city}, {d.lead?.country}
                </p>
              </button>
            ))}
          </div>

          {/* Right Demo Preview & Approval Workspace */}
          {active && (
            <div className="lg:col-span-8 rounded-xl border border-slate-800 bg-slate-900/90 p-5 space-y-5">
              {/* Branded Prospect Header */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-4">
                <div className="flex items-center gap-3">
                  {active.lead?.favicon_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={active.lead.favicon_url} alt="" className="h-9 w-9 rounded-lg bg-slate-950 p-1 border border-slate-700" />
                  ) : (
                    <div className="h-9 w-9 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center">
                      <Sparkles className="h-4 w-4 text-blue-400" />
                    </div>
                  )}
                  <div>
                    <h3 className="text-base font-extrabold text-white">{active.lead?.business_name}</h3>
                    <p className="text-xs text-slate-400">
                      {active.business_snapshot?.usd_pricing || "$299/month | $499 setup (USD)"} • Hours:{" "}
                      {active.business_snapshot?.working_hours || "Business Hours"}
                    </p>
                  </div>
                </div>

                {/* Action Controls */}
                <div className="flex flex-wrap gap-2">
                  {active.status === "draft" && (
                    <>
                      <button
                        type="button"
                        disabled={busyDemoId === active.id}
                        onClick={() => onSaveDraft(active.id, draftEdits[active.id] || {})}
                        className="rounded-lg border border-slate-700 bg-slate-950 hover:border-blue-500 px-3 py-1.5 text-xs font-semibold text-slate-200"
                      >
                        Keep in Draft (Save)
                      </button>
                      <button
                        type="button"
                        disabled={busyDemoId === active.id}
                        onClick={() => onApprove(active.id)}
                        className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 text-xs font-bold text-white"
                      >
                        <CheckCircle className="h-3.5 w-3.5" /> Approve (Manual Send)
                      </button>
                      <button
                        type="button"
                        disabled={busyDemoId === active.id || !emailOn}
                        onClick={() => onApproveAndSend(active.id, "email")}
                        title={!emailOn ? "Turn ON Auto Email Sender in Control Panel first" : "Approve & send via Email"}
                        className="inline-flex items-center gap-1 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 px-3 py-1.5 text-xs font-bold text-white"
                      >
                        <Send className="h-3.5 w-3.5" /> Approve &amp; Send
                      </button>
                      <button
                        type="button"
                        disabled={busyDemoId === active.id}
                        onClick={() => onReject(active.id)}
                        className="inline-flex items-center gap-1 rounded-lg border border-rose-500/40 bg-rose-950/40 px-3 py-1.5 text-xs font-semibold text-rose-300"
                      >
                        <XCircle className="h-3.5 w-3.5" /> Reject
                      </button>
                    </>
                  )}

                  {active.status === "approved" && (
                    <>
                      <button
                        type="button"
                        disabled={busyDemoId === active.id || !emailOn}
                        onClick={() => onSendApproved(active.id, "email")}
                        className="inline-flex items-center gap-1 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 px-3 py-1.5 text-xs font-bold text-white"
                      >
                        <Mail className="h-3.5 w-3.5" /> Send Email {!emailOn && "(Switch OFF)"}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCopyLinkedin(active)}
                        className="inline-flex items-center gap-1 rounded-lg border border-cyan-500/40 bg-cyan-950/30 px-3 py-1.5 text-xs font-bold text-cyan-300"
                      >
                        {copiedLi ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                        <span>Copy LinkedIn DM</span>
                      </button>
                      {liOn && (
                        <button
                          type="button"
                          disabled={busyDemoId === active.id}
                          onClick={() => onSendApproved(active.id, "linkedin")}
                          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-semibold text-slate-200"
                        >
                          Log LinkedIn Draft Sent
                        </button>
                      )}
                      {isUae && (
                        <button
                          type="button"
                          disabled={busyDemoId === active.id || !waOn}
                          onClick={() => onSendApproved(active.id, "whatsapp")}
                          className="rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 px-3 py-1.5 text-xs font-bold text-white"
                        >
                          Send UAE WhatsApp {!waOn && "(Switch OFF)"}
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>

              {/* 4 Formats Editable Preview */}
              <div className="space-y-4 text-xs">
                <div>
                  <label className="font-bold text-blue-300 flex items-center gap-1.5 mb-1">
                    <Mail className="h-3.5 w-3.5" /> 1. Cold Email Subject &amp; Copy (English)
                  </label>
                  <input
                    type="text"
                    value={getField(active, "email_subject")}
                    onChange={(e) => setField(active.id, "email_subject", e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white mb-2"
                  />
                  <textarea
                    rows={5}
                    value={getField(active, "email_copy")}
                    onChange={(e) => setField(active.id, "email_copy", e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-200"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="font-bold text-emerald-300 flex items-center gap-1.5 mb-1">
                      <MessageSquare className="h-3.5 w-3.5" /> 2. WhatsApp / SMS Demo
                    </label>
                    <textarea
                      rows={4}
                      value={getField(active, "whatsapp_copy")}
                      onChange={(e) => setField(active.id, "whatsapp_copy", e.target.value)}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="font-bold text-cyan-300 flex items-center gap-1.5 mb-1">
                      <PhoneCall className="h-3.5 w-3.5" /> 3. Voice AI Receptionist Script
                    </label>
                    <textarea
                      rows={4}
                      value={getField(active, "voice_script")}
                      onChange={(e) => setField(active.id, "voice_script", e.target.value)}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-200"
                    />
                  </div>
                </div>

                {/* 4. Interactive Website Chat Demo Widget */}
                <div className="rounded-xl border border-blue-500/30 bg-slate-950 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-blue-300">
                      4. Interactive Website Chat Demo ({active.lead?.business_name})
                    </span>
                    <span className="text-[10px] text-slate-400">Live Prospect Sandbox Preview</span>
                  </div>
                  <div className="space-y-2 max-h-36 overflow-y-auto text-[11px]">
                    {chatLog.length === 0 ? (
                      <p className="text-slate-500">
                        Ask a test customer question below (e.g., hours, pricing, booking) to preview how the AI responds.
                      </p>
                    ) : (
                      chatLog.map((c, idx) => (
                        <div
                          key={idx}
                          className={`rounded-lg px-3 py-1.5 ${
                            c.from === "Visitor" ? "bg-slate-800 text-slate-200" : "bg-blue-950/60 border border-blue-500/30 text-blue-200"
                          }`}
                        >
                          <strong>{c.from}:</strong> {c.text}
                        </div>
                      ))
                    )}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      placeholder="Ask as a patient/client..."
                      className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-white"
                    />
                    <button
                      type="button"
                      onClick={() => handleChatTest(active)}
                      className="rounded-lg bg-blue-600 hover:bg-blue-500 px-3 py-1.5 text-xs font-bold text-white"
                    >
                      Test AI Chat
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
