"use client";

import React, { useState } from "react";
import { RentSchedule } from "./types";
import {
  Building2,
  Phone,
  Calendar,
  MessageSquare,
  Plus,
  CheckCircle2,
  AlertCircle,
  Clock,
} from "lucide-react";

interface RentSchedulesProps {
  schedules: RentSchedule[];
  loading: boolean;
  onOpenNewModal: () => void;
  onTriggerReminders: () => Promise<void>;
  reminderLoading: boolean;
}

export function RentSchedulesTable({
  schedules,
  loading,
  onOpenNewModal,
  onTriggerReminders,
  reminderLoading,
}: RentSchedulesProps) {
  const [filterStatus, setFilterStatus] = useState<string>("all");

  const filtered = schedules.filter(
    (s) => filterStatus === "all" || s.status === filterStatus
  );

  return (
    <div className="rounded-xl bg-[#131F2E] border border-slate-800/80 shadow-lg overflow-hidden">
      <div className="p-5 border-b border-slate-800/80 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-white">Property Rent Schedules</h3>
            <span className="rounded-full bg-teal-500/10 text-teal-400 border border-teal-500/20 px-2 py-0.5 text-[10px] font-bold uppercase">
              Real Estate
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Automated tenant billing cycles and WhatsApp dispatching
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
          >
            <option value="all">All Units</option>
            <option value="active">Active Leases</option>
            <option value="vacant">Vacant Units</option>
          </select>

          {/* Trigger WhatsApp Reminders */}
          <button
            onClick={onTriggerReminders}
            disabled={reminderLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-xs font-semibold text-emerald-400 border border-emerald-500/30 transition disabled:opacity-50"
            title="Scan upcoming/overdue rent and send automated WhatsApp reminder"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            {reminderLoading ? "Dispatching..." : "Send WhatsApp Reminders"}
          </button>

          {/* New Schedule Modal */}
          <button
            onClick={onOpenNewModal}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-semibold text-white shadow transition"
          >
            <Plus className="h-3.5 w-3.5" />
            + New Lease Schedule
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/60 text-slate-400 uppercase tracking-wider font-semibold">
              <th className="py-3 px-4">Property / Unit</th>
              <th className="py-3 px-4">Lessee Name</th>
              <th className="py-3 px-4">WhatsApp Contact</th>
              <th className="py-3 px-4">Monthly Rent</th>
              <th className="py-3 px-4">Billing Day</th>
              <th className="py-3 px-4">Auto Remind</th>
              <th className="py-3 px-4">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 text-slate-300">
            {loading ? (
              <tr>
                <td colSpan={7} className="py-10 text-center text-slate-500">
                  Loading property rent schedules...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-10 text-center text-slate-500">
                  No property units or rent schedules registered yet. Click &quot;+ New Lease Schedule&quot; to begin.
                </td>
              </tr>
            ) : (
              filtered.map((s) => (
                <tr key={s.id} className="hover:bg-slate-850/40 transition">
                  <td className="py-3.5 px-4 font-medium text-white whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <Building2 className="h-4 w-4 text-emerald-400" />
                      <span>{s.property_unit}</span>
                    </div>
                  </td>

                  <td className="py-3.5 px-4 whitespace-nowrap font-medium text-slate-200">
                    {s.lessee_name}
                  </td>

                  <td className="py-3.5 px-4 whitespace-nowrap text-slate-400">
                    <div className="flex items-center gap-1.5 font-mono text-[11px]">
                      <Phone className="h-3 w-3 text-emerald-500" />
                      <span>{s.lessee_whatsapp}</span>
                    </div>
                  </td>

                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <span className="font-mono font-bold text-emerald-400">
                      {s.currency} {s.monthly_rent.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-slate-500 text-[10px]"> / month</span>
                  </td>

                  <td className="py-3.5 px-4 whitespace-nowrap text-slate-300">
                    <div className="flex items-center gap-1 text-[11px]">
                      <Calendar className="h-3 w-3 text-slate-500" />
                      <span>Every {s.billing_day}th</span>
                    </div>
                  </td>

                  <td className="py-3.5 px-4 whitespace-nowrap">
                    {s.auto_remind_whatsapp ? (
                      <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="h-2.5 w-2.5" /> 3d Pre-Alerts
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">
                        Disabled
                      </span>
                    )}
                  </td>

                  <td className="py-3.5 px-4 whitespace-nowrap">
                    {s.status === "active" ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400 border border-emerald-500/20">
                        Active Lease
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 px-2.5 py-0.5 text-[11px] font-semibold text-slate-400 border border-slate-700">
                        Vacant
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
