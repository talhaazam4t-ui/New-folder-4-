"use client";

import React, { useState } from "react";
import { HunterLead } from "./types";
import { Clock, ExternalLink, AlertCircle } from "lucide-react";

const STAGE_LABELS: Array<{ id: string; label: string }> = [
  { id: "new_lead", label: "New Lead" },
  { id: "apollo_enriched", label: "Apollo Enriched" },
  { id: "demo_generated", label: "Demo Generated" },
  { id: "demo_sent", label: "Demo Sent" },
  { id: "followup_1", label: "Follow-up 1" },
  { id: "followup_2", label: "Follow-up 2" },
  { id: "followup_3", label: "Follow-up 3" },
  { id: "replied_hot", label: "Replied / Hot Lead" },
  { id: "call_done", label: "Call Done" },
  { id: "trial_started", label: "Trial Started" },
  { id: "paid_client", label: "Paid Client" },
  { id: "not_interested", label: "Not Interested" },
];

interface Props {
  leads: HunterLead[];
  onMoveStage: (leadId: string, stage: string) => void;
}

export function KanbanPipelineTab({ leads, onMoveStage }: Props) {
  const [dragLeadId, setDragLeadId] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-400">
        Drag and drop lead cards across pipeline stages (or use the stage dropdown on any card).
      </p>

      <div className="flex gap-3 overflow-x-auto pb-4">
        {STAGE_LABELS.map((col) => {
          const cards = leads.filter((l) => l.pipeline_stage === col.id);
          return (
            <div
              key={col.id}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                if (dragLeadId) {
                  onMoveStage(dragLeadId, col.id);
                  setDragLeadId(null);
                }
              }}
              className="w-72 shrink-0 rounded-xl border border-slate-800 bg-slate-900/80 flex flex-col max-h-[680px]"
            >
              <div className="px-3.5 py-2.5 border-b border-slate-800 flex items-center justify-between bg-slate-950/70 rounded-t-xl">
                <span className="text-xs font-bold text-white">{col.label}</span>
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-bold text-blue-300">
                  {cards.length}
                </span>
              </div>

              <div className="p-2.5 space-y-2.5 overflow-y-auto flex-1">
                {cards.length === 0 ? (
                  <div className="text-[11px] text-slate-600 text-center py-6">Drop lead here</div>
                ) : (
                  cards.map((lead) => (
                    <div
                      key={lead.id}
                      draggable
                      onDragStart={() => setDragLeadId(lead.id)}
                      className={`rounded-lg border p-3 text-xs space-y-2 cursor-grab active:cursor-grabbing ${
                        lead.human_needed
                          ? "border-rose-500 bg-rose-950/30"
                          : "border-slate-800 bg-slate-950 hover:border-blue-500/50"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-bold text-white leading-tight">{lead.business_name}</span>
                        <span className="rounded bg-blue-600/20 px-1.5 py-0.5 text-[9px] font-bold uppercase text-blue-300 shrink-0">
                          {lead.lead_source === "google_places" ? "Places" : lead.lead_source === "apollo" ? "Apollo" : "Hybrid"}
                        </span>
                      </div>

                      {lead.human_needed && (
                        <div className="flex items-center gap-1 text-[10px] font-bold text-rose-300">
                          <AlertCircle className="h-3 w-3" /> Human Needed Now
                        </div>
                      )}

                      <div className="text-[11px] text-slate-400">
                        {lead.owner_name || lead.city} • Score {lead.interest_score}
                      </div>

                      <div className="text-[10px] text-slate-500 space-y-0.5">
                        <div className="flex items-center gap-1">
                          <Clock className="h-3 w-3 text-cyan-400" />
                          <span>{lead.timezone}</span>
                        </div>
                        <div>
                          Last contact: {lead.last_contact_at ? new Date(lead.last_contact_at).toLocaleDateString() : "Never"}
                        </div>
                        {lead.next_followup_at && (
                          <div className="text-amber-300">
                            Next follow-up: {new Date(lead.next_followup_at).toLocaleString()}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center justify-between gap-2 pt-1 border-t border-slate-800">
                        <select
                          value={lead.pipeline_stage}
                          onChange={(e) => onMoveStage(lead.id, e.target.value)}
                          className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-200 max-w-[140px]"
                        >
                          {STAGE_LABELS.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.label}
                            </option>
                          ))}
                        </select>
                        {lead.website && (
                          <a
                            href={lead.website}
                            target="_blank"
                            rel="noreferrer"
                            className="text-blue-400 hover:text-blue-300"
                          >
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
