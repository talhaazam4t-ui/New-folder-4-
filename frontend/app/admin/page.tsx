"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { StatCard } from "@/components/dashboard/StatCard";
import { apiRequest } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import {
  Building2,
  DollarSign,
  Cpu,
  Activity,
  ShieldCheck,
  AlertOctagon,
  Ban,
  CheckCircle,
} from "lucide-react";

interface AdminStats {
  total_tenants: number;
  active_tenants: number;
  suspended_tenants: number;
  monthly_recurring_revenue: number;
  total_collected_payments: number;
  total_agent_executions: number;
  system_health: string;
}

interface TenantItem {
  id: string;
  name: string;
  slug: string;
  industry: string;
  status: string;
  members_count: number;
  created_at: string;
}

export default function AdminPage() {
  const [stats, setStats] = useState<AdminStats>({
    total_tenants: 0,
    active_tenants: 0,
    suspended_tenants: 0,
    monthly_recurring_revenue: 0,
    total_collected_payments: 0,
    total_agent_executions: 0,
    system_health: "checking",
  });
  const [tenants, setTenants] = useState<TenantItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAdminData = async () => {
    try {
      const statsRes = await apiRequest<AdminStats>("/api/v1/admin/stats");
      const rawData = (statsRes.data || statsRes) as AdminStats;
      if (rawData && rawData.total_tenants !== undefined) {
        setStats(rawData);
      } else if (statsRes.error) {
        setError(statsRes.error.message);
      }

      const tenantsRes = await apiRequest("/api/v1/admin/tenants");
      if (tenantsRes.success && tenantsRes.data) {
        setTenants(tenantsRes.data);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load admin telemetry.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    fetchAdminData();
  }, []);

  const handleToggleStatus = async (tenantId: string, currentStatus: string) => {
    const newStatus = currentStatus === "active" ? "suspended" : "active";
    const res = await apiRequest(`/api/v1/admin/tenants/${tenantId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: newStatus }),
    });

    if (res.success) {
      fetchAdminData();
    }
  };

  if (error) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-white p-6">
        <div className="max-w-md text-center space-y-4">
          <AlertOctagon className="h-12 w-12 text-rose-500 mx-auto" />
          <h2 className="text-xl font-bold">Access Denied</h2>
          <p className="text-sm text-slate-400">{error}</p>
          <a
            href="/dashboard"
            className="inline-block rounded-lg bg-slate-800 px-4 py-2 text-xs font-semibold hover:bg-slate-700 transition"
          >
            Return to Client Dashboard
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col">
      <Navbar />

      <div className="flex flex-1">
        <AdminSidebar currentPath="/admin" />

        <main className="flex-1 p-6 sm:p-8 space-y-8 max-w-7xl mx-auto w-full">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-6">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                  Platform Administration Console
                </h1>
                <span className="rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 px-2.5 py-0.5 text-xs font-semibold">
                  Owner Level
                </span>
              </div>
              <p className="mt-1 text-xs sm:text-sm text-slate-400">
                Centralized multi-tenant monitoring, revenue tracking, and security enforcement.
              </p>
            </div>

            <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg">
              <ShieldCheck className="h-4 w-4" />
              <span>Server-Side Authorization Active</span>
            </div>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
            <StatCard
              title="Total Companies"
              value={stats.total_tenants}
              icon={Building2}
              badge={{ text: "Registered", variant: "neutral" }}
              subtext="Platform accounts"
            />
            <StatCard
              title="Active Companies"
              value={stats.active_tenants}
              icon={Building2}
              badge={{ text: "Operational", variant: "success" }}
              subtext="Healthy workspaces"
            />
            <StatCard
              title="Suspended"
              value={stats.suspended_tenants}
              icon={Ban}
              badge={{
                text: stats.suspended_tenants > 0 ? "Review" : "Clean",
                variant: stats.suspended_tenants > 0 ? "warning" : "neutral",
              }}
              subtext="Action required"
            />
            <StatCard
              title="Monthly MRR"
              value={`$${stats.monthly_recurring_revenue.toLocaleString()}`}
              icon={DollarSign}
              badge={{ text: "Recurring", variant: "success" }}
              subtext="Active subscriptions"
            />
            <StatCard
              title="Total Payments"
              value={`$${stats.total_collected_payments.toLocaleString()}`}
              icon={DollarSign}
              badge={{ text: "Settled", variant: "success" }}
              subtext="Lifetime collected"
            />
            <StatCard
              title="Agent Executions"
              value={stats.total_agent_executions}
              icon={Cpu}
              badge={{ text: "All Tenants", variant: "neutral" }}
              subtext="Circuit Breaker Active"
            />
          </div>

          {/* Tenants Directory Table */}
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-white">Registered Companies Directory</h3>
                <p className="text-xs text-slate-400">
                  Manage tenant workspaces, view subscription status, and enforce account suspension.
                </p>
              </div>
              <span className="text-xs text-slate-400 font-mono">
                {tenants.length} Companies Total
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 uppercase font-semibold tracking-wider">
                    <th className="py-3 px-4">Company</th>
                    <th className="py-3 px-4">Handle</th>
                    <th className="py-3 px-4">Industry</th>
                    <th className="py-3 px-4">Members</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Created Date</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  {tenants.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-500">
                        No companies registered yet.
                      </td>
                    </tr>
                  ) : (
                    tenants.map((t) => (
                      <tr key={t.id} className="hover:bg-slate-900/60 transition">
                        <td className="py-3 px-4 font-medium text-white">{t.name}</td>
                        <td className="py-3 px-4 font-mono text-slate-400">{t.slug}</td>
                        <td className="py-3 px-4">{t.industry}</td>
                        <td className="py-3 px-4">{t.members_count} users</td>
                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                              t.status === "active"
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                            }`}
                          >
                            {t.status === "active" ? (
                              <CheckCircle className="h-3 w-3" />
                            ) : (
                              <Ban className="h-3 w-3" />
                            )}
                            {t.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-slate-400">
                          {new Date(t.created_at).toLocaleDateString()}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => handleToggleStatus(t.id, t.status)}
                            className={`rounded px-2.5 py-1 text-[11px] font-semibold transition ${
                              t.status === "active"
                                ? "bg-rose-600/20 text-rose-400 hover:bg-rose-600/30 border border-rose-500/30"
                                : "bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30 border border-emerald-500/30"
                            }`}
                          >
                            {t.status === "active" ? "Suspend Account" : "Reactivate"}
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
