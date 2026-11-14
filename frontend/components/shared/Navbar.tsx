"use client";

import React, { useEffect, useState } from "react";
import {
  getCurrentUser,
  getActiveTenant,
  clearSession,
  isSuperAdminUser,
  UserSession,
  ActiveTenant,
} from "@/lib/auth";
import { LogOut, Building2, User, ShieldCheck, ShieldAlert } from "lucide-react";

export function Navbar() {
  const [user, setUser] = useState<UserSession | null>(null);
  const [tenant, setTenant] = useState<ActiveTenant | null>(null);
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);

  useEffect(() => {
    setUser(getCurrentUser());
    setTenant(getActiveTenant());
    setIsSuperAdmin(isSuperAdminUser());
  }, []);

  const handleLogout = () => {
    clearSession();
    window.location.href = "/login";
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-200 bg-white px-6 shadow-sm">
      <div className="flex items-center gap-4">
        <a href={isSuperAdmin ? "/admin" : "/dashboard"} className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-600 text-white font-bold text-lg shadow-sm">
            T
          </div>
          <div>
            <span className="text-lg font-bold tracking-tight text-slate-900">Talox</span>
            <span className="ml-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-emerald-700 border border-emerald-200">
              Managed AI
            </span>
          </div>
        </a>

        {tenant && (
          <div className="hidden sm:flex items-center gap-2 ml-4 pl-4 border-l border-slate-200 text-sm text-slate-600">
            <Building2 className="h-4 w-4 text-slate-400" />
            <span className="font-medium text-slate-800">{tenant.name}</span>
            {tenant.industry && (
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 border border-emerald-200">
                {tenant.industry}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-4">
        {isSuperAdmin ? (
          <a
            href="/admin"
            className="hidden md:flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800 border border-amber-200 hover:bg-amber-100 transition"
          >
            <ShieldAlert className="h-3.5 w-3.5 text-amber-600" />
            <span>Platform Owner Mode</span>
          </a>
        ) : (
          <div className="hidden md:flex items-center gap-1.5 rounded-full bg-slate-50 px-3 py-1 text-xs text-slate-600 border border-slate-200">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
            <span>Tenant Isolated</span>
          </div>
        )}

        {user && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-right">
              <div className="hidden sm:block">
                <p className="text-xs font-semibold text-slate-800">{user.fullName}</p>
                <p className="text-[11px] text-slate-500">{user.email}</p>
              </div>
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-700">
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
  );
}
