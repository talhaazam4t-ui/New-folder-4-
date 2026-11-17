"use client";

import React from "react";
import { MonthlyChartPoint } from "./types";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";

interface ChartProps {
  data: MonthlyChartPoint[];
  currency?: string;
  loading: boolean;
}

export function CashFlowChart({ data, currency = "USD", loading }: ChartProps) {
  if (loading) {
    return (
      <div className="h-72 w-full rounded-xl bg-[#131F2E] border border-slate-800/80 p-6 flex items-center justify-center">
        <div className="text-sm text-slate-500 animate-pulse">Loading cash flow analysis...</div>
      </div>
    );
  }

  const customTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-lg bg-slate-900 border border-slate-700/80 p-3 shadow-xl text-xs">
          <p className="font-semibold text-slate-200 mb-1.5">{label}</p>
          {payload.map((entry: any, index: number) => (
            <p key={index} style={{ color: entry.color }} className="flex justify-between gap-4 py-0.5">
              <span>{entry.name}:</span>
              <span className="font-mono font-bold">
                {currency} {Number(entry.value).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </span>
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="rounded-xl bg-[#131F2E] border border-slate-800/80 p-6 shadow-lg">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
        <div>
          <h3 className="text-sm font-semibold text-white tracking-wide">
            Cash Flow Trend: Income vs. Expenses
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            6-Month chronological operational comparison ({currency})
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-400">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-emerald-500 inline-block" /> Inflow (Income/Rent)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-rose-500 inline-block" /> Outflow (Expenses)
          </span>
        </div>
      </div>

      <div className="h-72 w-full">
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-slate-500">
            No transaction records logged for historical charting yet.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
              <XAxis dataKey="month" stroke="#64748B" fontSize={11} tickLine={false} />
              <YAxis
                stroke="#64748B"
                fontSize={11}
                tickLine={false}
                tickFormatter={(val) => `${val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val}`}
              />
              <Tooltip content={customTooltip} />
              <Legend wrapperStyle={{ display: "none" }} />
              <Bar dataKey="income" name="Inflow" fill="#10B981" radius={[4, 4, 0, 0]} maxBarSize={32} />
              <Bar dataKey="expense" name="Outflow" fill="#F43F5E" radius={[4, 4, 0, 0]} maxBarSize={32} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
