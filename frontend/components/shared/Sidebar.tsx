"use client";

import React, { useEffect, useState } from "react";
import {
  LayoutDashboard,
  CreditCard,
  Settings,
  TrendingUp,
  Sparkles,
  MessageSquare,
  ShieldCheck,
  Megaphone,
  Bot,
  PhoneCall,
  X,
  LifeBuoy,
} from "lucide-react";
import { SUPPORT_WHATSAPP_NUMBER, SUPPORT_WHATSAPP_LINK } from "@/lib/auth";
import { SupportRequestModal } from "@/components/shared/SupportRequestModal";

export interface SidebarProps {
  currentPath?: string;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export function Sidebar({
  currentPath = "/dashboard",
  mobileOpen,
  onMobileClose,
}: SidebarProps) {
  const [internalMobileOpen, setInternalMobileOpen] = useState(false);
  const [supportModalOpen, setSupportModalOpen] = useState(false);

  const isDrawerOpen = mobileOpen !== undefined ? mobileOpen : internalMobileOpen;

  const closeDrawer = () => {
    setInternalMobileOpen(false);
    if (onMobileClose) onMobileClose();
  };

  useEffect(() => {
    const handleToggle = () => {
      setInternalMobileOpen((prev) => !prev);
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setInternalMobileOpen(false);
        if (onMobileClose) onMobileClose();
      }
    };
    window.addEventListener("talox:toggle-sidebar", handleToggle);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("talox:toggle-sidebar", handleToggle);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onMobileClose]);

  // Pure Done-For-You Managed Service navigation for Clients
  // Completely separate from Admin operations
  const clientNavItems = [
    { label: "Performance Overview", href: "/dashboard", icon: LayoutDashboard },
    { label: "Onboarding & Connections", href: "/onboarding", icon: Sparkles },
    { label: "Services & Packages", href: "/billing", icon: CreditCard },
    { label: "Financial Results", href: "/finance", icon: TrendingUp },
    { label: "Marketing & Leads", href: "/marketing", icon: Megaphone },
    { label: "Office Receptionist", href: "/receptionist", icon: PhoneCall },
    { label: "AI Agents & Approvals", href: "/agents", icon: Bot },
    { label: "Integrations & Account", href: "/settings", icon: Settings },
  ];

  const renderSidebarBody = (isMobile = false) => (
    <div className="flex flex-col justify-between h-full space-y-6">
      <div className="space-y-6">
        <div className="space-y-1">
          <div className="flex items-center justify-between px-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Client Portal Menu
            </p>
            {isMobile && (
              <button
                type="button"
                onClick={closeDrawer}
                aria-label="Close navigation menu"
                className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
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
                  onClick={() => {
                    if (isMobile) closeDrawer();
                  }}
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

        {/* Dedicated Support & WhatsApp Services Assistance Card */}
        <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-3.5 text-xs text-emerald-950 space-y-2">
          <div className="flex items-center gap-2 text-emerald-800 font-semibold">
            <MessageSquare className="h-4 w-4 text-emerald-600" />
            <span>Dedicated Support</span>
          </div>
          <p className="text-[11px] text-emerald-800/80 leading-relaxed">
            Need customized workflow modifications or quick assistance?
          </p>
          <button
            type="button"
            onClick={() => {
              if (isMobile) closeDrawer();
              setSupportModalOpen(true);
            }}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-semibold text-emerald-800 hover:bg-emerald-100/60 transition"
          >
            <LifeBuoy className="h-3.5 w-3.5 text-emerald-600" />
            <span>Request Support</span>
          </button>
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
    </div>
  );

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="w-64 shrink-0 border-r border-slate-200 bg-white min-h-[calc(100vh-4rem)] p-4 hidden md:flex flex-col justify-between">
        {renderSidebarBody(false)}
      </aside>

      {/* Mobile Slide-Over Drawer */}
      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          <div
            className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs"
            onClick={closeDrawer}
            aria-hidden="true"
          />
          <aside className="relative z-10 w-72 max-w-[85vw] h-full bg-white border-r border-slate-200 p-4 overflow-y-auto shadow-2xl">
            {renderSidebarBody(true)}
          </aside>
        </div>
      )}

      <SupportRequestModal
        isOpen={supportModalOpen}
        onClose={() => setSupportModalOpen(false)}
      />
    </>
  );
}
