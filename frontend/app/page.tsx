import React from "react";
import {
  ArrowRight,
  Briefcase,
  CalendarCheck2,
  CheckCircle2,
  MessageSquare,
  PhoneCall,
  PhoneForwarded,
  ShieldCheck,
  Sparkles,
  Users,
  Zap,
} from "lucide-react";
import { SUPPORT_WHATSAPP_LINK, SUPPORT_WHATSAPP_NUMBER } from "@/lib/auth";
import { CANONICAL_SERVICES, CORE_INDUSTRIES } from "@/lib/services";

export default function Home() {
  const flagshipVoiceService = CANONICAL_SERVICES.find(
    (s) => s.slug === "office-receptionist"
  );
  const coreSixServices = CANONICAL_SERVICES.filter(
    (s) => s.slug !== "office-receptionist"
  );

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-950 to-slate-950 text-white">
      {/* Sticky Top SaaS Navigation Bar (Client-Facing Only — No Public Admin Button) */}
      <header className="sticky top-0 z-40 border-b border-slate-800/80 bg-slate-950/85 backdrop-blur-md">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-4 px-4 sm:px-8 h-16">
          <a href="/" className="flex items-center gap-2.5 group">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-600 text-white font-extrabold text-base shadow-md shadow-emerald-900/40 group-hover:bg-emerald-500 transition">
              T
            </div>
            <div className="leading-tight">
              <span className="text-base font-extrabold tracking-tight text-white block">
                Teloxtech
              </span>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400 block">
                Managed AI Automation
              </span>
            </div>
          </a>

          <nav className="hidden md:flex items-center gap-6 text-xs font-semibold text-slate-300">
            <a href="#services" className="hover:text-emerald-400 transition">
              Services (7)
            </a>
            <a href="#how-it-works" className="hover:text-emerald-400 transition">
              How It Works
            </a>
            <a href="#industries" className="hover:text-emerald-400 transition">
              Industries
            </a>
            <a
              href={SUPPORT_WHATSAPP_LINK}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-emerald-400 transition"
            >
              WhatsApp Support
            </a>
          </nav>

          <div className="flex items-center gap-2.5">
            <a
              href="/login"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 hover:text-white transition"
            >
              Sign In
            </a>
            <a
              href="/register"
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-md shadow-emerald-900/30 hover:bg-emerald-500 transition"
            >
              <span>Get Started</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </header>

      <main className="px-4 py-12 sm:px-8 sm:py-16">
        <div className="max-w-6xl mx-auto space-y-16">
          {/* Hero Section */}
          <section className="max-w-3xl mx-auto text-center space-y-6">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-sm">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              24/7 Done-For-You AI Voice, WhatsApp &amp; Growth Automation
            </div>

            <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight leading-[1.1] bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-emerald-200">
              Automate Calls, Leads, WhatsApp &amp; Finances — 24/7
            </h1>

            <p className="text-base sm:text-lg text-slate-300 max-w-2xl mx-auto leading-relaxed">
              Teloxtech runs your AI Office Receptionist, WhatsApp customer concierge, verified lead
              qualification, marketing campaigns, and financial ledger — managed end-to-end with
              human approval controls so you stay in charge.
            </p>

            {/* Clean Client-Focused CTAs */}
            <div className="flex flex-wrap items-center justify-center gap-3.5 pt-2">
              <a
                href="/register"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold transition shadow-lg shadow-emerald-900/40"
              >
                <Zap className="h-4 w-4" />
                <span>Start Free Workspace Setup</span>
                <ArrowRight className="h-4 w-4" />
              </a>

              <a
                href="/login"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-100 text-sm font-semibold border border-slate-700 transition"
              >
                <Users className="h-4 w-4 text-emerald-400" />
                <span>Client Sign In</span>
              </a>

              <a
                href={SUPPORT_WHATSAPP_LINK}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 text-sm font-medium border border-emerald-500/30 transition"
              >
                <MessageSquare className="h-4 w-4 text-emerald-400" />
                <span>WhatsApp: {SUPPORT_WHATSAPP_NUMBER}</span>
              </a>
            </div>

            {/* Business Trust & Capability Highlights */}
            <div className="pt-8 grid grid-cols-2 sm:grid-cols-4 gap-3.5 text-left border-t border-slate-800">
              <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800/80">
                <p className="text-[11px] text-slate-400 uppercase font-semibold">Managed Suite</p>
                <p className="text-sm font-bold text-emerald-400 mt-1">7 Ready AI Services</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Voice, WhatsApp, CRM &amp; Finance</p>
              </div>
              <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800/80">
                <p className="text-[11px] text-slate-400 uppercase font-semibold">AI Receptionist</p>
                <p className="text-sm font-bold text-white mt-1">24/7 Live Phone Calls</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Cal.com booking + live transfer</p>
              </div>
              <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800/80">
                <p className="text-[11px] text-slate-400 uppercase font-semibold">Safety Controls</p>
                <p className="text-sm font-bold text-emerald-400 mt-1">Human-in-the-Loop</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Approve campaigns &amp; payouts</p>
              </div>
              <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800/80">
                <p className="text-[11px] text-slate-400 uppercase font-semibold">Direct Support</p>
                <p className="text-sm font-mono font-bold text-emerald-400 mt-1">
                  {SUPPORT_WHATSAPP_NUMBER}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">Assisted onboarding on WhatsApp</p>
              </div>
            </div>
          </section>

          {/* How Teloxtech Works in 3 Simple Steps */}
          <section
            id="how-it-works"
            className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 sm:p-8 space-y-6"
          >
            <div className="text-center space-y-1.5">
              <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-400">
                Zero Coding Required
              </span>
              <h2 className="text-xl sm:text-2xl font-extrabold text-white">
                Go Live with Managed AI in 3 Simple Steps
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-5 space-y-2">
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-xs font-extrabold text-emerald-400">
                  1
                </span>
                <h3 className="text-sm font-bold text-white">Pick Your Industry &amp; Services</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Choose one service like Office Receptionist or combine all 7 with transparent
                  Starter, Growth, and Enterprise monthly plans.
                </p>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-5 space-y-2">
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-xs font-extrabold text-emerald-400">
                  2
                </span>
                <h3 className="text-sm font-bold text-white">5-Minute Guided Onboarding</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Our dynamic wizard asks only for what your chosen service needs — business hours,
                  FAQs, Cal.com link, WhatsApp, or Gmail.
                </p>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-5 space-y-2">
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-xs font-extrabold text-emerald-400">
                  3
                </span>
                <h3 className="text-sm font-bold text-white">Track Live Results &amp; Approvals</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Monitor answered calls, booked appointments, qualified leads, and net profits in
                  your private dashboard — with full approval control.
                </p>
              </div>
            </div>
          </section>

          {/* 4 Core Industries + Custom Setups Strip */}
          <section
            id="industries"
            className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 sm:p-8 space-y-5"
          >
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <Briefcase className="h-5 w-5 text-emerald-400 shrink-0" />
                <div>
                  <h2 className="text-lg sm:text-xl font-bold text-white">
                    Tailored for 4 Core Industries + Custom Setups
                  </h2>
                  <p className="text-xs text-slate-400">
                    Pre-built compliance, workflows, and AI playbooks — custom industry setups
                    configured during onboarding.
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

          {/* 7 Done-For-You Managed AI Services Showcase */}
          <section id="services" className="space-y-6">
            <div className="text-center space-y-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-3 py-1 text-xs font-semibold text-emerald-400">
                <Sparkles className="h-3.5 w-3.5" />
                7 Done-For-You Managed AI Services
              </span>
              <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                Choose the Automation Services Your Business Needs
              </h2>
              <p className="text-xs sm:text-sm text-slate-400 max-w-2xl mx-auto">
                Start with our flagship AI Office Receptionist or combine multiple workflows.
                Transparent Starter, Growth, and Enterprise plans with zero hidden fees.
              </p>
            </div>

            {/* Flagship Featured Service Banner: Office Receptionist (AI Voice Agent) */}
            {flagshipVoiceService && (
              <div className="rounded-2xl border border-emerald-500/40 bg-gradient-to-br from-emerald-950/40 via-slate-900 to-slate-950 p-6 sm:p-8 shadow-xl shadow-emerald-950/20">
                <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
                  <div className="space-y-3 max-w-2xl">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/20 border border-emerald-500/30 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                        <PhoneCall className="h-3 w-3" /> New Flagship Voice AI
                      </span>
                      <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-300">
                        Retell AI + Telnyx + Cal.com
                      </span>
                    </div>

                    <h3 className="text-xl sm:text-2xl font-extrabold text-white">
                      {flagshipVoiceService.name}
                    </h3>
                    <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                      {flagshipVoiceService.description}
                    </p>

                    <div className="flex flex-wrap gap-4 pt-1 text-xs text-emerald-200/90">
                      <span className="inline-flex items-center gap-1.5">
                        <CalendarCheck2 className="h-3.5 w-3.5 text-emerald-400" />
                        Live Cal.com Booking
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <PhoneForwarded className="h-3.5 w-3.5 text-emerald-400" />
                        Emergency Human Transfer
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                        Auto Call Forwarding Guide
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-col justify-between gap-4 rounded-xl border border-slate-800 bg-slate-950/80 p-5 lg:min-w-[290px]">
                    <div>
                      <p className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">
                        Monthly Plans
                      </p>
                      <p className="text-2xl font-extrabold text-white mt-0.5">
                        From ${flagshipVoiceService.starterPrice}
                        <span className="text-xs font-normal text-slate-400"> / mo</span>
                      </p>
                      <div className="mt-2 flex items-center justify-between text-[11px] font-mono text-slate-400">
                        <span>Starter: ${flagshipVoiceService.starterPrice}</span>
                        <span>Growth: ${flagshipVoiceService.growthPrice}</span>
                        <span>Ent: ${flagshipVoiceService.enterprisePrice}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <a
                        href={`/register?service=${encodeURIComponent(flagshipVoiceService.slug)}`}
                        className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-4 py-2.5 text-xs font-semibold text-white transition"
                      >
                        <span>Launch AI Receptionist</span>
                        <ArrowRight className="h-3.5 w-3.5" />
                      </a>
                      <a
                        href={`/onboarding?service=${encodeURIComponent(flagshipVoiceService.slug)}`}
                        className="inline-flex items-center justify-center rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 px-3 py-2.5 text-xs font-medium text-slate-300 transition"
                      >
                        Configure
                      </a>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Balanced 3x2 Grid for the 6 Core Automation Services */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {coreSixServices.map((srv) => (
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

                    <div className="flex items-center gap-2">
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
                        Configure
                      </a>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Clean Footer */}
          <footer className="mt-10 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-slate-800 pt-6 text-xs text-slate-400">
            <p>© {new Date().getFullYear()} Teloxtech. Managed AI Automation Platform.</p>
            <div className="flex flex-wrap items-center gap-5">
              <a href="/login" className="hover:text-white transition">
                Client Sign In
              </a>
              <a href="/register" className="hover:text-white transition">
                Get Started
              </a>
              <a
                href={SUPPORT_WHATSAPP_LINK}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-emerald-400 transition"
              >
                WhatsApp Support
              </a>
              <a href="/privacy/" className="hover:text-white transition">
                Privacy Policy
              </a>
              <a href="/terms/" className="hover:text-white transition">
                Terms of Service
              </a>
            </div>
          </footer>
        </div>
      </main>
    </div>
  );
}
