"use client";

import React, { useState } from "react";
import { apiRequest } from "@/lib/api";
import {
  setAuthToken,
  setCurrentUser,
  SUPPORT_WHATSAPP_NUMBER,
  SUPPORT_WHATSAPP_LINK,
} from "@/lib/auth";
import { Lock, Mail, User, Phone, ArrowRight, AlertCircle, MessageSquare } from "lucide-react";

export default function RegisterPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await apiRequest("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({
          full_name: fullName.trim(),
          email: email.trim().toLowerCase(),
          password,
          phone: phone.trim() || null,
          account_type: "client",
        }),
      });

      if (!res.access_token && !res.data?.access_token) {
        setError(res.error?.message || "Failed to create account. Please check your details.");
        setLoading(false);
        return;
      }

      const token = res.access_token || res.data?.access_token;
      const userId = res.user_id || res.data?.user_id;

      // Automatically persist client session so they remain remembered across subsequent visits
      setAuthToken(token, true);
      setCurrentUser(
        {
          userId,
          email: email.trim().toLowerCase(),
          fullName: fullName.trim(),
          token,
          isSuperAdmin: false,
          rememberMe: true,
        },
        true
      );

      // Clients route strictly to client onboarding / client portal
      window.location.href = "/onboarding";
    } catch (err: any) {
      setError(err.message || "Failed to register. Please try again.");
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
            Create Your Client Account
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Done-For-You Managed AI Automation Services
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
            <label className="block text-xs font-medium text-slate-300">Full Name</label>
            <div className="relative mt-1">
              <User className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Sarah Connor"
                className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300">Email Address</label>
            <div className="relative mt-1">
              <Mail className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="sarah@enterprise.com"
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
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            <p className="mt-1 text-[11px] text-slate-500">Minimum 8 characters. Persisted securely.</p>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300">Phone / WhatsApp (Optional)</label>
            <div className="relative mt-1">
              <Phone className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 555-0199"
                className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white shadow-md hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-slate-950 disabled:opacity-50 transition"
          >
            {loading ? "Creating Account..." : "Create Account & Continue"}
            <ArrowRight className="h-4 w-4" />
          </button>
        </form>

        <div className="border-t border-slate-800/80 pt-4 space-y-3">
          <div className="text-center text-xs text-slate-400">
            Already have an account?{" "}
            <a href="/login" className="font-medium text-emerald-400 hover:text-emerald-300">
              Sign In
            </a>
          </div>

          <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-3 text-center">
            <p className="text-xs text-slate-400">
              Have questions regarding our service packages?
            </p>
            <a
              href={SUPPORT_WHATSAPP_LINK}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1.5 inline-flex items-center gap-2 text-xs font-semibold text-emerald-400 hover:text-emerald-300"
            >
              <MessageSquare className="h-3.5 w-3.5" />
              <span>Contact Services on WhatsApp: {SUPPORT_WHATSAPP_NUMBER}</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
