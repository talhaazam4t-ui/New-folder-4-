"use client";

import React, { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import {
  setAuthToken,
  setCurrentUser,
  setActiveTenant,
  getAuthToken,
  getCurrentUser,
  getActiveTenant,
  clearSession,
  isSoleAdminEmail,
  isSuperAdminUser,
  SUPPORT_WHATSAPP_NUMBER,
  SUPPORT_WHATSAPP_LINK,
} from "@/lib/auth";
import { Lock, Mail, ArrowRight, AlertCircle, ShieldCheck, Check, MessageSquare } from "lucide-react";
import { TurnstileWidget } from "@/components/shared/TurnstileWidget";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [autoRedirecting, setAutoRedirecting] = useState(false);

  // Client Session Persistence Check: validate token against /auth/me before redirecting
  useEffect(() => {
    const token = getAuthToken();
    const user = getCurrentUser();
    if (!token || !user) return;

    let cancelled = false;
    setAutoRedirecting(true);

    (async () => {
      try {
        const meRes = await apiRequest("/api/v1/auth/me");
        if (cancelled) return;

        const meEmail = meRes.email || meRes.data?.email;
        if (!meEmail || meRes.error) {
          clearSession();
          setAutoRedirecting(false);
          return;
        }

        const isAdmin =
          Boolean(meRes.is_super_admin ?? meRes.data?.is_super_admin) ||
          isSuperAdminUser() ||
          isSoleAdminEmail(meEmail);

        if (isAdmin) {
          window.location.href = "/admin";
          return;
        }

        if (!getActiveTenant()) {
          const tenantsRes = await apiRequest("/api/v1/tenants");
          if (tenantsRes.error) {
            setAutoRedirecting(false);
            setError(tenantsRes.error.message || "Failed to load workspace list.");
            return;
          }
          const list = Array.isArray(tenantsRes)
            ? tenantsRes
            : Array.isArray(tenantsRes.data)
              ? tenantsRes.data
              : [];
          if (list.length > 0) {
            setActiveTenant(list[0], Boolean(user.rememberMe ?? true));
            window.location.href = "/dashboard";
          } else {
            window.location.href = "/onboarding";
          }
          return;
        }

        window.location.href = "/dashboard";
      } catch {
        if (!cancelled) {
          clearSession();
          setAutoRedirecting(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await apiRequest("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          password,
          turnstile_token: turnstileToken,
        }),
      });

      if (!res.access_token && !res.data?.access_token) {
        setError(res.error?.message || "Invalid email or password");
        setLoading(false);
        return;
      }

      const token = res.access_token || res.data?.access_token;
      const userId = res.user_id || res.data?.user_id;
      const fullName = res.full_name || res.data?.full_name;
      const isSoleAdmin = isSoleAdminEmail(email);
      const isSuperAdmin = Boolean(res.is_super_admin ?? res.data?.is_super_admin) || isSoleAdmin;

      // Clear any prior session before writing new credentials
      clearSession();

      // Persist session securely for client persistence across visits
      setAuthToken(token, rememberMe);
      setCurrentUser(
        {
          userId,
          email: email.trim().toLowerCase(),
          fullName,
          token,
          isSuperAdmin,
          rememberMe,
        },
        rememberMe
      );

      // Dedicated Admin Routing vs Client Routing (Strict Portal Separation)
      if (isSuperAdmin || isSoleAdmin) {
        // Platform Super Admin routes directly and exclusively to Admin Dashboard
        window.location.href = "/admin";
        return;
      }

      // Fetch user's client tenants
      const tenantsRes = await apiRequest("/api/v1/tenants", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (tenantsRes.error) {
        setError(tenantsRes.error.message || "Failed to load client workspaces. Please try again.");
        return;
      }

      const list = Array.isArray(tenantsRes)
        ? tenantsRes
        : Array.isArray(tenantsRes.data)
          ? tenantsRes.data
          : [];

      if (list.length > 0) {
        setActiveTenant(list[0], rememberMe);
        window.location.href = "/dashboard";
      } else {
        window.location.href = "/onboarding";
      }
    } catch (err: any) {
      setError(err.message || "Failed to sign in. Please verify your credentials.");
    } finally {
      setLoading(false);
    }
  };

  if (autoRedirecting) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4 text-slate-100">
        <div className="text-center space-y-3">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
          <p className="text-sm text-slate-400">Remembered session active. Restoring portal...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4 py-12 text-slate-100">
      <div className="w-full max-w-md space-y-8 rounded-2xl border border-slate-800 bg-slate-950 p-8 shadow-2xl">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500 text-white font-extrabold text-xl shadow-lg shadow-emerald-500/20">
            T
          </div>
          <h2 className="mt-4 text-2xl font-bold tracking-tight text-white">
            Sign In to Teloxtech SaaS
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Autonomous Multi-Tenant Automation Platform
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-400">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300">Email Address</label>
            <div className="relative mt-1">
              <Mail className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300">Password</label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>

          <div className="flex items-center justify-between text-xs">
            <label className="flex items-center gap-2 text-slate-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-emerald-500 focus:ring-emerald-500 focus:ring-offset-slate-950"
              />
              <span>Remember me (Persistent Session)</span>
            </label>
            <a href="/forgot-password" className="text-emerald-400 hover:text-emerald-300 font-medium">
              Forgot Password?
            </a>
          </div>

          <TurnstileWidget onTokenChange={setTurnstileToken} />

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white shadow-md hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-slate-950 disabled:opacity-50 transition"
          >
            {loading ? "Authenticating..." : "Sign In"}
            <ArrowRight className="h-4 w-4" />
          </button>
        </form>

        <div className="border-t border-slate-800/80 pt-4 space-y-3">
          <div className="text-center text-xs text-slate-400">
            Don&apos;t have an account?{" "}
            <a href="/register" className="font-medium text-emerald-400 hover:text-emerald-300">
              Create a Client Account
            </a>
          </div>

          <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-3 text-center">
            <p className="text-xs text-slate-400">
              Need assistance or service onboarding?
            </p>
            <a
              href={SUPPORT_WHATSAPP_LINK}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1.5 inline-flex items-center gap-2 text-xs font-semibold text-emerald-400 hover:text-emerald-300"
            >
              <MessageSquare className="h-3.5 w-3.5" />
              <span>WhatsApp Services Support: {SUPPORT_WHATSAPP_NUMBER}</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
