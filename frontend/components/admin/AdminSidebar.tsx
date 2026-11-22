"use client";

import React, { useEffect, useState } from "react";
import {
  ShieldAlert,
  Building2,
  Cpu,
  Layers,
  Megaphone,
  Link2,
  CheckCheck,
  Activity,
  PhoneCall,
  LogOut,
  Users,
  Terminal,
  X,
} from "lucide-react";
import { clearSession, getCurrentUser, UserSession } from "@/lib/auth";

export interface AdminSidebarProps {
  currentPath?: string;
  activeTab?: string;
  onTabChange?: (tab: string) => void;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export function AdminSidebar({
  currentPath = "/admin",
  activeTab,
  onTabChange,
  mobileOpen,
  onMobileClose,
}: AdminSidebarProps) {
  const [internalMobileOpen, setInternalMobileOpen] = useState(false);
  const [user, setUser] = useState<UserSession | null>(null);

  const isDrawerOpen = mobileOpen !== undefined ? mobileOpen : internalMobileOpen;

  const closeDrawer = () => {
    setInternalMobileOpen(false);
    if (onMobileClose) onMobileClose();
  };

  useEffect(() => {
    setUser(getCurrentUser());
  }, []);

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
    window.addEventListener("talox:toggle-admin-sidebar", handleToggle);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("talox:toggle-admin-sidebar", handleToggle);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onMobileClose]);

  const effectiveTab =
    activeTab !== undefined ? activeTab : currentPath === "/agents" ? "" : "platform";
  const adminItems = [
    { id: "platform", label: "Global Overview", icon: ShieldAlert },
    { id: "tenants", label: "Tenant Directory", icon: Building2 },
    { id: "services", label: "Service Catalog", icon: Layers },
    { id: "agents", label: "Agent Controls", icon: Cpu },
    { id: "leads", label: "Lead Gen & Outreach", icon: Megaphone },
    { id: "integrations", label: "Integrations & OAuth", icon: Link2 },
    { id: "voice_settings", label: "Voice AI Settings", icon: PhoneCall },
    { id: "approvals", label: "Approval Center", icon: CheckCheck },
    { id: "monitoring", label: "System Health & Logs", icon: Activity },
  ];

  const handleAdminLogout = () => {
    clearSession();
    window.location.href = "/login";
  };

  const renderSidebarBody = (isMobile = false) => (
    <div className="flex flex-col justify-between h-full space-y-6">
      <div className="space-y-6">
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold uppercase tracking-wider">
              <ShieldAlert className="h-3.5 w-3.5" />
              <span>Sole Admin Console</span>
            </div>
            {isMobile && (
              <button
                type="button"
                onClick={closeDrawer}
                aria-label="Close admin navigation"
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          <nav className="space-y-1 mt-4">
            {adminItems.map((item) => {
              const Icon = item.icon;
              const isActive = currentPath === "/admin" && effectiveTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    if (isMobile) closeDrawer();
                    if (onTabChange) {
                      onTabChange(item.id);
                    } else {
                      window.location.href =
                        item.id === "platform" ? "/admin" : `/admin?tab=${item.id}`;
                    }
                  }}
                  type="button"
                  className={`w-full text-left flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    isActive
                      ? "bg-slate-800 text-white font-semibold border-l-2 border-emerald-500"
                      : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                  }`}
                >
                  <Icon
                    className={`h-4 w-4 ${isActive ? "text-emerald-400" : "text-slate-500"}`}
                  />
                  <span>{item.label}</span>
                </button>
              );
            })}

            <div className="pt-2 mt-2 border-t border-slate-800/80">
              <a
                href="/agents"
                onClick={() => {
                  if (isMobile) closeDrawer();
                }}
                className={`w-full flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  currentPath === "/agents"
                    ? "bg-slate-800 text-white font-semibold border-l-2 border-emerald-500"
                    : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                }`}
              >
                <Terminal
                  className={`h-4 w-4 ${
                    currentPath === "/agents" ? "text-emerald-400" : "text-slate-500"
                  }`}
                />
                <span>Agent Orchestrator</span>
              </a>
            </div>
          </nav>
        </div>

        <div className="rounded-lg bg-slate-900/90 border border-slate-800 p-3 space-y-1.5 text-xs">
          <div className="flex items-center gap-2 text-slate-200 font-semibold">
            <Users className="h-3.5 w-3.5 text-emerald-400" />
            <span>Admin Authorization</span>
          </div>
          <p className="text-[11px] text-slate-400 break-all">
            {user?.email || "Platform Owner"}
          </p>
          <div className="pt-1">
            <span className="inline-block rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-500/20">
              Exclusive Platform Owner
            </span>
          </div>
        </div>
      </div>

      <div className="border-t border-slate-800/80 pt-3">
        <button
          onClick={handleAdminLogout}
          type="button"
          className="w-full flex items-center justify-center gap-2 rounded-lg border border-slate-800 bg-slate-900 p-2 text-xs font-medium text-red-400 hover:bg-red-500/10 hover:border-red-500/30 transition"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span>Exit Admin Portal</span>
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Admin Sidebar */}
      <aside className="w-64 shrink-0 border-r border-slate-800 bg-slate-950 text-slate-300 min-h-[calc(100vh-4rem)] p-4 hidden md:flex flex-col justify-between">
        {renderSidebarBody(false)}
      </aside>

      {/* Mobile Dark Slide-Over Drawer */}
      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          <div
            className="fixed inset-0 bg-slate-950/75 backdrop-blur-xs"
            onClick={closeDrawer}
            aria-hidden="true"
          />
          <aside className="relative z-10 w-72 max-w-[85vw] h-full bg-slate-950 text-slate-300 border-r border-slate-800 p-4 overflow-y-auto shadow-2xl">
            {renderSidebarBody(true)}
          </aside>
        </div>
      )}
    </>
  );
}
