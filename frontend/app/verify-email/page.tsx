"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";
import { apiRequest } from "@/lib/api";

function VerifyEmailInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const [status, setStatus] = useState<"verifying" | "verified" | "error">("verifying");
  const [message, setMessage] = useState("Verifying your email address...");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Verification token is missing from URL.");
      return;
    }

    let cancelled = false;
    (async () => {
      const res = await apiRequest("/api/v1/auth/verify-email", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      if (cancelled) return;
      if (res.success || res.data?.email_verified) {
        setStatus("verified");
        setMessage("Your email address is verified! Your workspace security is active.");
      } else {
        setStatus("error");
        setMessage(res.error?.message || "Verification link is invalid or has expired.");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="w-full max-w-md space-y-6 rounded-2xl border border-slate-800 bg-slate-950 p-8 shadow-2xl text-center">
      {status === "verifying" && (
        <div className="space-y-3">
          <RefreshCw className="h-8 w-8 text-emerald-400 animate-spin mx-auto" />
          <h1 className="text-xl font-bold text-white">Verifying Email</h1>
          <p className="text-xs text-slate-400">{message}</p>
        </div>
      )}

      {status === "verified" && (
        <div className="space-y-4">
          <CheckCircle2 className="h-10 w-10 text-emerald-400 mx-auto" />
          <h1 className="text-xl font-bold text-white">Email Verified</h1>
          <p className="text-xs text-slate-300">{message}</p>
          <a
            href="/dashboard"
            className="block w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500"
          >
            Continue to Portal
          </a>
        </div>
      )}

      {status === "error" && (
        <div className="space-y-4">
          <AlertCircle className="h-10 w-10 text-red-400 mx-auto" />
          <h1 className="text-xl font-bold text-white">Verification Failed</h1>
          <p className="text-xs text-red-300">{message}</p>
          <a
            href="/login"
            className="block w-full rounded-lg border border-slate-700 bg-slate-900 py-2.5 text-sm font-semibold text-slate-200 hover:bg-slate-800"
          >
            Return to Sign In
          </a>
        </div>
      )}
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4 py-12 text-slate-100">
      <Suspense fallback={<div className="text-slate-400 text-sm">Verifying...</div>}>
        <VerifyEmailInner />
      </Suspense>
    </div>
  );
}
