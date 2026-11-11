"use client";

import React from "react";
import {
  ShieldAlert,
  Building2,
  Cpu,
  Layers,
  CircleDollarSign,
  CheckCheck,
  Activity,
  ArrowLeft,
} from "lucide-react";

interface AdminSidebarProps {
  currentPath?: string;
}

export function AdminSidebar({ currentPath = "/admin" }: AdminSidebarProps) {
  const adminItems = [
    { label: "Global Overview", href: "/admin", icon: ShieldAlert },
    { label: "Tenant Directory", href: "/admin", icon: Building2 },
    { label: "Service Catalog", href: "/admin", icon: Layers },
    { label: "Agent Controls", href: "/admin", icon: Cpu },
    { label: "Financial Ledger", href: "/admin", icon: CircleDollarSign },
    { label: "Approval Center", href: "/admin", icon: CheckCheck },
    { label: "System Health", href: "/admin", icon: Activity },
  ];

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-950 text-slate-300 min-h-[calc(100vh-4rem)] p-4 flex flex-col justify-between hidden md:flex">
      <div className="space-y-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-semibold uppercase tracking-wider">
            <ShieldAlert className="h-3.5 w-3.5" />
            <span>Platform Owner Mode</span>
          </div>

          <nav className="space-y-1 mt-4">
            {adminItems.map((item) => {
              const Icon = item.icon;
              const isActive = currentPath === item.href;
              return (
                <a
                  key={item.label}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    isActive
                      ? "bg-slate-800 text-white font-semibold"
                      : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                  }`}
                >
                  <Icon className={`h-4 w-4 ${isActive ? "text-emerald-400" : "text-slate-500"}`} />
                  {item.label}
                </a>
              );
            })}
          </nav>
        </div>

        <div className="border-t border-slate-800 pt-4">
          <a
            href="/dashboard"
            className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2 text-xs font-medium text-slate-300 hover:bg-slate-800 transition"
          >
            <ArrowLeft className="h-4 w-4 text-slate-400" />
            <span>Return to Client Portal</span>
          </a>
        </div>
      </div>

      <div className="rounded-lg bg-slate-900 p-3 border border-slate-800 text-xs text-slate-400">
        <p className="font-semibold text-slate-200">Server Authorization Path</p>
        <p className="text-[10px] text-slate-500 mt-0.5">Strict Admin Guard Active</p>
      </div>
    </aside>
  );
}
