"use client";

import React, { useEffect, useState } from "react";
import { X, Send, CheckCircle2, AlertCircle, MessageSquare, LifeBuoy, ExternalLink } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { SUPPORT_WHATSAPP_NUMBER, SUPPORT_WHATSAPP_LINK } from "@/lib/auth";

export interface SupportRequestModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultSubject?: string;
  defaultCategory?: string;
  defaultMessage?: string;
  defaultProvider?: string;
  defaultServiceSlug?: string;
}

interface SupportTicketResponse {
  id?: string;
  ticket_id?: string;
  status?: string;
  subject?: string;
  whatsapp_number?: string;
  whatsapp_url?: string;
  created_at?: string;
}

export function SupportRequestModal({
  isOpen,
  onClose,
  defaultSubject = "",
  defaultCategory = "general",
  defaultMessage = "",
  defaultProvider,
  defaultServiceSlug,
}: SupportRequestModalProps) {
  const [subject, setSubject] = useState(defaultSubject);
  const [category, setCategory] = useState(defaultCategory);
  const [priority, setPriority] = useState("normal");
  const [contactPreference, setContactPreference] = useState("whatsapp");
  const [message, setMessage] = useState(defaultMessage);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedTicket, setSubmittedTicket] = useState<SupportTicketResponse | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSubject(defaultSubject);
      setCategory(defaultCategory || "general");
      setMessage(defaultMessage);
      setPriority("normal");
      setContactPreference("whatsapp");
      setError(null);
      setSubmittedTicket(null);
    }
  }, [isOpen, defaultSubject, defaultCategory, defaultMessage]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subject.trim() || !message.trim()) {
      setError("Please enter both a subject and details for your support request.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const payload: Record<string, string> = {
        subject: subject.trim(),
        message: message.trim(),
        category,
        priority,
        contact_preference: contactPreference,
      };
      if (defaultProvider) payload.provider = defaultProvider;
      if (defaultServiceSlug) payload.service_slug = defaultServiceSlug;

      const res = await apiRequest<SupportTicketResponse>("/api/v1/support/requests", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      const ticketData = res.data?.ticket_id || res.data?.id ? res.data : (res as unknown as SupportTicketResponse);
      if (!res.error && (ticketData?.ticket_id || ticketData?.id)) {
        setSubmittedTicket(ticketData);
      } else {
        setError(
          res.error?.message ||
            `Could not submit request right now. Please message our team directly on WhatsApp (${SUPPORT_WHATSAPP_NUMBER}).`
        );
      }
    } catch {
      setError(
        `Network error submitting request. Please contact us directly on WhatsApp (${SUPPORT_WHATSAPP_NUMBER}).`
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="support-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-950 text-slate-100 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-600 text-white">
              <LifeBuoy className="h-5 w-5" />
            </div>
            <div>
              <h2 id="support-modal-title" className="text-sm font-bold text-white">
                Request Managed Support or Assisted Setup
              </h2>
              <p className="text-[11px] text-slate-400">
                Submit a ticket to our onboarding engineers or reach us directly on WhatsApp
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close support dialog"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {submittedTicket ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 space-y-2">
                <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
                  <CheckCircle2 className="h-5 w-5 shrink-0" />
                  <span>Support Request Received</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Your request has been logged for our managed operations team.
                  {submittedTicket.ticket_id && (
                    <>
                      {" "}
                      Ticket ID:{" "}
                      <strong className="font-mono text-white">{submittedTicket.ticket_id}</strong>
                    </>
                  )}
                </p>
              </div>

              <div className="flex flex-col sm:flex-row gap-2 justify-end">
                <a
                  href={submittedTicket.whatsapp_url || SUPPORT_WHATSAPP_LINK}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition"
                >
                  <MessageSquare className="h-3.5 w-3.5" />
                  <span>Chat on WhatsApp ({submittedTicket.whatsapp_number || SUPPORT_WHATSAPP_NUMBER})</span>
                  <ExternalLink className="h-3 w-3" />
                </a>
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 transition"
                >
                  Done
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
                  <AlertCircle className="h-4 w-4 shrink-0 text-red-400 mt-0.5" />
                  <span>{error}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Subject *
                </label>
                <input
                  type="text"
                  required
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="e.g., Assisted setup for WhatsApp Cloud API"
                  className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Category
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
                  >
                    <option value="integration_setup">Integration Setup</option>
                    <option value="service_configuration">Service Configuration</option>
                    <option value="billing_payment">Billing &amp; Payment</option>
                    <option value="technical_support">Technical Support</option>
                    <option value="general">General Assistance</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Priority
                  </label>
                  <select
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                    className="w-full rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
                  >
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Contact Via
                  </label>
                  <select
                    value={contactPreference}
                    onChange={(e) => setContactPreference(e.target.value)}
                    className="w-full rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
                  >
                    <option value="whatsapp">WhatsApp ({SUPPORT_WHATSAPP_NUMBER})</option>
                    <option value="email">Email</option>
                    <option value="dashboard">Portal Notification</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Details *
                </label>
                <textarea
                  rows={4}
                  required
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Describe what you need help setting up, any accounts to connect, or questions about your package..."
                  className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                />
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-slate-800">
                <a
                  href={SUPPORT_WHATSAPP_LINK}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-400 hover:text-emerald-300"
                >
                  <MessageSquare className="h-3.5 w-3.5" />
                  <span>WhatsApp Direct: {SUPPORT_WHATSAPP_NUMBER}</span>
                </a>

                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={onClose}
                    className="rounded-lg border border-slate-700 px-3.5 py-2 text-xs font-medium text-slate-300 hover:bg-slate-900 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 transition"
                  >
                    <Send className="h-3.5 w-3.5" />
                    <span>{submitting ? "Submitting..." : "Submit Request"}</span>
                  </button>
                </div>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
