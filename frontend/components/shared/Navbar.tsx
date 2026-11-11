"use client";

import React from "react";
import { Building2, LogOut, ShieldCheck, User } from "lucide-react";
import { clearSession, getCurrentUser, getActiveTenant } from "@/lib/auth";

export function Navbar() {
  const user = getCurrentUser();
  const tenant = getActiveTenant();

  const handleLogout = () => {
    clearSession();
    window.location.href = "/login";
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-200 bg-white/80 px-6 backdrop-blur-md">
      <div className="flex items-center gap-4">
        <a href="/dashboard" className="flex items-center gap-2 font-bold text-lg text-slate-900">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600 text-white font-extrabold text-sm shadow-sm">
            T
          </span>
          <span>Talox Stream</span>
        </a>

        {tenant && (
          <div className="hidden sm:flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700">
            <Building2 className="h-3.5 w-3.5 text-slate-500" />
            <span>{tenant.name}</span>
            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800 uppercase">
              {tenant.role}
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        {user && (
          <div className="hidden sm:flex items-center gap-2 text-sm text-slate-700">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-600 border border-slate-200">
              <User className="h-4 w-4" />
            </div>
            <div className="text-left leading-tight">
              <p className="font-medium text-xs text-slate-900">{user.fullName}</p>
              <p className="text-[10px] text-slate-500">{user.email}</p>
            </div>
          </div>
        )}

        <button
          onClick={handleLogout}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition"
          title="Sign Out"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Sign Out</span>
        </button>
      </div>
    </header>
  );
}
