"use client";

import React, { useState } from "react";
import { HunterFollowup, HunterLead } from "./types";
import { RefreshCw, MessageSquareWarning, Ban, Send } from "lucide-react";

interface Props {
  followups: HunterFollowup[];
  leads: HunterLead[];
  followupEngineOn: boolean;
  busy: boolean;
  onProcessDue: () => void;
  onSimulateReply: (leadId: string, message: string, channel: string) => void;
}

export function FollowupHandoverTab({
  followups,
  leads,
  followupEngineOn,
  busy,
  onProcessDue,
  onSimulateReply,
}: Props) {
  const [selectedLeadId, setSelectedLeadId] = useState<string>(leads[0]?.id || "");
  const [replyChannel, setReplyChannel] = useState("email");
  const [replyMessage, setReplyMessage] = useState("YES interested, please share pricing and call me.");

  const targetLeadId = selectedLeadId || leads[0]?.id || "";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div className="lg:col-span-7 rounded-xl border border-slate-800 bg-slate-900/90 p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-sm font-bold text-white">Auto Follow-up Sequence Queue (24h / 48h / 72h)</h2>
            <p className="text-[11px] text-slate-400">
              Engine status: <strong className={followupEngineOn ? "text-blue-400" : "text-amber-400"}>{followupEngineOn ? "ON" : "OFF (Paused)"}</strong>
            </p>
          </div>
          <button
            type="button"
            disabled={busy || !followupEngineOn}
            onClick={onProcessDue}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 px-3.5 py-2 text-xs font-bold text-white"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} />
            <span>Run Due Follow-ups</span>
          </button>
        </div>

        {followups.length === 0 ? (
          <p className="text-xs text-slate-400 py-6 text-center">
            No follow-ups queued yet. Turn ON &ldquo;Auto Follow-up Engine&rdquo; and send an approved demo.
          </p>
        ) : (
          <div className="space-y-2.5 max-h-[480px] overflow-y-auto">
            {followups.map((f) => (
              <div key={f.id} className="rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-white">
                    {f.business_name || "Lead"} — Follow-up #{f.followup_number} ({f.channel})
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                      f.status === "sent"
                        ? "bg-emerald-500/20 text-emerald-300"
                        : f.status === "cancelled_human_handover"
                        ? "bg-rose-500/20 text-rose-300"
                        : f.status === "cancelled_dnd"
                        ? "bg-slate-800 text-slate-400"
                        : "bg-blue-500/20 text-blue-300"
                    }`}
                  >
                    {f.status.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-slate-300">{f.message}</p>
                {f.scheduled_at && (
                  <p className="text-[10px] text-slate-500">
                    Scheduled: {new Date(f.scheduled_at).toLocaleString()}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Log / Simulate Prospect Reply -> Instant Human Handover or DND */}
      <div className="lg:col-span-5 rounded-xl border border-slate-800 bg-slate-900/90 p-5 space-y-4">
        <div>
          <h2 className="text-sm font-bold text-white flex items-center gap-2">
            <MessageSquareWarning className="h-4 w-4 text-rose-400" />
            <span>Log Prospect Reply (Human Handover &amp; DND Shield)</span>
          </h2>
          <p className="text-[11px] text-slate-400 mt-1">
            Replies with &ldquo;YES / Interested / Price / Demo / Call&rdquo; immediately cancel ALL follow-ups, flag <strong>Human Needed - Contact Now</strong>, and never auto-reply. Replies with &ldquo;No / Stop / Unsubscribe&rdquo; mark permanent DND.
          </p>
        </div>

        <div className="space-y-3 text-xs">
          <div>
            <label className="block text-slate-300 font-semibold mb-1">Prospect Lead</label>
            <select
              value={targetLeadId}
              onChange={(e) => setSelectedLeadId(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            >
              {leads.length === 0 && <option value="">No leads available</option>}
              {leads.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.business_name} ({l.owner_name || l.city})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-slate-300 font-semibold mb-1">Channel</label>
            <select
              value={replyChannel}
              onChange={(e) => setReplyChannel(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            >
              <option value="email">Email</option>
              <option value="whatsapp">WhatsApp</option>
              <option value="linkedin">LinkedIn</option>
              <option value="call">Phone Call</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-300 font-semibold mb-1">Inbound Reply Text</label>
            <textarea
              rows={3}
              value={replyMessage}
              onChange={(e) => setReplyMessage(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={!targetLeadId || busy}
              onClick={() => onSimulateReply(targetLeadId, replyMessage, replyChannel)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 px-4 py-2 font-bold text-white"
            >
              <Send className="h-3.5 w-3.5" /> Record Prospect Reply
            </button>
            <button
              type="button"
              disabled={!targetLeadId || busy}
              onClick={() => onSimulateReply(targetLeadId, "STOP unsubscribe please", replyChannel)}
              className="inline-flex items-center gap-1 rounded-lg border border-rose-500/40 bg-rose-950/30 px-3 py-2 font-semibold text-rose-300"
            >
              <Ban className="h-3.5 w-3.5" /> Test Opt-Out (DND)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
