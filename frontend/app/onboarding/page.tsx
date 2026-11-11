"use client";

import React, { useState } from "react";
import { apiRequest } from "@/lib/api";
import { setActiveTenant, getCurrentUser } from "@/lib/auth";
import { Building2, Sparkles, ArrowRight, AlertCircle, Hash, Briefcase } from "lucide-react";

const INDUSTRIES = [
  "Real Estate & Property Management",
  "Healthcare & Medical Clinics",
  "Retail & E-Commerce",
  "Technology & Software",
  "Logistics & Supply Chain",
  "Professional Financial Services",
  "Hospitality & Tourism",
];

export default function OnboardingPage() {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [industry, setIndustry] = useState(INDUSTRIES[0]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleNameChange = (val: string) => {
    setName(val);
    // Auto-generate clean slug
    const generatedSlug = val
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    setSlug(generatedSlug);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await apiRequest("/api/v1/tenants", {
        method: "POST",
        body: JSON.stringify({
          name,
          slug,
          industry,
          settings: {
            onboarding_completed: true,
            theme: "emerald",
          },
        }),
      });

      if (!res.id && !res.data?.id) {
        setError(res.error?.message || "Failed to create company workspace. Handle may already be taken.");
        setLoading(false);
        return;
      }

      const tenant = res.id ? res : res.data;
      setActiveTenant(tenant);

      window.location.href = "/dashboard";
    } catch (err: any) {
      setError(err.message || "An error occurred creating your company workspace.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4 py-12 text-slate-100">
      <div className="w-full max-w-xl space-y-8 rounded-2xl border border-slate-800 bg-slate-950 p-8 shadow-2xl">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500 text-white shadow-lg shadow-emerald-500/20">
            <Sparkles className="h-6 w-6" />
          </div>
          <h2 className="mt-4 text-2xl font-bold tracking-tight text-white">
            Set Up Your Company Workspace
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Configure your isolated multi-tenant business environment
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-400">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          <div>
            <label className="block text-xs font-medium text-slate-300">Company Name</label>
            <div className="relative mt-1">
              <Building2 className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
              <input
                type="text"
                required
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="e.g. Apex Property Dealers"
                className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300">Company Handle / Slug</label>
            <div className="relative mt-1">
              <Hash className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
              <input
                type="text"
                required
                pattern="^[a-z0-9-]+$"
                value={slug}
                onChange={(e) => setSlug(e.target.value.toLowerCase())}
                placeholder="apex-property-dealers"
                className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 font-mono"
              />
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Unique identifier used in URLs and tenant isolation policies.
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300">Industry Category</label>
            <div className="relative mt-1">
              <Briefcase className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
              <select
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {INDUSTRIES.map((ind) => (
                  <option key={ind} value={ind} className="bg-slate-900 text-white">
                    {ind}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="rounded-lg bg-slate-900/60 p-4 border border-slate-800/80 text-xs text-slate-400 space-y-1">
            <p className="font-semibold text-slate-300">Tenant Isolation Policy</p>
            <p>
              Your data is secured with Supabase Row Level Security (RLS). No other company can
              view or alter your records.
            </p>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white shadow-md hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-slate-950 disabled:opacity-50 transition"
          >
            {loading ? "Creating Workspace..." : "Launch Company Dashboard"}
            <ArrowRight className="h-4 w-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
