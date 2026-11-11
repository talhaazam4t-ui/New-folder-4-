"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { Sidebar } from "@/components/shared/Sidebar";
import { StatCard } from "@/components/dashboard/StatCard";
import { apiRequest } from "@/lib/api";
import { getActiveTenant, getAuthToken } from "@/lib/auth";
import {
  DollarSign,
  TrendingUp,
  Receipt,
  Users,
  Bot,
  AlertTriangle,
  ArrowUpRight,
  MessageSquare,
  Sparkles,
} from "lucide-react";

interface OverviewMetrics {
  income: number;
  expenses: number;
  net_profit: number;
  outstanding: number;
  leads: number;
  active_agents: number;
}

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<OverviewMetrics>({
    income: 0,
    expenses: 0,
    net_profit: 0,
    outstanding: 0,
    leads: 0,
    active_agents: 0,
  });
  const [tenant, setTenant] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }

    const currentTenant = getActiveTenant();
    if (!currentTenant) {
      window.location.href = "/onboarding";
      return;
    }

    setTenant(currentTenant);

    // Fetch real overview metrics for active tenant
    apiRequest(`/api/v1/tenants/${currentTenant.id}/overview`)
      .then((res) => {
        if (res.success && res.data?.metrics) {
          setMetrics(res.data.metrics);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />

      <div className="flex flex-1">
        <Sidebar currentPath="/dashboard" />

        <main className="flex-1 p-6 sm:p-8 space-y-8 max-w-7xl mx-auto w-full">
          {/* Header Banner */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-6">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                  {tenant?.name || "Company Overview"}
                </h1>
                <span className="rounded-full bg-emerald-100 text-emerald-800 px-2.5 py-0.5 text-xs font-semibold">
                  Live
                </span>
              </div>
              <p className="mt-1 text-xs sm:text-sm text-slate-500">
                Industry: <span className="font-medium text-slate-700">{tenant?.industry || "Enterprise"}</span> | 
                Role: <span className="font-medium text-slate-700 uppercase">{tenant?.role || "Owner"}</span>
              </p>
            </div>

            <div className="flex items-center gap-3">
              <a
                href="/business"
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-emerald-500 transition"
              >
                <ArrowUpRight className="h-4 w-4" />
                <span>Record Transaction</span>
              </a>
            </div>
          </div>

          {/* Metric Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
            <StatCard
              title="Total Income"
              value={`$${metrics.income.toLocaleString()}`}
              icon={DollarSign}
              badge={{ text: "+12%", variant: "success" }}
              subtext="Confirmed receipts"
            />
            <StatCard
              title="Expenses"
              value={`$${metrics.expenses.toLocaleString()}`}
              icon={Receipt}
              badge={{ text: "Normal", variant: "neutral" }}
              subtext="Operating costs"
            />
            <StatCard
              title="Net Cashflow"
              value={`$${metrics.net_profit.toLocaleString()}`}
              icon={TrendingUp}
              badge={{
                text: metrics.net_profit >= 0 ? "Positive" : "Deficit",
                variant: metrics.net_profit >= 0 ? "success" : "danger",
              }}
              subtext="Income - Expenses"
            />
            <StatCard
              title="Outstanding"
              value={`$${metrics.outstanding.toLocaleString()}`}
              icon={AlertTriangle}
              badge={{ text: "Pending", variant: "warning" }}
              subtext="Receivables"
            />
            <StatCard
              title="Total Leads"
              value={metrics.leads}
              icon={Users}
              badge={{ text: "Active", variant: "success" }}
              subtext="CRM pipeline"
            />
            <StatCard
              title="Active Agents"
              value={metrics.active_agents}
              icon={Bot}
              badge={{ text: "Protected", variant: "success" }}
              subtext="Circuit Breaker ON"
            />
          </div>

          {/* Core Feature Hub Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* WhatsApp Integration Hub Card */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-100">
                    <MessageSquare className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900 text-sm">WhatsApp Business Hub</h3>
                    <p className="text-xs text-slate-500">Automated transaction extraction</p>
                  </div>
                </div>
                <span className="rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5">
                  Active
                </span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                Connect your WhatsApp Business number to receive voice/text rent confirmations,
                auto-extract ledger entries, and send payment reminders.
              </p>

              <div className="rounded-lg bg-slate-50 p-3 border border-slate-100 text-xs text-slate-600">
                <span className="font-medium text-slate-800">Example format:</span>
                <p className="italic text-slate-500 mt-0.5">
                  "Received 75,000 rent from Flat 4B for November."
                </p>
              </div>

              <a
                href="/settings"
                className="block text-center rounded-lg border border-slate-200 bg-white py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
              >
                Manage WhatsApp Connection
              </a>
            </div>

            {/* AI Multi-Agent Orchestration Card */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600 border border-blue-100">
                    <Bot className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900 text-sm">Autonomous Agent Hierarchy</h3>
                    <p className="text-xs text-slate-500">OpenRouter Smart Model Tiering</p>
                  </div>
                </div>
                <span className="rounded-full bg-blue-100 text-blue-800 text-[10px] font-bold px-2 py-0.5">
                  Bounded
                </span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                All agent tasks are strictly bounded. Routine replies use Gemini Flash / GPT-4o Mini,
                while audits and planning route to Claude 3.5 Sonnet.
              </p>

              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between py-1 border-b border-slate-100">
                  <span className="text-slate-600">Master Router Agent</span>
                  <span className="text-emerald-600 font-medium">Ready</span>
                </div>
                <div className="flex items-center justify-between py-1 border-b border-slate-100">
                  <span className="text-slate-600">Reviewer Validation Agent</span>
                  <span className="text-emerald-600 font-medium">Enforced</span>
                </div>
                <div className="flex items-center justify-between py-1">
                  <span className="text-slate-600">Cost Circuit Breaker</span>
                  <span className="text-emerald-600 font-medium">Active (3-fail lock)</span>
                </div>
              </div>

              <button
                disabled
                className="w-full rounded-lg bg-slate-100 py-2 text-xs font-semibold text-slate-500 cursor-not-allowed"
              >
                Tool Permissions Locked to Role
              </button>
            </div>

            {/* Marketing & Growth Card */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50 text-purple-600 border border-purple-100">
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900 text-sm">Marketing & Growth</h3>
                    <p className="text-xs text-slate-500">Campaigns & Lead Scoring</p>
                  </div>
                </div>
                <span className="rounded-full bg-purple-100 text-purple-800 text-[10px] font-bold px-2 py-0.5">
                  Self-Service
                </span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                Generate market research, draft content, and qualify incoming leads.
                External ad publication strictly requires Human Approval.
              </p>

              <div className="rounded-lg bg-purple-50/50 p-3 border border-purple-100 text-xs text-purple-900">
                <p className="font-semibold">Human Approval Gate:</p>
                <p className="text-[11px] text-purple-700 mt-0.5">
                  No budget is spent and no public ads run without explicit Owner sign-off.
                </p>
              </div>

              <a
                href="/marketing"
                className="block text-center rounded-lg border border-slate-200 bg-white py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
              >
                Open Marketing Engine
              </a>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
