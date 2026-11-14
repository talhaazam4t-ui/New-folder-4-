"use client";

import React, { useEffect, useState } from "react";
import { isSuperAdminUser } from "@/lib/auth";
import {
  LayoutDashboard,
  CreditCard,
  Settings,
  ShieldAlert,
  TrendingUp,
  Cpu,
  Megaphone,
  Sparkles,
  CheckCircle2,
} from "lucide-react";

interface SidebarProps {
  currentPath?: string;
}

export function Sidebar({ currentPath = "/dashboard" }: SidebarProps) {
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);

  useEffect(() => {
    setIsSuperAdmin(isSuperAdminUser());
  }, []);

  // Done-For-You Managed Service navigation for Clients (no internal agent/prompt/workflow config)
  const clientNavItems = [
    { label: "Performance Overview", href: "/dashboard", icon: LayoutDashboard },
    { label: "Onboarding & Connections", href: "/onboarding", icon: Sparkles },
    { label: "Services & Packages", href: "/billing", icon: CreditCard },
    { label: "Financial Results", href: "/business", icon: TrendingUp },
    { label: "Integrations & Account", href: "/settings", icon: Settings },
  ];

  // Additional internal operational views visible only to Platform Super Admin
  const ownerExtraItems = [
    { label: "AI Agent Infrastructure", href: "/agents", icon: Cpu },
    { label: "Outreach Studio", href: "/marketing", icon: Megaphone },
  ];

  const navItems = isSuperAdmin ? [...clientNavItems, ...ownerExtraItems] : clientNavItems;

  return (
    <aside className="w-64 border-r border-slate-200 bg-white min-h-[calc(100vh-4rem)] p-4 flex flex-col justify-between hidden md:flex">
      <div className="space-y-6">
        <div className="space-y-1">
          <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Managed AI Service Portal
          </p>
          <nav className="space-y-1 mt-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = currentPath === item.href;
              return (
                <a
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    isActive
                      ? "bg-emerald-50 text-emerald-700 font-semibold"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  <Icon
                    className={`h-4 w-4 ${isActive ? "text-emerald-600" : "text-slate-400"}`}
                  />
                  {item.label}
                </a>
              );
            })}
          </nav>
        </div>

        {isSuperAdmin && (
          <div className="border-t border-slate-100 pt-4">
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Platform Administration
            </p>
            <nav className="mt-2 space-y-1">
              <a
                href="/admin"
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  currentPath.startsWith("/admin")
                    ? "bg-slate-900 text-white font-semibold"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <ShieldAlert className="h-4 w-4 text-amber-500" />
                Owner Operations Console
              </a>
            </nav>
          </div>
        )}
      </div>

      {/* Managed Service Assurance Footer */}
      <div className="rounded-xl bg-slate-900 p-4 text-white">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          <span className="text-xs font-semibold">Done-For-You AI Service</span>
        </div>
        <p className="mt-1 text-[11px] text-slate-400 leading-relaxed">
          Managed end-to-end by Talox Operations with strict tenant isolation.
        </p>
      </div>
    </aside>
  );
}
