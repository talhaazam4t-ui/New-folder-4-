"use client";

import React, { useState } from "react";
import { apiRequest } from "@/lib/api";
import { setAuthToken, setCurrentUser, setActiveTenant } from "@/lib/auth";
import { Lock, Mail, ArrowRight, AlertCircle } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await apiRequest("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });

      if (!res.access_token && !res.data?.access_token) {
        setError(res.error?.message || "Invalid email or password");
        setLoading(false);
        return;
      }

      const token = res.access_token || res.data?.access_token;
      const userId = res.user_id || res.data?.user_id;
      const fullName = res.full_name || res.data?.full_name;
      const isSuperAdmin = Boolean(res.is_super_admin ?? res.data?.is_super_admin);

      setAuthToken(token);
      setCurrentUser({
        userId,
        email,
        fullName,
        token,
        isSuperAdmin,
      });

      // Fetch user's tenants
      const tenantsRes = await apiRequest("/api/v1/tenants", {
        headers: { Authorization: `Bearer ${token}` },
      });

      const list = Array.isArray(tenantsRes)
        ? tenantsRes
        : Array.isArray(tenantsRes.data)
          ? tenantsRes.data
          : [];

      if (list.length > 0) {
        setActiveTenant(list[0]);
      }

      if (isSuperAdmin) {
        window.location.href = "/admin";
      } else if (list.length > 0) {
        window.location.href = "/dashboard";
      } else {
        window.location.href = "/onboarding";
      }
    } catch (err: any) {
      setError(err.message || "Failed to sign in. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4 py-12 text-slate-100">
      <div className="w-full max-w-md space-y-8 rounded-2xl border border-slate-800 bg-slate-950 p-8 shadow-2xl">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500 text-white font-extrabold text-xl shadow-lg shadow-emerald-500/20">
            T
          </div>
          <h2 className="mt-4 text-2xl font-bold tracking-tight text-white">
            Sign In to Talox Tech Stream
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Done-For-You Managed AI Automation Platform
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
                placeholder="name@company.com"
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

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white shadow-md hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-slate-950 disabled:opacity-50 transition"
          >
            {loading ? "Authenticating..." : "Sign In"}
            <ArrowRight className="h-4 w-4" />
          </button>
        </form>

        <div className="text-center text-xs text-slate-400">
          Don&apos;t have an account?{" "}
          <a href="/register" className="font-medium text-emerald-400 hover:text-emerald-300">
            Create a Client Account
          </a>
        </div>
      </div>
    </div>
  );
}
