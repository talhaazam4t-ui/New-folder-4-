"use client";

import React, { useState } from "react";
import { HunterLead } from "./types";
import { Phone, Mail, ExternalLink, Clock, AlertCircle, Sparkles, DollarSign } from "lucide-react";

interface Props {
  callList: HunterLead[];
  busyLeadId: string | null;
  onOutcome: (leadId: string, outcome: string, dealValueUsd?: number) => void;
  onGenerateDemo: (leadId: string) => void;
  onRunAgent?: (leadId: string) => void;
  onAcknowledgeHandover: (leadId: string) => void;
}

function formatProspectClock(tz: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: tz || "America/New_York",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZoneName: "short",
    }).format(new Date());
  } catch {
    return tz;
  }
}

export function HotCallListTab({
  callList,
  busyLeadId,
  onOutcome,
  onGenerateDemo,
  onRunAgent,
  onAcknowledgeHandover,
}: Props) {
  const [expandedScriptId, setExpandedScriptId] = useState<string | null>(null);
  const myLocalTz =
    typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "Local";

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-blue-500/30 bg-blue-950/20 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs">
        <div>
          <span className="font-bold text-blue-300">Direct Outreach Call List (Score 80+ Hot Leads Only)</span>
          <p className="text-slate-300 mt-0.5">
            Zero automated messages sent in Direct Call Mode unless you manually approve &amp; send. Your clock: {myLocalTz}
          </p>
        </div>
        <span className="font-mono text-emerald-400 font-bold">{callList.length} Hot Prospect(s)</span>
      </div>

      {callList.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-10 text-center text-xs text-slate-400">
          No Hot Leads (Score 80+) ready yet. Search for businesses in Lead Finder or click &ldquo;Add to Hot Lead&rdquo;.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {callList.map((lead) => {
            const localThere = formatProspectClock(lead.timezone);
            const showScript = expandedScriptId === lead.id;
            return (
              <div
                key={lead.id}
                className={`rounded-xl border p-5 space-y-4 ${
                  lead.human_needed
                    ? "border-rose-500 bg-rose-950/20"
                    : "border-slate-800 bg-slate-900/90"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-extrabold text-white">{lead.business_name}</h3>
                      <span className="rounded bg-emerald-500/20 px-2 py-0.5 font-mono text-[11px] font-bold text-emerald-300">
                        Score {lead.interest_score}
                      </span>
                    </div>
                    <p className="text-xs text-blue-300 font-semibold mt-0.5">
                      {lead.owner_name || "Owner / Decision Maker"}
                      {lead.owner_title ? ` — ${lead.owner_title}` : ""}
                    </p>
                    <p className="text-[11px] text-slate-400">
                      {lead.category} • {lead.city}, {lead.country}
                    </p>
                  </div>

                  {lead.human_needed && (
                    <button
                      type="button"
                      onClick={() => onAcknowledgeHandover(lead.id)}
                      className="rounded-lg bg-rose-600 hover:bg-rose-500 px-2.5 py-1 text-[10px] font-bold text-white"
                    >
                      Human Needed • Clear Alert
                    </button>
                  )}
                </div>

                <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-1.5 text-xs">
                  <div className="flex flex-wrap items-center gap-4 text-slate-200">
                    <span className="inline-flex items-center gap-1.5 font-mono">
                      <Phone className="h-3.5 w-3.5 text-emerald-400" />
                      {lead.phone || "No direct phone"}
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <Mail className="h-3.5 w-3.5 text-blue-400" />
                      {lead.email || "No email"}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
                    {lead.linkedin_url && (
                      <a
                        href={lead.linkedin_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-cyan-400 hover:underline"
                      >
                        <span>LinkedIn Profile</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                    {lead.website && (
                      <a
                        href={lead.website}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-blue-400 hover:underline"
                      >
                        <span>Website</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </div>

                {/* Pain Point + Timezone Conversion */}
                <div className="space-y-1.5 text-xs">
                  <div className="flex items-start gap-2 text-amber-300">
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                    <span>{lead.pain_summary || lead.services}</span>
                  </div>
                  <div className="flex items-center gap-2 text-cyan-300 text-[11px]">
                    <Clock className="h-3.5 w-3.5 shrink-0" />
                    <span>
                      Current time in {lead.city}: <strong>{localThere}</strong> (Call 9:30–11:30 AM or 2:00–4:30 PM there)
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => setExpandedScriptId(showScript ? null : lead.id)}
                    className="text-xs font-semibold text-blue-400 hover:underline"
                  >
                    {showScript ? "Hide Call & Email Script" : "Show Tailored Cold Call & Email Script"}
                  </button>
                  <div className="flex items-center gap-1.5">
                    {onRunAgent && (
                      <button
                        type="button"
                        disabled={busyLeadId === lead.id}
                        onClick={() => onRunAgent(lead.id)}
                        className="inline-flex items-center gap-1 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 px-2.5 py-1 text-[11px] font-bold text-white"
                      >
                        <Sparkles className="h-3 w-3" />
                        <span>{busyLeadId === lead.id ? "Running..." : "Run AI Agent"}</span>
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busyLeadId === lead.id}
                      onClick={() => onGenerateDemo(lead.id)}
                      className="inline-flex items-center gap-1 rounded bg-slate-800 hover:bg-blue-600 px-2.5 py-1 text-[11px] font-semibold text-white"
                    >
                      <Sparkles className="h-3 w-3" /> Generate Demo
                    </button>
                  </div>
                </div>

                {showScript && (
                  <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-2 text-[11px] text-slate-300">
                    <div>
                      <span className="font-bold text-blue-300">Suggested Cold Call Script:</span>
                      <p className="mt-0.5 leading-relaxed">{lead.cold_call_script}</p>
                    </div>
                    <div className="pt-2 border-t border-slate-800">
                      <span className="font-bold text-cyan-300">Suggested Cold Email:</span>
                      <pre className="mt-0.5 whitespace-pre-wrap font-sans">{lead.cold_email_script}</pre>
                    </div>
                  </div>
                )}

                {/* Manual Outreach Outcomes */}
                <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-800">
                  <button
                    type="button"
                    disabled={busyLeadId === lead.id}
                    onClick={() => onOutcome(lead.id, "interested")}
                    className="rounded-lg bg-blue-600 hover:bg-blue-500 px-2.5 py-1.5 text-[11px] font-bold text-white"
                  >
                    Interested
                  </button>
                  <button
                    type="button"
                    disabled={busyLeadId === lead.id}
                    onClick={() => onOutcome(lead.id, "call_later")}
                    className="rounded-lg border border-amber-500/40 bg-amber-950/40 hover:bg-amber-900/50 px-2.5 py-1.5 text-[11px] font-bold text-amber-300"
                  >
                    Call Later (+24h)
                  </button>
                  <button
                    type="button"
                    disabled={busyLeadId === lead.id}
                    onClick={() => onOutcome(lead.id, "demo_sent")}
                    className="rounded-lg border border-cyan-500/40 bg-cyan-950/40 hover:bg-cyan-900/50 px-2.5 py-1.5 text-[11px] font-bold text-cyan-300"
                  >
                    Demo Sent
                  </button>
                  <button
                    type="button"
                    disabled={busyLeadId === lead.id}
                    onClick={() => onOutcome(lead.id, "paid", 299)}
                    className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-2.5 py-1.5 text-[11px] font-bold text-white"
                  >
                    <DollarSign className="h-3 w-3" /> Paid ($299)
                  </button>
                  <button
                    type="button"
                    disabled={busyLeadId === lead.id}
                    onClick={() => onOutcome(lead.id, "not_interested")}
                    className="rounded-lg border border-slate-700 bg-slate-950 hover:border-rose-500 px-2.5 py-1.5 text-[11px] font-semibold text-slate-400 hover:text-rose-300"
                  >
                    Not Interested
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
