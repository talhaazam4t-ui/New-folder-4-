"use client";

import React from "react";
import {
  LayoutDashboard,
  Receipt,
  MessageSquare,
  TrendingUp,
  Bot,
  CreditCard,
  Settings,
  PlusCircle,
} from "lucide-react";

interface SidebarProps {
  currentPath?: string;
}

export function Sidebar({ currentPath = "/dashboard" }: SidebarProps) {
  const navItems = [
    { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
    { label: "Business Tracking", href: "/business", icon: Receipt },
    { label: "WhatsApp Hub", href: "/settings", icon: MessageSquare },
    { label: "Marketing & Growth", href: "/marketing", icon: TrendingUp },
    { label: "AI Agents", href: "/dashboard", icon: Bot },
    { label: "Billing & Plans", href: "/billing", icon: CreditCard },
    { label: "Settings", href: "/settings", icon: Settings },
  ];

  return (
    <aside className="w-64 border-r border-slate-200 bg-white min-h-[calc(100vh-4rem)] p-4 flex flex-col justify-between hidden md:flex">
      <div className="space-y-6">
        <div className="space-y-1">
          <p className="px-3 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Workspace
          </p>
          <nav className="space-y-1 mt-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = currentPath === item.href;
              return (
                <a
                  key={item.label}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    isActive
                      ? "bg-emerald-50 text-emerald-700"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  <Icon className={`h-4 w-4 ${isActive ? "text-emerald-600" : "text-slate-400"}`} />
                  {item.label}
                </a>
              );
            })}
          </nav>
        </div>

        <div className="border-t border-slate-100 pt-4">
          <a
            href="/onboarding"
            className="flex items-center gap-2 rounded-lg border border-dashed border-slate-300 p-2 text-xs font-medium text-slate-600 hover:border-slate-400 hover:bg-slate-50 transition"
          >
            <PlusCircle className="h-4 w-4 text-slate-400" />
            <span>Create New Company</span>
          </a>
        </div>
      </div>

      <div className="rounded-lg bg-slate-50 p-3 border border-slate-100 text-xs text-slate-500">
        <p className="font-semibold text-slate-700">Talox Tech Stream</p>
        <p className="text-[10px] text-slate-400 mt-0.5">Custom Python Engine Active</p>
      </div>
    </aside>
  );
}
