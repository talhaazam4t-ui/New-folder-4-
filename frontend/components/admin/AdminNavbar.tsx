"use client";

import React, { useEffect, useState } from "react";
import { getCurrentUser, clearSession, UserSession } from "@/lib/auth";
import { ShieldAlert, LogOut, Terminal, Activity } from "lucide-react";

export function AdminNavbar() {
  const [user, setUser] = useState<UserSession | null>(null);

  useEffect(() => {
    setUser(getCurrentUser());
  }, []);

  const handleLogout = () => {
    clearSession();
    window.location.href = "/login";
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-800 bg-slate-950 px-6 shadow-md text-slate-100">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500 text-slate-950 font-black text-lg shadow-md shadow-amber-500/20">
            A
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold tracking-tight text-white">Teloxtech</span>
              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-400 border border-amber-500/30">
                Admin Portal
              </span>
            </div>
            <p className="text-[10px] text-slate-500">Sole Platform Administration</p>
          </div>
        </div>

        <div className="hidden md:flex items-center gap-2 ml-4 pl-4 border-l border-slate-800 text-xs text-slate-400">
          <Terminal className="h-3.5 w-3.5 text-emerald-400" />
          <span>Operational Control Engine Active</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-400 border border-emerald-500/20">
          <Activity className="h-3.5 w-3.5 animate-pulse text-emerald-400" />
          <span>Cluster Healthy</span>
        </div>

        <div className="flex items-center gap-3 pl-2 border-l border-slate-800">
          <div className="text-right hidden sm:block">
            <p className="text-xs font-semibold text-white">
              {user?.fullName || "Platform Owner"}
            </p>
            <p className="text-[11px] text-amber-400 font-mono">
              {user?.email || "talhazam4@gmail.com"}
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
