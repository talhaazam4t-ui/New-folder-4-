"use client";

import React from "react";
import { FinancialSummary } from "./types";
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Clock,
  AlertCircle,
} from "lucide-react";

interface KPIRowProps {
  summary: FinancialSummary | null;
  loading: boolean;
}

export function FinancialKPIRow({ summary, loading }: KPIRowProps) {
  const currency = summary?.currency || "USD";

  const formatMoney = (val: number | undefined) => {
    if (val === undefined || isNaN(val)) return "0.00";
    return new Intl.NumberFormat("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(val);
  };

  const kpis = [
    {
      title: "Total Cash Balance",
      value: `${currency} ${formatMoney(summary?.total_cash_balance)}`,
      subtext: Object.keys(summary?.currency_balances || {}).length > 1
        ? `${Object.entries(summary?.currency_balances || {})
            .map(([curr, bal]) => `${curr}: ${formatMoney(bal)}`)
            .join(" • ")}`
        : "Reconciled across active vaults",
      icon: Wallet,
      color: "text-emerald-400",
      bgColor: "bg-emerald-500/10",
      borderColor: "border-emerald-500/20",
    },
    {
      title: "Monthly Revenue (Inflow)",
      value: `${currency} ${formatMoney(summary?.monthly_revenue)}`,
      subtext: "Paid income & rent (last 30d)",
      icon: TrendingUp,
      color: "text-emerald-400",
      bgColor: "bg-emerald-500/10",
      borderColor: "border-emerald-500/20",
    },
    {
      title: "Monthly Expenses (Outflow)",
      value: `${currency} ${formatMoney(summary?.monthly_expenses)}`,
      subtext: `Monthly burn rate: ${currency} ${formatMoney(summary?.monthly_burn_rate)}`,
      icon: TrendingDown,
      color: "text-rose-400",
      bgColor: "bg-rose-500/10",
      borderColor: "border-rose-500/20",
    },
    {
      title: "Net Cash Flow",
      value: `${currency} ${formatMoney(summary?.net_cash_flow)}`,
      subtext: (summary?.net_cash_flow || 0) >= 0 ? "Positive Operational Margin" : "Negative Margin (Deficit)",
      icon: DollarSign,
      color: (summary?.net_cash_flow || 0) >= 0 ? "text-emerald-400" : "text-rose-400",
      bgColor: (summary?.net_cash_flow || 0) >= 0 ? "bg-emerald-500/10" : "bg-rose-500/10",
      borderColor: (summary?.net_cash_flow || 0) >= 0 ? "border-emerald-500/20" : "border-rose-500/20",
    },
    {
      title: "Pending / Overdue Rent",
      value: `${currency} ${formatMoney(summary?.accounts_receivable)}`,
      subtext: `${summary?.pending_rent_count || 0} pending • ${summary?.overdue_rent_count || 0} overdue`,
      icon: (summary?.overdue_rent_count || 0) > 0 ? AlertCircle : Clock,
      color: (summary?.overdue_rent_count || 0) > 0 ? "text-amber-400" : "text-slate-300",
      bgColor: (summary?.overdue_rent_count || 0) > 0 ? "bg-amber-500/10" : "bg-slate-800/50",
      borderColor: (summary?.overdue_rent_count || 0) > 0 ? "border-amber-500/30" : "border-slate-800",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      {kpis.map((kpi, idx) => {
        const Icon = kpi.icon;
        return (
          <div
            key={idx}
            className="rounded-xl bg-[#131F2E] border border-slate-800/80 p-5 shadow-lg relative overflow-hidden transition-all hover:border-slate-700/90"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
                {kpi.title}
              </span>
              <div className={`p-2 rounded-lg ${kpi.bgColor} border ${kpi.borderColor}`}>
                <Icon className={`h-4 w-4 ${kpi.color}`} />
              </div>
            </div>
            {loading ? (
              <div className="h-7 w-28 bg-slate-800/60 animate-pulse rounded my-1" />
            ) : (
              <div className="text-xl font-bold tracking-tight text-white mb-1">
                {kpi.value}
              </div>
            )}
            <p className="text-[11px] text-slate-400 truncate" title={kpi.subtext}>
              {kpi.subtext}
            </p>
          </div>
        );
      })}
    </div>
  );
}
