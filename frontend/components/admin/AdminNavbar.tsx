"use client";

import React, { useEffect, useState } from "react";
import { getCurrentUser, clearSession, UserSession } from "@/lib/auth";
import { LogOut, Terminal, Activity, Menu } from "lucide-react";

export interface AdminNavbarProps {
  onMenuClick?: () => void;
}

export function AdminNavbar({ onMenuClick }: AdminNavbarProps = {}) {
  const [user, setUser] = useState<UserSession | null>(null);

  useEffect(() => {
    setUser(getCurrentUser());
  }, []);

  const handleLogout = () => {
    clearSession();
    window.location.href = "/login";
  };

  const handleToggleAdminSidebar = () => {
    if (onMenuClick) {
      onMenuClick();
    } else if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("talox:toggle-admin-sidebar"));
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-800 bg-slate-950 px-4 sm:px-6 shadow-md text-slate-100">
      <div className="flex items-center gap-3 sm:gap-4 min-w-0">
        <button
          type="button"
          onClick={handleToggleAdminSidebar}
          aria-label="Open admin navigation"
          className="md:hidden inline-flex items-center justify-center rounded-lg border border-slate-800 bg-slate-900 p-2 text-slate-300 hover:bg-slate-800 hover:text-white transition"
        >
          <Menu className="h-5 w-5" />
        </button>

        <div className="flex items-center gap-2.5 shrink-0">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500 text-slate-950 font-black text-lg shadow-md shadow-amber-500/20">
            A
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base sm:text-lg font-bold tracking-tight text-white">
                Teloxtech
              </span>
              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-400 border border-amber-500/30">
                Admin Portal
              </span>
            </div>
            <p className="hidden sm:block text-[10px] text-slate-500">
              Sole Platform Administration
            </p>
          </div>
        </div>

        <div className="hidden lg:flex items-center gap-2 ml-4 pl-4 border-l border-slate-800 text-xs text-slate-400">
          <Terminal className="h-3.5 w-3.5 text-emerald-400" />
          <span>Operational Control Engine Active</span>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        <div className="hidden sm:flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-400 border border-emerald-500/20">
          <Activity className="h-3.5 w-3.5 animate-pulse text-emerald-400" />
          <span>Cluster Healthy</span>
        </div>

        <div className="flex items-center gap-2 sm:gap-3 pl-2 border-l border-slate-800">
          <div className="text-right hidden sm:block">
            <p className="text-xs font-semibold text-white">
              {user?.fullName || "Platform Owner"}
            </p>
            <p className="text-[11px] text-amber-400 font-mono">
              {user?.email || "Platform Owner"}
            </p>
          </div>

          <button
            onClick={handleLogout}
            title="Sign Out of Admin Console"
            className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-red-500/10 hover:border-red-500/30 hover:text-red-400 transition"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Sign Out</span>
          </button>
        </div>
      </div>
    </header>
  );
}
