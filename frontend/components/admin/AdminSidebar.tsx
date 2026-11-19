"use client";

import React from "react";
import {
  ShieldAlert,
  Building2,
  Cpu,
  Layers,
  Megaphone,
  Link2,
  CheckCheck,
  Activity,
  LogOut,
  Users,
  Terminal,
} from "lucide-react";
import { clearSession, getCurrentUser } from "@/lib/auth";

interface AdminSidebarProps {
  currentPath?: string;
  activeTab?: string;
  onTabChange?: (tab: string) => void;
}

export function AdminSidebar({
  currentPath = "/admin",
  activeTab,
  onTabChange,
}: AdminSidebarProps) {
  const effectiveTab = activeTab !== undefined ? activeTab : currentPath === "/agents" ? "" : "platform";
  const adminItems = [
    { id: "platform", label: "Global Overview", icon: ShieldAlert },
    { id: "tenants", label: "Tenant Directory", icon: Building2 },
    { id: "services", label: "Service Catalog", icon: Layers },
    { id: "agents", label: "Agent Controls", icon: Cpu },
    { id: "leads", label: "Lead Gen & Outreach", icon: Megaphone },
    { id: "integrations", label: "Integrations & OAuth", icon: Link2 },
    { id: "approvals", label: "Approval Center", icon: CheckCheck },
    { id: "monitoring", label: "System Health & Logs", icon: Activity },
  ];

  const handleAdminLogout = () => {
    clearSession();
    window.location.href = "/login";
  };

  const user = getCurrentUser();

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-950 text-slate-300 min-h-[calc(100vh-4rem)] p-4 flex flex-col justify-between hidden md:flex">
      <div className="space-y-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold uppercase tracking-wider">
            <ShieldAlert className="h-3.5 w-3.5" />
            <span>Sole Admin Console</span>
          </div>

          <nav className="space-y-1 mt-4">
            {adminItems.map((item) => {
              const Icon = item.icon;
              const isActive = currentPath === "/admin" && effectiveTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    if (onTabChange) {
                      onTabChange(item.id);
                    } else {
                      window.location.href =
                        item.id === "platform" ? "/admin" : `/admin?tab=${item.id}`;
                    }
                  }}
                  type="button"
                  className={`w-full text-left flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    isActive
                      ? "bg-slate-800 text-white font-semibold border-l-2 border-emerald-500"
                      : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                  }`}
                >
                  <Icon className={`h-4 w-4 ${isActive ? "text-emerald-400" : "text-slate-500"}`} />
                  <span>{item.label}</span>
                </button>
              );
            })}

            <div className="pt-2 mt-2 border-t border-slate-800/80">
              <a
                href="/agents"
                className={`w-full flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  currentPath === "/agents"
                    ? "bg-slate-800 text-white font-semibold border-l-2 border-emerald-500"
                    : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                }`}
              >
                <Terminal
                  className={`h-4 w-4 ${
                    currentPath === "/agents" ? "text-emerald-400" : "text-slate-500"
                  }`}
                />
                <span>Agent Orchestrator</span>
              </a>
            </div>
          </nav>
        </div>

        <div className="rounded-lg bg-slate-900/90 border border-slate-800 p-3 space-y-1.5 text-xs">
          <div className="flex items-center gap-2 text-slate-200 font-semibold">
            <Users className="h-3.5 w-3.5 text-emerald-400" />
            <span>Admin Authorization</span>
          </div>
          <p className="text-[11px] text-slate-400 break-all">
            {user?.email || "talhazam4@gmail.com"}
          </p>
          <div className="pt-1">
            <span className="inline-block rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-500/20">
              Exclusive Platform Owner
            </span>
          </div>
        </div>
      </div>

      <div className="border-t border-slate-800/80 pt-3">
        <button
          onClick={handleAdminLogout}
          type="button"
          className="w-full flex items-center justify-center gap-2 rounded-lg border border-slate-800 bg-slate-900 p-2 text-xs font-medium text-red-400 hover:bg-red-500/10 hover:border-red-500/30 transition"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span>Exit Admin Portal</span>
        </button>
      </div>
    </aside>
  );
}
