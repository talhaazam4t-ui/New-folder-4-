"use client";

import React from "react";
import {
  LayoutDashboard,
  CreditCard,
  Settings,
  TrendingUp,
  Sparkles,
  MessageSquare,
  ShieldCheck,
  Megaphone,
} from "lucide-react";
import { SUPPORT_WHATSAPP_NUMBER, SUPPORT_WHATSAPP_LINK } from "@/lib/auth";

interface SidebarProps {
  currentPath?: string;
}

export function Sidebar({ currentPath = "/dashboard" }: SidebarProps) {
  // Pure Done-For-You Managed Service navigation for Clients
  // Completely separate from Admin operations
  const clientNavItems = [
    { label: "Performance Overview", href: "/dashboard", icon: LayoutDashboard },
    { label: "Onboarding & Connections", href: "/onboarding", icon: Sparkles },
    { label: "Services & Packages", href: "/billing", icon: CreditCard },
    { label: "Financial Results", href: "/finance", icon: TrendingUp },
    { label: "Marketing & Leads", href: "/marketing", icon: Megaphone },
    { label: "Integrations & Account", href: "/settings", icon: Settings },
  ];

  return (
    <aside className="w-64 border-r border-slate-200 bg-white min-h-[calc(100vh-4rem)] p-4 flex flex-col justify-between hidden md:flex">
      <div className="space-y-6">
        <div className="space-y-1">
          <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Client Portal Menu
          </p>
          <nav className="space-y-1 mt-2">
            {clientNavItems.map((item) => {
              const Icon = item.icon;
              const isActive =
                currentPath === item.href ||
                (item.href === "/finance" && currentPath === "/business");
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

        {/* WhatsApp Services Assistance Card */}
        <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-3.5 text-xs text-emerald-950 space-y-2">
          <div className="flex items-center gap-2 text-emerald-800 font-semibold">
            <MessageSquare className="h-4 w-4 text-emerald-600" />
            <span>Dedicated Support</span>
          </div>
          <p className="text-[11px] text-emerald-800/80 leading-relaxed">
            Need customized workflow modifications or quick assistance?
          </p>
          <a
            href={SUPPORT_WHATSAPP_LINK}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-center rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-emerald-500 transition"
          >
            WhatsApp: {SUPPORT_WHATSAPP_NUMBER}
          </a>
        </div>
      </div>

      {/* Managed Service Assurance Footer */}
      <div className="rounded-xl bg-slate-900 p-4 text-white">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          <p className="text-xs font-semibold">Managed AI Guarantee</p>
        </div>
        <p className="mt-1 text-[11px] text-slate-400 leading-relaxed">
          Zero complex code or agent debugging required. Fully handled for your business.
        </p>
      </div>
    </aside>
  );
}
