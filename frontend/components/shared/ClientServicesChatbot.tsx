"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  X,
  Send,
  Phone,
  Sparkles,
  ExternalLink,
  Bot,
  ArrowRight,
} from "lucide-react";
import { SUPPORT_WHATSAPP_NUMBER, SUPPORT_WHATSAPP_LINK } from "@/lib/auth";
import { apiRequest } from "@/lib/api";

interface ChatMessage {
  id: string;
  sender: "bot" | "user";
  text: string;
  timestamp: string;
  actionUrl?: string;
  actionLabel?: string;
  serviceName?: string;
  serviceSlug?: string;
}

export function ClientServicesChatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "msg-1",
      sender: "bot",
      text: "👋 Welcome to Teloxtech! I am your AI Sales Concierge. We build and operate done-for-you managed AI automations — from rent & financial tracking to 24/7 WhatsApp triage and lead growth. What type of business do you run, and what challenges are you looking to automate today?",
      timestamp: "Just now",
    },
  ]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen]);

  const handleRedirectToDashboard = (url: string, slug?: string) => {
    if (typeof window !== "undefined") {
      if (slug) {
        localStorage.setItem("teloxtech_preselected_service", slug);
      }
      window.location.href = url;
    }
  };

  const handleSendMessage = async (textToSend?: string) => {
    const userQuery = (textToSend || input).trim();
    if (!userQuery) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: userQuery,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    if (!textToSend) setInput("");
    setIsTyping(true);

    try {
      // Prepare message history for conversational assistant endpoint
      const payloadMessages = nextMessages.map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: m.text,
      }));

      const res = await apiRequest("/api/v1/assistant/chat", {
        method: "POST",
        body: JSON.stringify({
          messages: payloadMessages,
        }),
      });

      if (res.data) {
        setMessages((prev) => [
          ...prev,
          {
            id: `bot-${Date.now()}`,
            sender: "bot",
            text: res.data.reply,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            actionUrl: res.data.action_url,
            actionLabel: res.data.action_label,
            serviceName: res.data.service_name,
            serviceSlug: res.data.service_slug,
          },
        ]);
      } else {
        // Fallback if backend returns an unexpected response
        setMessages((prev) => [
          ...prev,
          {
            id: `bot-${Date.now()}`,
            sender: "bot",
            text: "Thank you! Our managed AI services eliminate manual business overhead. You can explore our pre-configured packages directly on the Client Service Dashboard.",
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            actionUrl: "/onboarding",
            actionLabel: "👉 Proceed to Client Service Dashboard",
            serviceName: "Managed AI Automation Suite",
          },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-${Date.now()}`,
          sender: "bot",
          text: "Thank you for sharing your requirements. We have prepared tailored service packages for your workspace.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          actionUrl: "/onboarding",
          actionLabel: "👉 Proceed to Client Service Dashboard",
          serviceName: "Managed AI Automation Suite",
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 font-sans">
      {/* 1. Compact Sleek Toggle Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="group flex items-center gap-2 rounded-full bg-emerald-600 hover:bg-emerald-500 text-white px-3.5 py-2.5 shadow-xl transition-all duration-200 border border-emerald-400/30"
          title="Open Teloxtech Services Assistant"
        >
          <div className="relative">
            <Bot className="h-4 w-4" />
            <span className="absolute -top-1 -right-1 flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-300 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-white"></span>
            </span>
          </div>
          <span className="font-semibold text-xs tracking-wide">
            Teloxtech Assistant
          </span>
        </button>
      )}

      {/* 2. Chat Window: Compact & Responsive Dimensions */}
      {isOpen && (
        <div className="flex flex-col w-[calc(100vw-1.5rem)] max-w-[340px] sm:w-[340px] h-[400px] sm:h-[450px] max-h-[70vh] sm:max-h-[80vh] rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl overflow-hidden animate-in fade-in slide-in-from-bottom-3 duration-200 text-slate-100">
          {/* Header */}
          <div className="flex items-center justify-between bg-slate-950 px-3.5 py-2.5 border-b border-slate-800 shrink-0">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-600 text-white">
                <Bot className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-xs font-bold text-white leading-none">
                  Teloxtech Services Assistant
                </h3>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  <span className="text-[10px] text-slate-400 font-medium">
                    AI Sales Concierge • 24/7 Managed
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition"
                title="Close Chat"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Messages Container */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-slate-900/60 text-xs">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
              >
                <div
                  className={`max-w-[88%] rounded-2xl px-3 py-2 text-xs leading-relaxed shadow-sm ${
                    msg.sender === "user"
                      ? "bg-emerald-600 text-white rounded-br-none"
                      : "bg-slate-800/90 text-slate-200 border border-slate-700/60 rounded-bl-none"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.text}</p>

                  {/* High-Converting Dashboard Redirect Action Card */}
                  {msg.actionUrl && (
                    <div className="mt-2.5 rounded-xl border border-emerald-500/30 bg-emerald-950/40 p-2.5 space-y-1.5 text-left">
                      <div className="flex items-center gap-1.5 text-emerald-400 font-bold text-[10px]">
                        <Sparkles className="h-3 w-3" />
                        <span>Recommended Service Package</span>
                      </div>
                      <p className="text-[11px] font-bold text-white leading-tight">
                        {msg.serviceName || "Managed AI Solution"}
                      </p>
                      <button
                        onClick={() => handleRedirectToDashboard(msg.actionUrl!, msg.serviceSlug)}
                        className="w-full mt-1 flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white py-1.5 px-3 text-[11px] font-bold transition shadow-sm"
                      >
                        <span>👉 Proceed to Client Service Dashboard</span>
                        <ArrowRight className="h-3 w-3" />
                      </button>
                    </div>
                  )}
                </div>
                <span className="mt-0.5 text-[9px] text-slate-500 px-1">{msg.timestamp}</span>
              </div>
            ))}

            {isTyping && (
              <div className="flex items-center gap-1 text-slate-400 text-xs px-2">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-emerald-400"></span>
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-emerald-400 delay-100"></span>
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-emerald-400 delay-200"></span>
                <span className="text-[10px] ml-1 text-slate-400">Assistant is thinking...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Inquiry Pills */}
          <div className="px-2.5 py-1.5 border-t border-slate-800/80 bg-slate-950/70 flex gap-1.5 overflow-x-auto no-scrollbar shrink-0">
            <button
              onClick={() => handleSendMessage("Tell me about Rent & Financial Tracking")}
              className="whitespace-nowrap rounded-full bg-slate-800 hover:bg-slate-700 px-2 py-0.5 text-[10px] text-slate-300 font-medium transition border border-slate-700/60"
            >
              🏢 Rent & Finance Tracking
            </button>
            <button
              onClick={() => handleSendMessage("How does 24/7 WhatsApp AI Support work?")}
              className="whitespace-nowrap rounded-full bg-slate-800 hover:bg-slate-700 px-2 py-0.5 text-[10px] text-slate-300 font-medium transition border border-slate-700/60"
            >
              💬 WhatsApp AI Concierge
            </button>
            <button
              onClick={() => handleSendMessage("Tell me about Google Maps Lead Generation")}
              className="whitespace-nowrap rounded-full bg-slate-800 hover:bg-slate-700 px-2 py-0.5 text-[10px] text-slate-300 font-medium transition border border-slate-700/60"
            >
              📈 Google Maps Lead Growth
            </button>
          </div>

          {/* Clean Single WhatsApp Number Placement (Positioned strictly above the chat input box) */}
          <div className="px-3 py-1.5 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs shrink-0">
            <span className="text-[11px] text-slate-400 font-medium flex items-center gap-1.5">
              <Phone className="h-3 w-3 text-emerald-400" />
              <span>Direct Services Line:</span>
            </span>
            <a
              href={SUPPORT_WHATSAPP_LINK}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-bold text-emerald-400 hover:text-emerald-300 text-[11px] transition"
            >
              <span>{SUPPORT_WHATSAPP_NUMBER}</span>
              <ExternalLink className="h-2.5 w-2.5" />
            </a>
          </div>

          {/* Chat Input Form */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="flex items-center gap-1.5 p-2.5 bg-slate-950 border-t border-slate-800 shrink-0"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about services or discuss your business..."
              className="flex-1 rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={!input.trim() || isTyping}
              className="flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-30 transition"
              title="Send"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
