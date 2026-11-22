import React from "react";
import { Users, ShieldAlert, MessageSquare, ArrowRight, Sparkles, CheckCircle2, Briefcase } from "lucide-react";
import { SUPPORT_WHATSAPP_NUMBER, SUPPORT_WHATSAPP_LINK } from "@/lib/auth";
import { CANONICAL_SERVICES, CORE_INDUSTRIES } from "@/lib/services";

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-950 to-slate-950 text-white px-4 py-12 sm:px-8 sm:py-16">
      <div className="max-w-6xl mx-auto space-y-14">
        {/* Hero Section */}
        <div className="max-w-3xl mx-auto text-center space-y-6">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-sm">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Environment Configured &amp; Active
          </div>

          <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-slate-400">
            Teloxtech SaaS Platform
          </h1>

          <p className="text-base sm:text-lg text-slate-300 max-w-2xl mx-auto leading-relaxed">
            Autonomous multi-tenant platform with completely independent Client &amp; Admin portals,
            Supabase PostgreSQL isolation, and done-for-you AI business automation.
          </p>

          {/* Separated Portals Launch Actions */}
          <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
            <a
              href="/login"
              className="flex items-center gap-2 px-6 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition shadow-lg shadow-emerald-900/30"
            >
              <Users className="h-4 w-4" />
              <span>Client Portal</span>
            </a>

            <a
              href="/admin"
              className="flex items-center gap-2 px-6 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-amber-400 font-semibold border border-amber-500/30 transition shadow-lg shadow-slate-950/50"
            >
              <ShieldAlert className="h-4 w-4" />
              <span>Admin Portal</span>
            </a>

            <a
              href={SUPPORT_WHATSAPP_LINK}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-5 py-3 rounded-xl bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 font-medium border border-emerald-500/30 transition"
            >
              <MessageSquare className="h-4 w-4 text-emerald-400" />
              <span>WhatsApp Services: {SUPPORT_WHATSAPP_NUMBER}</span>
            </a>
          </div>

          {/* System Specifications Badges */}
          <div className="pt-8 grid grid-cols-2 sm:grid-cols-4 gap-4 text-left border-t border-slate-800">
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
              <p className="text-xs text-slate-400 uppercase font-semibold">Core Industries</p>
              <p className="text-xs font-medium text-emerald-400 mt-1">4 Core Verticals + Custom</p>
            </div>
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
              <p className="text-xs text-slate-400 uppercase font-semibold">Portal Separation</p>
              <p className="text-xs font-medium text-slate-200 mt-1">Strict Isolated Routes</p>
            </div>
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
              <p className="text-xs text-slate-400 uppercase font-semibold">Client Session</p>
              <p className="text-xs font-medium text-emerald-400 mt-1">Persistent &amp; Remembered</p>
            </div>
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
              <p className="text-xs text-slate-400 uppercase font-semibold">Services WhatsApp</p>
              <p className="text-xs font-mono font-medium text-emerald-400 mt-1">{SUPPORT_WHATSAPP_NUMBER}</p>
            </div>
          </div>
        </div>

        {/* 4 Core Industries + Custom Strip */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 sm:p-8 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <Briefcase className="h-5 w-5 text-emerald-400 shrink-0" />
              <div>
                <h2 className="text-lg sm:text-xl font-bold text-white">
                  Tailored for 4 Core Industries + Custom Setups
                </h2>
                <p className="text-xs text-slate-400">
                  Pre-built compliance, workflows, and AI playbooks — custom industry setups configured during onboarding.
                </p>
              </div>
            </div>
            <a
              href="/register"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-400 hover:text-emerald-300"
            >
              <span>Start Free Workspace Setup</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </a>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {CORE_INDUSTRIES.map((industry) => (
              <a
                key={industry}
                href={`/register?industry=${encodeURIComponent(industry)}`}
                className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-xs font-semibold text-slate-200 hover:border-emerald-500/50 hover:text-white transition"
              >
                <span className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                  <span>{industry}</span>
                </span>
                <ArrowRight className="h-3.5 w-3.5 text-slate-500" />
              </a>
            ))}
            <a
              href="/register"
              className="flex items-center justify-between rounded-xl border border-dashed border-emerald-500/40 bg-emerald-500/5 px-4 py-3 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/10 transition"
            >
              <span className="flex items-center gap-2">
                <Sparkles className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                <span>Custom Industry</span>
              </span>
              <ArrowRight className="h-3.5 w-3.5 text-emerald-400" />
            </a>
          </div>
        </section>

        {/* 6 Managed AI Services Showcase */}
        <section className="space-y-6">
          <div className="text-center space-y-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-3 py-1 text-xs font-semibold text-emerald-400">
              <Sparkles className="h-3.5 w-3.5" />
              6 Done-For-You Managed AI Services
            </span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Choose the Automation Services Your Business Needs
            </h2>
            <p className="text-xs sm:text-sm text-slate-400 max-w-2xl mx-auto">
              Select a single service or combine multiple workflows. Transparent Starter, Growth, and Enterprise tiers with human-in-the-loop safety.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {CANONICAL_SERVICES.map((srv) => (
              <div
                key={srv.slug}
                className="flex flex-col justify-between rounded-2xl border border-slate-800 bg-slate-900/70 p-6 hover:border-emerald-500/40 transition shadow-lg shadow-black/20"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-300">
                      {srv.category}
                    </span>
                    <span className="text-xs font-mono font-bold text-emerald-400">
                      From ${srv.starterPrice}/mo
                    </span>
                  </div>

                  <h3 className="text-base font-bold text-white leading-snug">
                    {srv.name}
                  </h3>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    {srv.description}
                  </p>
                </div>

                <div className="mt-5 pt-4 border-t border-slate-800/90 space-y-3">
                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                    <span>Starter: ${srv.starterPrice}</span>
                    <span>Growth: ${srv.growthPrice}</span>
                    <span>Enterprise: ${srv.enterprisePrice}</span>
                  </div>

                  <div className="flex flex-col sm:flex-row gap-2">
                    <a
                      href={`/register?service=${encodeURIComponent(srv.slug)}`}
                      className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3.5 py-2 text-xs font-semibold text-white transition"
                    >
                      <span>Get Started</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </a>
                    <a
                      href={`/onboarding?service=${encodeURIComponent(srv.slug)}`}
                      className="inline-flex items-center justify-center rounded-lg border border-slate-700 bg-slate-950 hover:bg-slate-800 px-3 py-2 text-xs font-medium text-slate-300 transition"
                    >
                      Already Registered? Configure
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
        <footer className="mt-10 flex justify-center gap-6 border-t border-slate-700/40 pt-4 text-xs text-slate-400">
          <a href="/privacy/" className="hover:underline">Privacy Policy</a>
          <a href="/terms/" className="hover:underline">Terms of Service</a>
        </footer>
      </div>
    </main>
  );
}
