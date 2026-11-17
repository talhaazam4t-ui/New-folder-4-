"use client";

import React, { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiRequest } from "@/lib/api";
import { setAuthToken, setCurrentUser, setActiveTenant } from "@/lib/auth";
import { Lock, Mail, User, Phone, ArrowRight, AlertCircle, Sparkles, CheckCircle2 } from "lucide-react";

function RegisterForm() {
  const searchParams = useSearchParams();
  const preSelectedIndustry = searchParams.get("industry") || "";
  const preSelectedService = searchParams.get("service") || "";
  const preSelectedPackage = searchParams.get("package") || searchParams.get("plan") || "";
  const preSelectedPrice = searchParams.get("price") ? parseFloat(searchParams.get("price")!) : null;

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
      const isSuperAdmin = Boolean(res.is_super_admin ?? res.data?.is_super_admin);

      setAuthToken(token);
      setCurrentUser({
        userId,
        email,
        fullName,
        token,
        isSuperAdmin,
      });

      // If user came through Chatbot with pre-selected industry and package, auto-provision and jump straight to Dashboard
      if (preSelectedIndustry) {
        try {
          const tenantSlug = `biz-${userId.slice(0, 8)}-${Date.now().toString(36).slice(-4)}`;
          const tenantRes = await apiRequest("/api/v1/tenants", {
            method: "POST",
            body: JSON.stringify({
              name: `${fullName}'s Business`,
              slug: tenantSlug,
              industry: preSelectedIndustry,
              settings: {
                onboarding_completed: true,
                automation_active: false,
                payment_approved: false,
                theme: "emerald",
              },
            }),
          });

          const tenant = tenantRes.id ? tenantRes : tenantRes.data;
          if (tenant?.id) {
            setActiveTenant(tenant);

            // Fetch catalog for this industry to subscribe the desired service
            const catRes = await apiRequest<{ services: any[] }>(
              `/api/v1/services?industry=${encodeURIComponent(preSelectedIndustry)}&ensure_seeded=true`
            );
            const servicesList = Array.isArray(catRes.data)
              ? catRes.data
              : Array.isArray((catRes as any).services)
                ? (catRes as any).services
                : [];

            if (servicesList.length > 0) {
              const targetService =
                servicesList.find((s: any) => s.slug === preSelectedService) ||
                (servicesList.length >= 3 ? servicesList[2] : servicesList[0]);

              if (targetService?.id) {
                await apiRequest("/api/v1/services/subscribe", {
                  method: "POST",
                  body: JSON.stringify({
                    service_id: targetService.id,
                    plan_name: preSelectedPackage || "growth",
                    price: preSelectedPrice || 249.0,
                    billing_interval: "monthly",
                  }),
                });
              }
            }

            // Seamless transition: jump straight to Dashboard!
            window.location.href = "/dashboard";
            return;
          }
        } catch {
          // If auto-provision fails, fall back to onboarding
          window.location.href = "/onboarding";
          return;
        }
      }

      window.location.href = "/onboarding";
    } catch (err: any) {
      setError(err.message || "Failed to register. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
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

        {preSelectedIndustry && (
          <div className="mt-3 flex items-center justify-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs text-emerald-300">
            <Sparkles className="h-3.5 w-3.5" />
            <span>
              Pre-loaded: <strong>{preSelectedIndustry}</strong>{" "}
              {preSelectedPackage && `(${preSelectedPackage.toUpperCase()} Tier)`}
            </span>
          </div>
        )}
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
              placeholder="sarah@example.com"
              className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-300">Phone (Optional)</label>
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
              placeholder="Minimum 8 characters"
              className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white shadow-md hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-slate-950 disabled:opacity-50 transition"
        >
          {loading ? (
            "Creating Account..."
          ) : preSelectedIndustry ? (
            <>
              <span>Launch Dashboard Directly</span>
              <CheckCircle2 className="h-4 w-4" />
            </>
          ) : (
            <>
              <span>Continue to Industry Selection</span>
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </button>
      </form>

      <div className="text-center text-xs text-slate-400">
        Already registered?{" "}
        <a href="/login" className="font-medium text-emerald-400 hover:text-emerald-300">
          Sign In Here
        </a>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4 py-12 text-slate-100">
      <Suspense fallback={<div className="text-slate-400 text-sm">Loading Registration...</div>}>
        <RegisterForm />
      </Suspense>
    </div>
  );
}
