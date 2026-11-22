"use client";

import React, { useEffect, useState } from "react";
import { Clock, Megaphone, TrendingUp, Users } from "lucide-react";
import { StatCard } from "../../components/dashboard/StatCard";
import { Navbar } from "../../components/shared/Navbar";
import { Sidebar } from "../../components/shared/Sidebar";
import { apiRequest } from "../../lib/api";
import { getActiveTenant, getAuthToken, isSuperAdminUser } from "../../lib/auth";

interface CampaignItem {
  id: string;
  name: string;
  platform: string;
  objective: string;
  status: string;
  budget: number;
  created_at: string;
}

interface LeadItem {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  source: string;
  status: string;
  qualification_score: number;
  metadata?: {
    website?: string | null;
    address?: string | null;
    data_source?: string | null;
  };
  created_at: string;
}

interface MarketingAnalytics {
  total_campaigns: number;
  active_campaigns: number;
  draft_campaigns: number;
  total_budget_allocated: number;
  total_leads: number;
  qualified_leads: number;
  average_qualification_score: number;
  roi_percentage: number;
}

export default function MarketingPage() {
  const [campaigns, setCampaigns] = useState<CampaignItem[]>([]);
  const [leads, setLeads] = useState<LeadItem[]>([]);
  const [analytics, setAnalytics] = useState<MarketingAnalytics | null>(null);

  const [campName, setCampName] = useState("");
  const [campPlatform, setCampPlatform] = useState("meta_ads");
  const [campObjective, setCampObjective] = useState("lead_generation");
  const [campBudget, setCampBudget] = useState("500");

  const [leadName, setLeadName] = useState("");
  const [leadEmail, setLeadEmail] = useState("");
  const [leadPhone, setLeadPhone] = useState("");
  const [leadSource, setLeadSource] = useState("whatsapp");

  const [copyChannel, setCopyChannel] = useState("whatsapp");
  const [copyTopic, setCopyTopic] = useState("");
  const [generatedCopy, setGeneratedCopy] = useState<string | null>(null);
  const [finderIndustry, setFinderIndustry] = useState("Real Estate / Property");
  const [finderLocation, setFinderLocation] = useState("Dubai");
  const [finderKeywords, setFinderKeywords] = useState("");
  const [finderLimit, setFinderLimit] = useState("8");
  const [findingLeads, setFindingLeads] = useState(false);
  const [isAdminUser, setIsAdminUser] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadMarketingWorkspace = async () => {
    const [campRes, leadRes, anaRes] = await Promise.all([
      apiRequest("/api/v1/marketing/campaigns"),
      apiRequest("/api/v1/marketing/leads"),
      apiRequest("/api/v1/marketing/analytics"),
    ]);

    if (Array.isArray(campRes)) setCampaigns(campRes);
    else if (campRes.data) setCampaigns(campRes.data);
    else if (campRes.error) setErrorMessage(campRes.error.message);

    if (Array.isArray(leadRes)) setLeads(leadRes);
    else if (leadRes.data) setLeads(leadRes.data);
    else if (leadRes.error) setErrorMessage(leadRes.error.message);

    const ana = (anaRes.data || anaRes) as MarketingAnalytics;
    if (ana && ana.total_campaigns !== undefined) setAnalytics(ana);
  };

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    if (!getActiveTenant()) {
      window.location.href = "/onboarding";
      return;
    }
    setIsAdminUser(isSuperAdminUser());
    loadMarketingWorkspace();
  }, []);

  const handleCreateCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest("/api/v1/marketing/campaigns", {
      method: "POST",
      body: JSON.stringify({
        name: campName,
        platform: campPlatform,
        objective: campObjective,
        budget: parseFloat(campBudget),
      }),
    });
    if (!res.error && (res.id || res.data?.id)) {
      setCampName("");
      setStatusMessage("Campaign created in 'draft' status and queued for Owner approval.");
      loadMarketingWorkspace();
    } else {
      setErrorMessage(res.error?.message || "Failed to save campaign draft.");
    }
  };

  const handleApproveCampaign = async (campaignId: string) => {
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest(`/api/v1/marketing/campaigns/${campaignId}/approve`, {
      method: "POST",
    });
    if (!res.error && (res.id || res.data?.id)) {
      setStatusMessage("Campaign approved and published live!");
      loadMarketingWorkspace();
    } else {
      setErrorMessage(res.error?.message || "Failed to approve campaign.");
    }
  };

  const handleCreateLead = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest("/api/v1/marketing/leads", {
      method: "POST",
      body: JSON.stringify({
        name: leadName,
        email: leadEmail || null,
        phone: leadPhone || null,
        source: leadSource,
      }),
    });
    if (!res.error && (res.id || res.data?.id)) {
      setLeadName("");
      setLeadEmail("");
      setLeadPhone("");
      setStatusMessage("Lead added to CRM.");
      loadMarketingWorkspace();
    } else {
      setErrorMessage(res.error?.message || "Failed to add lead to CRM.");
    }
  };

  const handleQualifyLead = async (leadId: string) => {
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest(`/api/v1/marketing/leads/${leadId}/qualify`, {
      method: "POST",
    });
    if (!res.error && (res.id || res.data?.id)) {
      setStatusMessage("AI Lead Qualification completed.");
      loadMarketingWorkspace();
    } else {
      setErrorMessage(res.error?.message || "Failed to qualify lead.");
    }
  };

  const handleGenerateCopy = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest("/api/v1/marketing/content/generate", {
      method: "POST",
      body: JSON.stringify({
        channel: copyChannel,
        topic: copyTopic,
        tone: "professional",
      }),
    });
    const data = res.data || res;
    if (!res.error && data?.generated_copy) {
      setGeneratedCopy(data.generated_copy);
      setStatusMessage(
        data?.provider
          ? `AI marketing copy generated via ${data.provider}.`
          : "AI marketing copy generated."
      );
    } else {
      setErrorMessage(res.error?.message || "Failed to generate marketing copy.");
    }
  };

  const handleFindLiveLeads = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMessage(null);
    setErrorMessage(null);
    setFindingLeads(true);
    try {
      const res = await apiRequest("/api/v1/marketing/leads/generate", {
        method: "POST",
        body: JSON.stringify({
          industry: finderIndustry,
          location: finderLocation.trim() || "Dubai",
          keywords: finderKeywords.trim() || undefined,
          limit: Math.min(Math.max(parseInt(finderLimit, 10) || 8, 1), 20),
        }),
      });
      const payload = res.data || res;
      if (!res.error && payload && (payload.created_count !== undefined || Array.isArray(payload.leads))) {
        const count = payload.created_count ?? payload.leads?.length ?? 0;
        const src = payload.data_source || "live_directory";
        setStatusMessage(
          `Found and added ${count} real business lead${count === 1 ? "" : "s"} in ${finderLocation} (source: ${src}).`
        );
        loadMarketingWorkspace();
      } else {
        setErrorMessage(res.error?.message || "Failed to search business leads.");
      }
    } finally {
      setFindingLeads(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Navbar />
      <div className="flex flex-1">
        <Sidebar currentPath="/marketing" />
        <main className="flex-1 min-w-0 p-4 sm:p-6 md:p-8 space-y-8 overflow-y-auto">
          <div>
            <h1 className="text-2xl font-bold text-white">Marketing, Campaigns & Lead CRM</h1>
            <p className="text-slate-400 text-sm mt-1">
              AI copy generation, multi-channel campaign orchestration with mandatory human approval, and automated lead qualification.
            </p>
          </div>

          {statusMessage && (
            <div className="p-4 rounded-lg bg-indigo-950/60 border border-indigo-700 text-indigo-200 text-sm">
              {statusMessage}
            </div>
          )}

          {errorMessage && (
            <div className="p-4 rounded-lg bg-red-950/60 border border-red-700 text-red-200 text-sm">
              {errorMessage}
            </div>
          )}

          {analytics && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <StatCard
                title="Active / Total Campaigns"
                value={`${analytics.active_campaigns} / ${analytics.total_campaigns}`}
                subtext={`$${analytics.total_budget_allocated.toLocaleString()} budget`}
                icon={Megaphone}
              />
              <StatCard
                title="Qualified Leads"
                value={`${analytics.qualified_leads} / ${analytics.total_leads}`}
                subtext={`Avg Score: ${analytics.average_qualification_score}%`}
                icon={Users}
              />
              <StatCard
                title="Drafts Awaiting Approval"
                value={String(analytics.draft_campaigns)}
                subtext="Human approval required"
                icon={Clock}
              />
              <StatCard
                title="Campaign ROI"
                value={`${analytics.roi_percentage}%`}
                subtext="Tracked revenue vs spend"
                icon={TrendingUp}
              />
            </div>
          )}

          {/* Admin-Only Live Business Lead Finder (OpenStreetMap / Google Places) */}
          {isAdminUser && (
          <div className="bg-slate-900 border border-emerald-800/60 rounded-xl p-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
              <div>
                <h2 className="text-lg font-semibold text-white">
                  Find Real Business Leads (Free Live Maps Search)
                </h2>
                <p className="text-xs text-slate-400">
                  Search any city &amp; niche to pull real companies (phone, website &amp; address) directly into your CRM — 100% free via OpenStreetMap or Google Places.
                </p>
              </div>
              <span className="inline-flex items-center rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-300">
                Zero Card Required
              </span>
            </div>
            <form onSubmit={handleFindLiveLeads} className="grid grid-cols-1 md:grid-cols-5 gap-3">
              <select
                value={finderIndustry}
                onChange={(e) => setFinderIndustry(e.target.value)}
                className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
              >
                <option value="Real Estate / Property">Real Estate / Property</option>
                <option value="Clinics / Hospitals">Clinics / Hospitals</option>
                <option value="Financing">Financing &amp; Accounting</option>
                <option value="E-Commerce">E-Commerce &amp; Retail</option>
              </select>
              <input
                type="text"
                required
                placeholder="City (e.g. Dubai, Lahore, London)"
                value={finderLocation}
                onChange={(e) => setFinderLocation(e.target.value)}
                className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
              />
              <input
                type="text"
                placeholder="Custom Keyword (e.g. dental clinic, salon)"
                value={finderKeywords}
                onChange={(e) => setFinderKeywords(e.target.value)}
                className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
              />
              <input
                type="number"
                min="1"
                max="20"
                value={finderLimit}
                onChange={(e) => setFinderLimit(e.target.value)}
                placeholder="Count (e.g. 8)"
                className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
              />
              <button
                type="submit"
                disabled={findingLeads}
                className="py-2 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-semibold transition"
              >
                {findingLeads ? "Searching Maps..." : "Find Real Leads"}
              </button>
            </form>
          </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Create Campaign */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-white mb-4">Draft Marketing Campaign</h2>
              <form onSubmit={handleCreateCampaign} className="space-y-3">
                <input
                  type="text"
                  required
                  placeholder="Campaign Name (e.g. Q4 Rent Promo)"
                  value={campName}
                  onChange={(e) => setCampName(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                />
                <div className="grid grid-cols-2 gap-3">
                  <select
                    value={campPlatform}
                    onChange={(e) => setCampPlatform(e.target.value)}
                    className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                  >
                    <option value="meta_ads">Meta Ads</option>
                    <option value="google_ads">Google Ads</option>
                    <option value="whatsapp">WhatsApp Broadcast</option>
                    <option value="linkedin">LinkedIn</option>
                  </select>
                  <input
                    type="number"
                    min="0"
                    step="10"
                    required
                    value={campBudget}
                    onChange={(e) => setCampBudget(e.target.value)}
                    placeholder="Budget (USD)"
                    className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                  />
                </div>
                <input
                  type="text"
                  required
                  value={campObjective}
                  onChange={(e) => setCampObjective(e.target.value)}
                  placeholder="Objective (e.g. lead_generation)"
                  className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                />
                <button
                  type="submit"
                  className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
                >
                  Save Campaign Draft
                </button>
              </form>
            </div>

            {/* Capture Lead */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-white mb-4">Capture New Lead</h2>
              <form onSubmit={handleCreateLead} className="space-y-3">
                <input
                  type="text"
                  required
                  placeholder="Full Name"
                  value={leadName}
                  onChange={(e) => setLeadName(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                />
                <input
                  type="email"
                  placeholder="Email Address"
                  value={leadEmail}
                  onChange={(e) => setLeadEmail(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                />
                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="text"
                    placeholder="Phone (+1...)"
                    value={leadPhone}
                    onChange={(e) => setLeadPhone(e.target.value)}
                    className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                  />
                  <select
                    value={leadSource}
                    onChange={(e) => setLeadSource(e.target.value)}
                    className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                  >
                    <option value="whatsapp">WhatsApp</option>
                    <option value="meta_ads">Meta Ads</option>
                    <option value="website">Website</option>
                    <option value="referral">Referral</option>
                  </select>
                </div>
                <button
                  type="submit"
                  className="w-full py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium"
                >
                  Add Lead to CRM
                </button>
              </form>
            </div>

            {/* AI Content Generator */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-white mb-4">AI Ad & Copy Studio</h2>
              <form onSubmit={handleGenerateCopy} className="space-y-3">
                <select
                  value={copyChannel}
                  onChange={(e) => setCopyChannel(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                >
                  <option value="whatsapp">WhatsApp Template</option>
                  <option value="meta_ads">Meta Ad Copy</option>
                  <option value="linkedin">LinkedIn Post</option>
                  <option value="email">Email Sequence</option>
                </select>
                <input
                  type="text"
                  required
                  placeholder="Offer or Campaign Topic"
                  value={copyTopic}
                  onChange={(e) => setCopyTopic(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                />
                <button
                  type="submit"
                  className="w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-medium"
                >
                  Generate AI Copy
                </button>
              </form>
              {generatedCopy && (
                <div className="mt-3 p-3 rounded bg-slate-950 border border-slate-800 text-xs text-slate-300 whitespace-pre-wrap">
                  {generatedCopy}
                </div>
              )}
            </div>
          </div>

          {/* Campaigns Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-5 border-b border-slate-800">
              <h2 className="text-lg font-semibold text-white">Campaigns & Human Approval Gate</h2>
            </div>
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-950 text-slate-400 text-xs uppercase">
                <tr>
                  <th className="py-3 px-4">Campaign</th>
                  <th className="py-3 px-4">Platform</th>
                  <th className="py-3 px-4">Budget</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {campaigns.map((c) => (
                  <tr key={c.id}>
                    <td className="py-3 px-4 font-medium text-white">{c.name}</td>
                    <td className="py-3 px-4 text-slate-300">{c.platform}</td>
                    <td className="py-3 px-4 text-slate-300">${c.budget.toLocaleString()}</td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          c.status === "active"
                            ? "bg-emerald-950 text-emerald-300"
                            : "bg-amber-950 text-amber-300"
                        }`}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      {c.status !== "active" && (
                        <button
                          onClick={() => handleApproveCampaign(c.id)}
                          className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium"
                        >
                          Approve & Publish
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Leads Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-5 border-b border-slate-800">
              <h2 className="text-lg font-semibold text-white">Lead Funnel & AI Qualification</h2>
            </div>
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-950 text-slate-400 text-xs uppercase">
                <tr>
                  <th className="py-3 px-4">Name</th>
                  <th className="py-3 px-4">Contact</th>
                  <th className="py-3 px-4">Source</th>
                  <th className="py-3 px-4">AI Score</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {leads.map((l) => (
                  <tr key={l.id}>
                    <td className="py-3 px-4">
                      <div className="font-medium text-white">{l.name}</div>
                      {l.metadata?.address && (
                        <div className="text-[11px] text-slate-500 truncate max-w-xs" title={l.metadata.address}>
                          {l.metadata.address}
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-400 space-y-0.5">
                      <div>{l.phone || l.email || "—"}</div>
                      {l.email && l.phone && <div className="text-[11px] text-slate-500">{l.email}</div>}
                      {l.metadata?.website && (
                        <a
                          href={l.metadata.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block text-[11px] text-emerald-400 hover:underline truncate max-w-[200px]"
                        >
                          {l.metadata.website.replace(/^https?:\/\//, "")}
                        </a>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-300">{l.source}</td>
                    <td className="py-3 px-4 font-semibold text-indigo-300">
                      {l.qualification_score}%
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-xs">
                        {l.status}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      {isAdminUser ? (
                        <button
                          onClick={() => handleQualifyLead(l.id)}
                          className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
                        >
                          AI Qualify
                        </button>
                      ) : Number(l.qualification_score || 0) > 0 ? (
                        <span className="inline-flex items-center rounded bg-emerald-950/80 border border-emerald-800 px-2.5 py-1 text-[11px] font-semibold text-emerald-300">
                          Admin AI Verified ({l.qualification_score}%)
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded bg-amber-950/60 border border-amber-800/60 px-2.5 py-1 text-[11px] font-medium text-amber-300">
                          Pending Admin Scoring
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </main>
      </div>
    </div>
  );
}
