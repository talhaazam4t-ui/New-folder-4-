"use client";

import React, { useEffect, useState } from "react";
import {
  getCurrentUser,
  getActiveTenant,
  clearSession,
  UserSession,
  ActiveTenant,
  SUPPORT_WHATSAPP_NUMBER,
  SUPPORT_WHATSAPP_LINK,
} from "@/lib/auth";
import { LogOut, Building2, User, ShieldCheck, MessageSquare, Menu, LifeBuoy } from "lucide-react";
import { SupportRequestModal } from "@/components/shared/SupportRequestModal";

export interface NavbarProps {
  onMenuClick?: () => void;
}

export function Navbar({ onMenuClick }: NavbarProps = {}) {
  const [user, setUser] = useState<UserSession | null>(null);
  const [tenant, setTenant] = useState<ActiveTenant | null>(null);
  const [supportOpen, setSupportOpen] = useState(false);

  useEffect(() => {
    setUser(getCurrentUser());
    setTenant(getActiveTenant());
  }, []);

  const handleLogout = () => {
    clearSession();
    window.location.href = "/login";
  };

  const handleToggleSidebar = () => {
    if (onMenuClick) {
      onMenuClick();
    } else if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("talox:toggle-sidebar"));
    }
  };

  return (
    <>
      <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-6 shadow-sm">
        {/* Mobile Hamburger + Brand & Active Workspace */}
        <div className="flex items-center gap-3 sm:gap-4 min-w-0">
          <button
            type="button"
            onClick={handleToggleSidebar}
            aria-label="Open navigation menu"
            className="md:hidden inline-flex items-center justify-center rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition"
          >
            <Menu className="h-5 w-5" />
          </button>

          <a href="/dashboard" className="flex items-center gap-2 shrink-0">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-600 text-white font-bold text-lg shadow-sm">
              T
            </div>
            <div className="flex items-center">
              <span className="text-base sm:text-lg font-bold tracking-tight text-slate-900">
                Teloxtech
              </span>
              <span className="ml-1.5 hidden sm:inline rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-emerald-700 border border-emerald-200">
                Client Portal
              </span>
            </div>
          </a>

          {tenant && (
            <div className="hidden sm:flex items-center gap-2 ml-2 pl-3 border-l border-slate-200 text-sm text-slate-600 min-w-0">
              <Building2 className="h-4 w-4 text-slate-400 shrink-0" />
              <span className="font-medium text-slate-800 truncate max-w-[140px]">
                {tenant.name}
              </span>
              {tenant.industry && (
                <span className="hidden lg:inline-block rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 border border-emerald-200">
                  {tenant.industry}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Right Controls: Support Modal Trigger, WhatsApp Quick Contact & Session Profile */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <button
            type="button"
            onClick={() => setSupportOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 sm:px-3 py-1.5 text-xs font-medium text-slate-700 border border-slate-200 hover:bg-slate-200 transition"
            title="Submit Support Request"
          >
            <LifeBuoy className="h-3.5 w-3.5 text-emerald-600" />
            <span className="hidden sm:inline">Support</span>
          </button>

          {/* Direct WhatsApp Services Contact */}
          <a
            href={SUPPORT_WHATSAPP_LINK}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden lg:flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-800 border border-emerald-200 hover:bg-emerald-100 transition"
            title="Direct WhatsApp Client Support"
          >
            <MessageSquare className="h-3.5 w-3.5 text-emerald-600" />
            <span>Services WhatsApp: {SUPPORT_WHATSAPP_NUMBER}</span>
          </a>

          <div className="hidden md:flex items-center gap-1.5 rounded-full bg-slate-50 px-2.5 py-1 text-xs text-slate-600 border border-slate-200">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
            <span>Secure Session</span>
          </div>

          {user && (
            <div className="flex items-center gap-2 sm:gap-3 pl-2 border-l border-slate-200">
              <div className="flex items-center gap-2 text-right">
                <div className="hidden lg:block">
                  <p className="text-xs font-semibold text-slate-800">{user.fullName}</p>
                  <p className="text-[11px] text-slate-500">{user.email}</p>
                </div>
                <div className="hidden sm:flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-700">
                  <User className="h-4 w-4" />
                </div>
              </div>

              <button
                onClick={handleLogout}
                title="Sign Out"
                className="flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </header>

      <SupportRequestModal isOpen={supportOpen} onClose={() => setSupportOpen(false)} />
    </>
  );
}
