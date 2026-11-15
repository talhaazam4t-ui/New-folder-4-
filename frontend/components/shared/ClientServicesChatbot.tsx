"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  MessageSquare,
  X,
  Send,
  Phone,
  Sparkles,
  ExternalLink,
  ChevronDown,
  Bot,
} from "lucide-react";
import { SUPPORT_WHATSAPP_NUMBER, SUPPORT_WHATSAPP_LINK } from "@/lib/auth";

interface ChatMessage {
  id: string;
  sender: "bot" | "user";
  text: string;
  timestamp: string;
  actionUrl?: string;
  actionLabel?: string;
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
      text: "👋 Welcome to Teloxtech! I am your AI Services Concierge. How can I help optimize your business today? You can ask me about our managed services or contact our team directly on WhatsApp at 03238300330.",
      timestamp: "Just now",
      actionUrl: SUPPORT_WHATSAPP_LINK,
      actionLabel: `Direct WhatsApp: ${SUPPORT_WHATSAPP_NUMBER}`,
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

  const handleSendMessage = (textToSend?: string) => {
    const userQuery = (textToSend || input).trim();
    if (!userQuery) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: userQuery,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMessage]);
    if (!textToSend) setInput("");
    setIsTyping(true);

    setTimeout(() => {
      let botResponse = "";
      let actionUrl: string | undefined = SUPPORT_WHATSAPP_LINK;
      let actionLabel: string | undefined = `Chat on WhatsApp: ${SUPPORT_WHATSAPP_NUMBER}`;

      const lower = userQuery.toLowerCase();

      if (lower.includes("price") || lower.includes("cost") || lower.includes("package") || lower.includes("pricing")) {
        botResponse =
          "Our managed plans start from $99/mo with tailored packages for Real Estate, Clinics, and E-Commerce. For custom pricing or volume discounts, reach out to our team on WhatsApp at 03238300330.";
      } else if (lower.includes("whatsapp") || lower.includes("wsp") || lower.includes("number")) {
        botResponse =
          "You can connect directly with our services support specialists on WhatsApp at 03238300330 for live onboarding, custom prompt tuning, or payment confirmations.";
      } else if (lower.includes("finance") || lower.includes("rent") || lower.includes("ledger")) {
        botResponse =
          "Our Business Financial Tracking service automates rent collection reminders, expense logging, and double-entry reconciliation. Want us to connect your bank feeds? Contact us on WhatsApp at 03238300330.";
      } else if (lower.includes("marketing") || lower.includes("lead") || lower.includes("growth")) {
        botResponse =
          "The Marketing & Growth Engine automates campaign calendars, lead scoring, and multi-channel outreach. We configure this completely for you. Chat with us on WhatsApp at 03238300330 to get started.";
      } else if (lower.includes("service") || lower.includes("offer") || lower.includes("what")) {
        botResponse =
          "We offer Done-For-You Managed AI Services including: 1) Business Finance & Rent Tracking, 2) WhatsApp Inbound/Outbound Automation, and 3) Autonomous Lead Growth. Speak with our experts directly on WhatsApp: 03238300330.";
      } else {
        botResponse =
          "Thank you for your message! Our AI platform handles all automated operations for your workspace. For custom inquiries or direct client support, our team is available on WhatsApp at 03238300330.";
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `bot-${Date.now()}`,
          sender: "bot",
          text: botResponse,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          actionUrl,
          actionLabel,
        },
      ]);
      setIsTyping(false);
    }, 600);
  };

  return (
    <div className="fixed bottom-5 right-5 z-50">
      {/* Floating Toggle Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="group flex items-center gap-2.5 rounded-full bg-emerald-600 px-4 py-3 text-white shadow-xl hover:bg-emerald-500 focus:outline-none focus:ring-4 focus:ring-emerald-400/40 transition-all duration-200"
          title="Open Services & WhatsApp Chatbot"
        >
          <div className="relative">
            <MessageSquare className="h-5 w-5" />
            <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-300 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-white"></span>
            </span>
          </div>
          <span className="font-semibold text-xs tracking-wide">
            Services Chat (WhatsApp: {SUPPORT_WHATSAPP_NUMBER})
          </span>
        </button>
      )}

      {/* Chat Window */}
      {isOpen && (
        <div className="flex flex-col w-96 max-w-[calc(100vw-2rem)] h-[520px] rounded-2xl bg-white border border-slate-200 shadow-2xl overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-200">
          {/* Header */}
          <div className="flex items-center justify-between bg-slate-900 px-4 py-3 text-white">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500 text-slate-950 font-bold">
                <Bot className="h-4 w-4 text-white" />
              </div>
              <div>
                <h3 className="text-xs font-bold leading-tight">Teloxtech Services Assistant</h3>
                <p className="text-[10px] text-emerald-400 font-medium">
                  WhatsApp Support: {SUPPORT_WHATSAPP_NUMBER}
                </p>
              </div>
            </div>

            <button
              onClick={() => setIsOpen(false)}
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition"
              title="Close Chat"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Quick WhatsApp Contact Ribbon */}
          <div className="flex items-center justify-between bg-emerald-50 border-b border-emerald-100 px-3 py-2 text-xs">
            <span className="text-[11px] font-medium text-emerald-900">
              Direct Services Line (WhatsApp):
            </span>
            <a
              href={SUPPORT_WHATSAPP_LINK}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-bold text-emerald-700 hover:text-emerald-800"
            >
              <Phone className="h-3 w-3" />
              <span>{SUPPORT_WHATSAPP_NUMBER}</span>
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>

          {/* Messages Container */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/50">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed shadow-sm ${
                    msg.sender === "user"
                      ? "bg-emerald-600 text-white rounded-br-none"
                      : "bg-white text-slate-800 border border-slate-200 rounded-bl-none"
                  }`}
                >
                  <p>{msg.text}</p>

                  {msg.actionUrl && (
                    <a
                      href={msg.actionUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2.5 flex items-center justify-center gap-1.5 rounded-lg bg-emerald-500 text-white px-2.5 py-1.5 text-[11px] font-semibold shadow hover:bg-emerald-600 transition"
                    >
                      <Phone className="h-3 w-3" />
                      <span>{msg.actionLabel || `WhatsApp: ${SUPPORT_WHATSAPP_NUMBER}`}</span>
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
                <span className="mt-1 text-[10px] text-slate-400 px-1">{msg.timestamp}</span>
              </div>
            ))}

            {isTyping && (
              <div className="flex items-center gap-1 text-slate-400 text-xs px-2">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"></span>
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 delay-100"></span>
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 delay-200"></span>
                <span className="text-[10px] ml-1">Assistant is typing...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Prompt Suggestions */}
          <div className="p-2 border-t border-slate-100 bg-white flex gap-1.5 overflow-x-auto no-scrollbar">
            <button
              onClick={() => handleSendMessage("What services are offered?")}
              className="whitespace-nowrap rounded-full bg-slate-100 hover:bg-slate-200 px-2.5 py-1 text-[10px] text-slate-600 font-medium transition"
            >
              Services Overview
            </button>
            <button
              onClick={() => handleSendMessage("How do I contact WhatsApp support?")}
              className="whitespace-nowrap rounded-full bg-emerald-50 hover:bg-emerald-100 px-2.5 py-1 text-[10px] text-emerald-700 font-semibold transition"
            >
              WhatsApp ({SUPPORT_WHATSAPP_NUMBER})
            </button>
            <button
              onClick={() => handleSendMessage("Pricing & Packages")}
              className="whitespace-nowrap rounded-full bg-slate-100 hover:bg-slate-200 px-2.5 py-1 text-[10px] text-slate-600 font-medium transition"
            >
              Pricing
            </button>
          </div>

          {/* Input Form */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="flex items-center gap-2 p-3 border-t border-slate-200 bg-white"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about services or WhatsApp 03238300330..."
              className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800 placeholder-slate-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
            <button
              type="submit"
              disabled={!input.trim()}
              className="flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-40 transition"
              title="Send Message"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
