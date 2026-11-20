"use client";

import React, { useState, useEffect, useRef } from "react";
import { apiRequest } from "@/lib/api";
import { getActiveTenant, SUPPORT_WHATSAPP_NUMBER, SUPPORT_WHATSAPP_LINK } from "@/lib/auth";
import {
  MessageSquare,
  X,
  Send,
  Sparkles,
  PhoneCall,
  ExternalLink,
  Flame,
  ArrowRight,
  ShieldCheck,
  Building2,
  DollarSign,
  Briefcase,
} from "lucide-react";

interface ChatMessage {
  id: string;
  sender: "user" | "bot";
  text: string;
  timestamp: string;
  hotLead?: boolean;
  alertMessage?: string | null;
  whatsappUrl?: string;
  detectedIndustry?: string;
  detectedPlan?: string;
  detectedPrice?: number;
  transitionUrl?: string;
}

export function SalesChatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      sender: "bot",
      text: "Hello! I am your Talox AI Sales Consultant & Receptionist. I can guide you through our 6 Done-For-You AI automation services across our 4 core industries (Financing, Clinics / Hospitals, Real Estate / Property, E-Commerce) plus custom setups, or connect you directly with our team on WhatsApp.",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen]);

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      sender: "user",
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInput("");
    setLoading(true);

    try {
      const tenant = getActiveTenant();
      const res = await apiRequest<{
        reply: string;
        detected_industry?: string;
        detected_service_slug?: string;
        detected_plan_name?: string;
        detected_price?: number;
        hot_lead?: boolean;
        alert_message?: string;
        whatsapp_url?: string;
        onboarding_transition_url?: string;
      }>("/api/v1/marketing/chatbot/message", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          session_id: `session_${Date.now()}`,
          current_industry: tenant?.industry || null,
        }),
      });

      const data = res.data || (res as any);
      const botMsg: ChatMessage = {
        id: `bot_${Date.now()}`,
        sender: "bot",
        text:
          data.reply ||
          `Thank you for contacting Talox Tech Stream! Our team is available 24/7. You can reach our executive consultants on WhatsApp at ${SUPPORT_WHATSAPP_NUMBER}.`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        hotLead: Boolean(data.hot_lead),
        alertMessage: data.alert_message,
        whatsappUrl: data.whatsapp_url || SUPPORT_WHATSAPP_LINK,
        detectedIndustry: data.detected_industry,
        detectedPlan: data.detected_plan_name,
        detectedPrice: data.detected_price,
        transitionUrl: data.onboarding_transition_url,
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot_err_${Date.now()}`,
          sender: "bot",
          text: `We are currently experiencing high request volume. For instant live assistance, please click below to message us directly on WhatsApp at ${SUPPORT_WHATSAPP_NUMBER}.`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          hotLead: true,
          alertMessage: "A hot lead is ready to chat with you right now!",
          whatsappUrl: SUPPORT_WHATSAPP_LINK,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end">
      {/* Floating Chat Trigger Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="group relative flex items-center gap-3 rounded-full bg-gradient-to-r from-emerald-600 to-teal-600 px-5 py-3.5 text-white shadow-2xl shadow-emerald-500/30 hover:scale-105 hover:from-emerald-500 hover:to-teal-500 transition-all duration-200"
          aria-label="Open AI Sales Chatbot"
        >
          <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-400 border-2 border-slate-900"></span>
          </span>
          <Sparkles className="h-5 w-5 text-emerald-200 group-hover:rotate-12 transition-transform" />
          <div className="text-left">
            <p className="text-xs font-extrabold tracking-wide uppercase leading-tight">AI Consultant</p>
            <p className="text-[11px] text-emerald-100 font-medium">Explore Packages & Support</p>
          </div>
        </button>
      )}

      {/* Expanded Chat Dialog Window */}
      {isOpen && (
        <div className="flex h-[560px] max-h-[80vh] w-[calc(100vw-2rem)] max-w-[calc(100vw-2rem)] sm:w-[360px] flex-col rounded-2xl border border-slate-700 bg-slate-950 text-slate-100 shadow-2xl shadow-black/60 overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-200">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-800 bg-gradient-to-r from-slate-900 via-slate-900 to-slate-950 px-4 py-3.5">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500 text-white shadow-md shadow-emerald-500/20">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-white">Talox AI Consultant</h3>
                  <span className="flex items-center gap-1 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-500/30">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    Live
                  </span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Pre-Registration Sales & Client Guidance
                </p>
              </div>
            </div>

            <button
              onClick={() => setIsOpen(false)}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition"
              aria-label="Close Chat"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Messages Feed */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3.5 text-xs">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${
                  msg.sender === "user" ? "items-end" : "items-start"
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 shadow-sm leading-relaxed ${
                    msg.sender === "user"
                      ? "bg-emerald-600 text-white rounded-br-xs"
                      : "bg-slate-900 border border-slate-800 text-slate-200 rounded-bl-xs"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.text}</p>
                </div>

                {/* Hot Lead Alert Trigger Banner */}
                {msg.hotLead && (
                  <div className="mt-2 w-[95%] rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-amber-200 space-y-2">
                    <div className="flex items-center gap-2 font-bold text-amber-400 text-[11px]">
                      <Flame className="h-4 w-4 animate-bounce text-amber-400" />
                      <span>{msg.alertMessage || "A hot lead is ready to chat with you right now!"}</span>
                    </div>
                    <p className="text-[11px] text-slate-300">
                      Our live senior support agent is available right now for direct assistance.
                    </p>
                    <a
                      href={msg.whatsappUrl || SUPPORT_WHATSAPP_LINK}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-500 shadow-md shadow-emerald-600/30 transition"
                    >
                      <PhoneCall className="h-3.5 w-3.5" />
                      <span>Chat with Live Human on WhatsApp ({SUPPORT_WHATSAPP_NUMBER})</span>
                    </a>
                  </div>
                )}

                {/* Seamless Transition Card (Chatbot to Dashboard) */}
                {msg.transitionUrl && msg.detectedIndustry && (
                  <div className="mt-2 w-[95%] rounded-xl border border-emerald-500/40 bg-emerald-950/30 p-3 text-slate-200 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 text-emerald-400 font-bold text-[11px]">
                        <Briefcase className="h-3.5 w-3.5" />
                        <span>Pre-Configured Package Ready</span>
                      </div>
                      <span className="font-mono text-xs font-extrabold text-white">
                        ${msg.detectedPrice?.toFixed(0) || "249"}/mo
                      </span>
                    </div>

                    <p className="text-[11px] text-slate-300">
                      Selected Industry: <strong className="text-white">{msg.detectedIndustry}</strong>
                      <br />
                      Tier: <strong className="text-emerald-400 capitalize">{msg.detectedPlan || "Growth"}</strong>
                    </p>

                    <a
                      href={msg.transitionUrl}
                      className="flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-bold text-slate-950 hover:bg-emerald-400 shadow-md shadow-emerald-500/20 transition"
                    >
                      <span>Launch Dashboard With This Package</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </a>
                  </div>
                )}

                <span className="mt-1 text-[10px] text-slate-500 px-1">
                  {msg.timestamp}
                </span>
              </div>
            ))}

            {loading && (
              <div className="flex items-center gap-2 text-slate-400 text-xs py-2">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping"></span>
                <span>Talox Consultant is typing...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Interactive Quick Prompts */}
          <div className="border-t border-slate-800 bg-slate-900/60 p-2 overflow-x-auto flex gap-1.5 no-scrollbar">
            <button
              onClick={() => handleSendMessage("What industries do you support?")}
              className="shrink-0 rounded-full border border-slate-700 bg-slate-800 px-2.5 py-1 text-[10px] text-slate-300 hover:border-emerald-500 hover:text-white transition"
            >
              🏢 4 Core Industries + Custom
            </button>
            <button
              onClick={() => handleSendMessage("Show me pricing and packages")}
              className="shrink-0 rounded-full border border-slate-700 bg-slate-800 px-2.5 py-1 text-[10px] text-slate-300 hover:border-emerald-500 hover:text-white transition"
            >
              💰 Pricing ($99+)
            </button>
            <button
              onClick={() => handleSendMessage("I want to talk to a human on WhatsApp")}
              className="shrink-0 rounded-full border border-emerald-500/50 bg-emerald-500/10 px-2.5 py-1 text-[10px] text-emerald-300 hover:bg-emerald-500/20 transition"
            >
              💬 WhatsApp ({SUPPORT_WHATSAPP_NUMBER})
            </button>
            <button
              onClick={() => handleSendMessage("What are your company bank details?")}
              className="shrink-0 rounded-full border border-slate-700 bg-slate-800 px-2.5 py-1 text-[10px] text-slate-300 hover:border-emerald-500 hover:text-white transition"
            >
              🏦 Bank Transfer Details
            </button>
          </div>

          {/* Input Bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="border-t border-slate-800 bg-slate-950 p-2.5 flex items-center gap-2"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about industries, plans, or services..."
              className="flex-1 rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-40 transition shadow-md shadow-emerald-600/20"
              aria-label="Send Message"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
