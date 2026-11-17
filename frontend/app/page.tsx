import React from "react";
import { SalesChatbot } from "@/components/chatbot/SalesChatbot";

export default function Home() {
  const supportWhatsapp = "03238300330";
  const whatsappUrl = `https://wa.me/923238300330?text=Hi%20Teloxtech%2C%20I%20would%20like%20to%20inquire%20about%20your%20services`;

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8 bg-gradient-to-b from-slate-900 to-slate-950 text-white relative">
      <div className="max-w-3xl text-center space-y-6">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          Environment Configured & Active
        </div>

        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-slate-400">
          Teloxtech SaaS Platform
        </h1>

        <p className="text-base sm:text-lg text-slate-300 max-w-xl mx-auto leading-relaxed">
          Autonomous multi-tenant platform with completely independent Client &amp; Admin portals,
          Supabase PostgreSQL isolation, and WhatsApp business automation.
        </p>

        {/* Separated Portals Launch Actions */}
        <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
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
            href={whatsappUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-5 py-3 rounded-xl bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 font-medium border border-emerald-500/30 transition"
          >
            <MessageSquare className="h-4 w-4 text-emerald-400" />
            <span>WhatsApp Services: {supportWhatsapp}</span>
          </a>
        </div>

        {/* System Specifications Badges */}
        <div className="pt-10 grid grid-cols-2 sm:grid-cols-4 gap-4 text-left border-t border-slate-800">
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
            <p className="text-xs text-slate-400 uppercase font-semibold">Sole Administrator</p>
            <p className="text-xs font-mono font-medium text-amber-400 mt-1 break-all">talhazam4@gmail.com</p>
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
            <p className="text-xs font-mono font-medium text-emerald-400 mt-1">{supportWhatsapp}</p>
          </div>
        </div>
      </div>

      <SalesChatbot />
    </main>
  );
}
