"use client";

import React, { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import { CheckCircle, AlertCircle, MessageSquareHeart } from "lucide-react";

export default function PrivateFeedbackPage() {
  const [token, setToken] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [feedbackText, setFeedbackText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      setToken(params.get("token") || "");
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      setErrorMsg("Feedback link token is missing or invalid.");
      return;
    }
    setSubmitting(true);
    setErrorMsg(null);
    try {
      const res = await apiRequest(`/api/v1/growth/reviews/private-feedback/${encodeURIComponent(token)}`, {
        method: "POST",
        body: JSON.stringify({
          feedback_text: feedbackText.trim(),
          customer_name: customerName.trim() || null,
        }),
      });
      if (res.success) {
        setSubmitted(true);
      } else {
        setErrorMsg(res.error?.message || "Could not submit feedback. Please check your link.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm space-y-5">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center">
            <MessageSquareHeart className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900">Share Private Feedback</h1>
            <p className="text-xs text-slate-500">
              Your response goes directly and confidentially to our management team so we can make things right.
            </p>
          </div>
        </div>

        {submitted ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex items-start gap-3 text-sm text-emerald-900">
            <CheckCircle className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Thank you for letting us know.</p>
              <p className="text-xs text-emerald-800 mt-1">
                Our team lead has received your private note and will follow up promptly.
              </p>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {errorMsg && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 flex items-center gap-2 text-xs text-red-800">
                <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Your Name (Optional)</label>
              <input
                type="text"
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                placeholder="e.g. Ayesha"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">What could we have done better?</label>
              <textarea
                rows={4}
                required
                minLength={3}
                value={feedbackText}
                onChange={(e) => setFeedbackText(e.target.value)}
                placeholder="Tell us openly so we can resolve it immediately..."
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white py-2.5 text-sm font-semibold"
            >
              {submitting ? "Submitting..." : "Send Private Feedback"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
