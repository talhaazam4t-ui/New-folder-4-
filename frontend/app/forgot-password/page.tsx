"use client";

import React, { useState } from "react";
import { AlertCircle, ArrowLeft, CheckCircle2, Mail } from "lucide-react";
import { TurnstileWidget } from "@/components/shared/TurnstileWidget";
import { apiRequest } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);
    setLoading(true);

    const res = await apiRequest("/api/v1/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({
        email: email.trim().toLowerCase(),
        turnstile_token: turnstileToken,
      }),
    });

    setLoading(false);
    if (res.success || res.data?.accepted) {
      setSuccessMessage(
        res.message ||
          "If an account exists for that email address, a password reset link has been sent."
      );
    } else {
      setError(res.error?.message || "Could not process password reset request.");
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4 py-12 text-slate-100">
      <div className="w-full max-w-md space-y-6 rounded-2xl border border-slate-800 bg-slate-950 p-8 shadow-2xl">
        <div className="text-center space-y-1">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500 text-white font-extrabold text-xl">
            T
          </div>
          <h1 className="mt-4 text-2xl font-bold text-white">Reset Your Password</h1>
          <p className="text-xs text-slate-400">
            Enter your account email and we will send a single-use reset link valid for 30 minutes.
          </p>
        </div>

        {successMessage && (
          <div className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{successMessage}</span>
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300">Account Email</label>
            <div className="relative mt-1">
              <Mail className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          <TurnstileWidget onTokenChange={setTurnstileToken} />

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 transition"
          >
            {loading ? "Sending Reset Link..." : "Send Reset Link"}
          </button>
        </form>

        <div className="text-center pt-2">
          <a
            href="/login"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-400 hover:text-emerald-300"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to Sign In
          </a>
        </div>
      </div>
    </div>
  );
}
