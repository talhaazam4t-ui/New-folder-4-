"use client";

import React from "react";
import { HunterModuleSetting } from "./types";
import { ShieldCheck, Sliders, Zap, DollarSign } from "lucide-react";

interface Props {
  budgetMode: string;
  modules: HunterModuleSetting[];
  busyModule: string | null;
  onToggleModule: (moduleName: string, isOn: boolean) => void;
  onUpdateLimit: (moduleName: string, dailyLimit: number) => void;
  onApplyBudgetMode: (mode: "free" | "low_budget" | "full_auto") => void;
}

export function ControlPanelTab({
  budgetMode,
  modules,
  busyModule,
  onToggleModule,
  onUpdateLimit,
  onApplyBudgetMode,
}: Props) {
  const apollo = modules.find((m) => m.module_name === "apollo_enrichment");
  const emailMod = modules.find((m) => m.module_name === "auto_email_sender");

  return (
    <div className="space-y-6">
      {/* Budget Mode Selector */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-blue-400" />
              <span>Budget Mode Presets (Zero-Overage Guardrail)</span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              All automation starts OFF by default except Direct Call Mode. Apply a preset or toggle modules individually.
            </p>
          </div>
          <span className="rounded-full border border-blue-500/40 bg-blue-500/10 px-3 py-1 text-[11px] font-semibold uppercase text-blue-300">
            Active: {budgetMode.replace("_", " ")}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <button
            type="button"
            disabled={busyModule !== null}
            onClick={() => onApplyBudgetMode("free")}
            className={`text-left rounded-xl border p-4 transition ${
              budgetMode === "free"
                ? "border-blue-500 bg-blue-950/40"
                : "border-slate-800 bg-slate-950 hover:border-blue-500/50"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-400">FREE MODE ($0)</span>
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
            </div>
            <p className="mt-1 text-[11px] text-slate-300">
              Free OpenStreetMap Lead Finder ($0) ON + Google Places &amp; Apollo Free Cap ON + Direct Call Mode ON. All senders &amp; generators OFF.
            </p>
          </button>

          <button
            type="button"
            disabled={busyModule !== null}
            onClick={() => onApplyBudgetMode("low_budget")}
            className={`text-left rounded-xl border p-4 transition ${
              budgetMode === "low_budget"
                ? "border-blue-500 bg-blue-950/40"
                : "border-slate-800 bg-slate-950 hover:border-blue-500/50"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-blue-400">LOW BUDGET MODE</span>
              <Sliders className="h-4 w-4 text-blue-400" />
            </div>
            <p className="mt-1 text-[11px] text-slate-300">
              Places + Apollo Free Cap + Demo Generator ON. All Auto Senders OFF (Manual approval &amp; sending only).
            </p>
          </button>

          <button
            type="button"
            disabled={busyModule !== null}
            onClick={() => onApplyBudgetMode("full_auto")}
            className={`text-left rounded-xl border p-4 transition ${
              budgetMode === "full_auto"
                ? "border-blue-500 bg-blue-950/40"
                : "border-slate-800 bg-slate-950 hover:border-blue-500/50"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-cyan-400">FULL AUTO MODE</span>
              <Zap className="h-4 w-4 text-cyan-400" />
            </div>
            <p className="mt-1 text-[11px] text-slate-300">
              All 9 switches ON while strictly enforcing daily anti-ban email/LinkedIn quotas &amp; Apollo free cap.
            </p>
          </button>
        </div>
      </div>

      {/* Anti-Ban & Apollo Free Credit Counter Bar */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {apollo && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 space-y-2.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-white">Apollo Free-Tier Daily Hard Cap</span>
              <span className="font-mono text-blue-400">
                {apollo.used_today} / {apollo.daily_limit} used today
              </span>
            </div>
            <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-blue-500 transition-all"
                style={{ width: `${Math.min(100, (apollo.used_today / Math.max(1, apollo.daily_limit)) * 100)}%` }}
              />
            </div>
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              <span>Max/day:</span>
              {[10, 15, 25].map((cap) => (
                <button
                  key={cap}
                  type="button"
                  onClick={() => onUpdateLimit("apollo_enrichment", cap)}
                  className={`rounded px-2 py-0.5 font-semibold border ${
                    apollo.daily_limit === cap
                      ? "border-blue-500 bg-blue-600/20 text-blue-300"
                      : "border-slate-700 bg-slate-950 text-slate-400 hover:text-white"
                  }`}
                >
                  {cap}/day
                </button>
              ))}
            </div>
          </div>
        )}

        {emailMod && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 space-y-2.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-white">Email Anti-Ban Daily Tier Limit</span>
              <span className="font-mono text-cyan-400">
                {emailMod.used_today} / {emailMod.daily_limit} sent today
              </span>
            </div>
            <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-cyan-500 transition-all"
                style={{ width: `${Math.min(100, (emailMod.used_today / Math.max(1, emailMod.daily_limit)) * 100)}%` }}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
              {[
                { label: "New Email (20/day)", limit: 20 },
                { label: "Warm Email (50/day)", limit: 50 },
                { label: "Verified Domain (200/day)", limit: 200 },
              ].map((tier) => (
                <button
                  key={tier.limit}
                  type="button"
                  onClick={() => onUpdateLimit("auto_email_sender", tier.limit)}
                  className={`rounded px-2 py-0.5 font-semibold border ${
                    emailMod.daily_limit === tier.limit
                      ? "border-blue-500 bg-blue-600/20 text-blue-300"
                      : "border-slate-700 bg-slate-950 text-slate-400 hover:text-white"
                  }`}
                >
                  {tier.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* All 9 Big ON/OFF Switches */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {modules.map((mod) => {
          const isBusy = busyModule === mod.module_name;
          return (
            <div
              key={mod.module_name}
              className={`rounded-xl border p-4 flex flex-col justify-between gap-4 transition ${
                mod.is_on
                  ? "border-blue-500/60 bg-slate-900"
                  : "border-slate-800 bg-slate-950/90"
              }`}
            >
              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="text-sm font-bold text-white leading-tight">{mod.label}</h3>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => onToggleModule(mod.module_name, !mod.is_on)}
                    aria-label={`Toggle ${mod.label}`}
                    className={`shrink-0 relative inline-flex h-7 w-14 items-center rounded-full px-1 transition ${
                      mod.is_on ? "bg-blue-600" : "bg-slate-700"
                    } ${isBusy ? "opacity-50" : ""}`}
                  >
                    <span
                      className={`inline-block h-5 w-5 transform rounded-full bg-white transition ${
                        mod.is_on ? "translate-x-7" : "translate-x-0"
                      }`}
                    />
                  </button>
                </div>
                <p className="text-xs text-slate-400">{mod.description}</p>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-[11px]">
                <span
                  className={`font-bold uppercase ${
                    mod.is_on ? "text-blue-400" : "text-slate-500"
                  }`}
                >
                  {mod.is_on ? "ON" : "OFF"}
                </span>
                <span className="font-mono text-slate-400">
                  Used: {mod.used_today}/{mod.daily_limit}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
