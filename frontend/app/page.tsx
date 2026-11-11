import React from "react";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8 bg-gradient-to-b from-slate-900 to-slate-950 text-white">
      <div className="max-w-3xl text-center space-y-6">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          Production-Ready Architecture Active
        </div>

        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400">
          Talox Tech Stream
        </h1>

        <p className="text-lg text-slate-300 max-w-xl mx-auto">
          Custom Python Multi-Tenant SaaS Agent Platform with OpenRouter Smart Routing,
          Strict Circuit Breakers, Meta WhatsApp Embedded Signup, and Automated Cascade Purge.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
          <a
            href="/login"
            className="px-6 py-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium transition shadow-lg shadow-emerald-900/20"
          >
            Client Portal
          </a>
          <a
            href="/admin"
            className="px-6 py-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium border border-slate-700 transition"
          >
            Admin Console
          </a>
        </div>

        <div className="pt-12 grid grid-cols-2 sm:grid-cols-4 gap-4 text-left border-t border-slate-800">
          <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800/80">
            <p className="text-xs text-slate-400 uppercase font-semibold">AI Routing</p>
            <p className="text-sm font-medium text-slate-200 mt-1">OpenRouter Smart Tier</p>
          </div>
          <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800/80">
            <p className="text-xs text-slate-400 uppercase font-semibold">Cost Protection</p>
            <p className="text-sm font-medium text-slate-200 mt-1">Circuit Breaker & Quotas</p>
          </div>
          <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800/80">
            <p className="text-xs text-slate-400 uppercase font-semibold">Messaging</p>
            <p className="text-sm font-medium text-slate-200 mt-1">Meta Embedded Signup</p>
          </div>
          <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800/80">
            <p className="text-xs text-slate-400 uppercase font-semibold">Database</p>
            <p className="text-sm font-medium text-slate-200 mt-1">Supabase PostgreSQL RLS</p>
          </div>
        </div>
      </div>
    </main>
  );
}
