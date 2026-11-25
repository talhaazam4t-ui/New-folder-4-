"use client";

import React, { useState } from "react";
import { HunterLead } from "./types";
import {
  Search,
  Sparkles,
  PhoneCall,
  Star,
  AlertTriangle,
  ExternalLink,
  Flame,
  Bot,
  CheckCircle,
  Upload,
  UserPlus,
} from "lucide-react";

interface Props {
  countries: string[];
  citiesByCountry: Record<string, string[]>;
  categories: string[];
  leads: HunterLead[];
  apiKeysStatus: {
    openstreetmap_free_ready?: boolean;
    google_places_configured: boolean;
    apollo_configured: boolean;
  };
  freeOsmOn?: boolean;
  onEnableFreeOsm?: () => void;
  searching: boolean;
  busyLeadId: string | null;
  onSearch: (payload: {
    country: string;
    city: string;
    category: string;
    source_mode: "openstreetmap_free" | "google_places" | "apollo" | "hybrid";
    max_results: number;
  }) => void;
  onEnrichApollo: (leadId: string) => void;
  onImportApolloCsv: (payload: {
    csv_text: string;
    default_country: string;
    default_city: string;
    default_category: string;
  }) => Promise<void>;
  onSaveManualOwner: (
    leadId: string,
    payload: {
      owner_name?: string;
      owner_title?: string;
      email?: string;
      linkedin_url?: string;
      phone?: string;
    }
  ) => Promise<void>;
  onGenerateDemo: (leadId: string) => void;
  onPromoteHot: (leadId: string) => void;
  onJumpToCallList: () => void;
}

export function LeadFinderTab({
  countries,
  citiesByCountry,
  categories,
  leads,
  apiKeysStatus,
  freeOsmOn = false,
  onEnableFreeOsm,
  searching,
  busyLeadId,
  onSearch,
  onEnrichApollo,
  onImportApolloCsv,
  onSaveManualOwner,
  onGenerateDemo,
  onPromoteHot,
  onJumpToCallList,
}: Props) {
  const [country, setCountry] = useState(countries[0] || "USA");
  const [city, setCity] = useState((citiesByCountry[countries[0] || "USA"] || ["New York"])[0]);
  const [category, setCategory] = useState(categories[0] || "Dental Clinic");
  const [sourceMode, setSourceMode] = useState<"openstreetmap_free" | "google_places" | "apollo" | "hybrid">("openstreetmap_free");
  const [importingCsv, setImportingCsv] = useState(false);
  const [editingLead, setEditingLead] = useState<HunterLead | null>(null);
  const [ownerForm, setOwnerForm] = useState({
    owner_name: "",
    owner_title: "",
    email: "",
    linkedin_url: "",
    phone: "",
  });

  const openOwnerEditor = (lead: HunterLead) => {
    setEditingLead(lead);
    setOwnerForm({
      owner_name: lead.owner_name || "",
      owner_title: lead.owner_title || "Owner / Founder",
      email: lead.email || "",
      linkedin_url: lead.linkedin_url || "",
      phone: lead.phone || "",
    });
  };

  const handleCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportingCsv(true);
    try {
      const csvText = await file.text();
      await onImportApolloCsv({
        csv_text: csvText,
        default_country: country,
        default_city: city,
        default_category: category,
      });
    } finally {
      setImportingCsv(false);
      e.target.value = "";
    }
  };

  const availableCities = citiesByCountry[country] || ["New York", "London", "Toronto", "Sydney", "Dubai"];

  const handleCountryChange = (nextCountry: string) => {
    setCountry(nextCountry);
    const nextCities = citiesByCountry[nextCountry] || [];
    if (nextCities.length > 0 && !nextCities.includes(city)) {
      setCity(nextCities[0]);
    }
  };

  return (
    <div className="space-y-6">
      {/* Free OpenStreetMap Ready Banner OR Missing Paid Key Banner */}
      {sourceMode === "openstreetmap_free" ? (
        <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/30 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs text-emerald-200">
          <div className="flex items-start gap-3">
            <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold">100% Free Real-Data Mode Active ($0 — No API Key or Credit Card Needed):</p>
              <p className="mt-0.5 text-emerald-300/90">
                Searches live international businesses via OpenStreetMap Overpass/Nominatim and scans each business website for AI widgets, emails, phone numbers, and LinkedIn pages.
              </p>
            </div>
          </div>
          {!freeOsmOn && onEnableFreeOsm && (
            <button
              type="button"
              onClick={onEnableFreeOsm}
              className="shrink-0 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3.5 py-2 text-xs font-bold text-white"
            >
              Turn ON Free Finder
            </button>
          )}
        </div>
      ) : (
        (!apiKeysStatus.google_places_configured || !apiKeysStatus.apollo_configured) && (
          <div className="rounded-xl border border-amber-500/40 bg-amber-950/30 p-4 flex items-start gap-3 text-xs text-amber-200">
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold">Strict Real-Data Protection Active (Zero Dummy Data):</p>
              <p className="mt-0.5 text-amber-300/90">
                {!apiKeysStatus.google_places_configured && !apiKeysStatus.apollo_configured
                  ? "Please add Google Places API Key / Apollo API Key in .env before running live searches."
                  : !apiKeysStatus.google_places_configured
                  ? "Please add Google Places API Key in .env to run Google Places / Hybrid searches."
                  : "Please add Apollo API Key in .env to run Apollo Decision-Maker searches or enrichment."}
              </p>
            </div>
          </div>
        )
      )}

      {/* International Filter & Dual-Source Toggle */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-5 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div>
            <label className="block font-semibold text-slate-300 mb-1.5">Country</label>
            <select
              value={country}
              onChange={(e) => handleCountryChange(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            >
              {countries.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block font-semibold text-slate-300 mb-1.5">City</label>
            <select
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            >
              {availableCities.map((ct) => (
                <option key={ct} value={ct}>
                  {ct}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block font-semibold text-slate-300 mb-1.5">Business Category</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            >
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 pt-2 border-t border-slate-800">
          <div className="flex flex-wrap gap-2 text-xs">
            {[
              { id: "openstreetmap_free", label: "Free OpenStreetMap + AI Scanner ($0)" },
              { id: "google_places", label: "Google Places Only" },
              { id: "apollo", label: "Apollo.io Paid API Only" },
              { id: "hybrid", label: "Hybrid: Google Places + Apollo Enrichment" },
            ].map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setSourceMode(opt.id as any)}
                className={`rounded-lg px-3 py-1.5 font-semibold border transition ${
                  sourceMode === opt.id
                    ? "border-blue-500 bg-blue-600 text-white"
                    : "border-slate-700 bg-slate-950 text-slate-300 hover:border-blue-500/50"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            disabled={searching}
            onClick={() =>
              onSearch({
                country,
                city,
                category,
                source_mode: sourceMode,
                max_results: 8,
              })
            }
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-5 py-2.5 text-xs font-bold text-white shadow-lg shadow-blue-900/30"
          >
            <Search className="h-4 w-4" />
            <span>{searching ? "Hunting & Detecting AI..." : "Hunt Real Leads"}</span>
          </button>
        </div>
      </div>

      {/* Apollo Free Tier (75 Free Web Credits/Mo) Direct Bridge */}
      <div className="rounded-xl border border-blue-500/30 bg-slate-900/90 p-4 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div className="text-xs">
          <p className="font-bold text-blue-300">
            Apollo Free Tier Bridge (Use Your 75 Free Web Credits/Mo at $0 Before Upgrading)
          </p>
          <p className="text-slate-400 mt-0.5">
            Find Dental/Medical/Law/Real Estate decision-makers inside Apollo Free Web UI, export CSV (or reveal a No-AI lead&apos;s owner via &ldquo;Apollo Free&rdquo;), and import directly into TALOX AI Detector.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <a
            href="https://app.apollo.io/#/people"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-950 hover:border-blue-500 px-3 py-2 text-xs font-semibold text-blue-300"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            <span>Open Apollo Free Search</span>
          </a>
          <label className="cursor-pointer inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 px-3.5 py-2 text-xs font-bold text-white">
            <Upload className="h-3.5 w-3.5" />
            <span>{importingCsv ? "Importing & Scanning AI..." : "Import Apollo CSV (.csv)"}</span>
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={importingCsv}
              onChange={handleCsvUpload}
              className="hidden"
            />
          </label>
        </div>
      </div>

      {/* Inline Manual Apollo Free Owner Save Modal */}
      {editingLead && (
        <div className="rounded-xl border border-blue-500/60 bg-slate-900 p-4 space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-bold text-white">
              Save Apollo Free Owner Details — {editingLead.business_name}
            </span>
            <button
              type="button"
              onClick={() => setEditingLead(null)}
              className="text-slate-400 hover:text-white"
            >
              Close
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5">
            <input
              type="text"
              placeholder="Owner Name"
              value={ownerForm.owner_name}
              onChange={(e) => setOwnerForm({ ...ownerForm, owner_name: e.target.value })}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            />
            <input
              type="text"
              placeholder="Title (e.g. Founder)"
              value={ownerForm.owner_title}
              onChange={(e) => setOwnerForm({ ...ownerForm, owner_title: e.target.value })}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            />
            <input
              type="email"
              placeholder="Verified Email"
              value={ownerForm.email}
              onChange={(e) => setOwnerForm({ ...ownerForm, email: e.target.value })}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            />
            <input
              type="text"
              placeholder="LinkedIn URL"
              value={ownerForm.linkedin_url}
              onChange={(e) => setOwnerForm({ ...ownerForm, linkedin_url: e.target.value })}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            />
            <input
              type="text"
              placeholder="Direct Phone"
              value={ownerForm.phone}
              onChange={(e) => setOwnerForm({ ...ownerForm, phone: e.target.value })}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setEditingLead(null)}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-slate-300"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={busyLeadId === editingLead.id}
              onClick={async () => {
                const targetId = editingLead.id;
                await onSaveManualOwner(targetId, ownerForm);
                setEditingLead(null);
              }}
              className="rounded-lg bg-emerald-600 hover:bg-emerald-500 px-4 py-1.5 font-bold text-white"
            >
              Save &amp; Score Hot Lead
            </button>
          </div>
        </div>
      )}

      {/* Leads Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 bg-slate-950 text-[11px] uppercase text-slate-400">
              <tr>
                <th className="py-3 px-4">Business Name</th>
                <th className="py-3 px-4">Decision Maker (Apollo)</th>
                <th className="py-3 px-4">Country / City</th>
                <th className="py-3 px-4">Phone &amp; Verified Email</th>
                <th className="py-3 px-4">Rating</th>
                <th className="py-3 px-4">Source</th>
                <th className="py-3 px-4">AI Status</th>
                <th className="py-3 px-4">Interest Score</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 text-slate-200">
              {leads.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-10 text-center text-slate-400">
                    No leads discovered yet. Enable Google Places / Apollo in Control Panel and run a search above.
                  </td>
                </tr>
              ) : (
                leads.map((lead) => (
                  <tr key={lead.id} className="hover:bg-slate-800/40">
                    <td className="py-3 px-4">
                      <div className="font-bold text-white flex items-center gap-2">
                        {lead.favicon_url && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={lead.favicon_url} alt="" className="h-4 w-4 rounded-sm shrink-0" />
                        )}
                        <span>{lead.business_name}</span>
                      </div>
                      <div className="text-[11px] text-slate-400">{lead.category}</div>
                    </td>
                    <td className="py-3 px-4">
                      {lead.owner_name ? (
                        <div>
                          <div className="font-semibold text-blue-300">{lead.owner_name}</div>
                          <div className="text-[11px] text-slate-400">{lead.owner_title || "Decision Maker"}</div>
                          {lead.linkedin_url && (
                            <a
                              href={lead.linkedin_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-[10px] text-cyan-400 hover:underline"
                            >
                              <span>LinkedIn</span>
                              <ExternalLink className="h-2.5 w-2.5" />
                            </a>
                          )}
                        </div>
                      ) : (
                        <div className="space-y-0.5">
                          <span className="text-slate-400 text-[11px]">
                            {lead.website ? "Website Contact Audit" : "Not enriched yet"}
                          </span>
                          {lead.linkedin_url && (
                            <div>
                              <a
                                href={lead.linkedin_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-[10px] text-cyan-400 hover:underline"
                              >
                                <span>LinkedIn</span>
                                <ExternalLink className="h-2.5 w-2.5" />
                              </a>
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <div>{lead.city}</div>
                      <div className="text-[11px] text-slate-400">{lead.country}</div>
                    </td>
                    <td className="py-3 px-4 space-y-0.5">
                      <div className="font-mono text-[11px]">{lead.phone || "No phone"}</div>
                      <div className="flex items-center gap-1 text-[11px] text-slate-300">
                        <span className="truncate max-w-[160px]">{lead.email || "No email"}</span>
                        {lead.email_verified && <CheckCircle className="h-3 w-3 text-emerald-400 shrink-0" />}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span className="inline-flex items-center gap-1 font-semibold text-amber-300">
                        <Star className="h-3 w-3 fill-amber-400 text-amber-400" />
                        {Number(lead.rating || 0).toFixed(1)}
                      </span>
                      <div className="text-[10px] text-slate-400">{lead.total_reviews} reviews</div>
                    </td>
                    <td className="py-3 px-4">
                      <span className="rounded-full border border-slate-700 bg-slate-950 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-300">
                        {lead.lead_source === "openstreetmap_free"
                          ? "OSM Free ($0)"
                          : lead.lead_source === "google_places"
                          ? "Places"
                          : lead.lead_source === "apollo"
                          ? "Apollo"
                          : "Hybrid"}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      {lead.has_ai ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-rose-950/60 border border-rose-500/40 px-2.5 py-0.5 text-[10px] font-bold text-rose-300">
                          <Bot className="h-3 w-3" /> Has AI / Chat
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/60 border border-emerald-500/40 px-2.5 py-0.5 text-[10px] font-bold text-emerald-300">
                          No AI - Good Lead
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`rounded-md px-2 py-1 font-mono text-xs font-extrabold ${
                          lead.interest_score >= 80
                            ? "bg-emerald-500/20 text-emerald-300"
                            : lead.interest_score >= 50
                            ? "bg-amber-500/20 text-amber-300"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {lead.interest_score}/100
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="inline-flex flex-wrap justify-end gap-1.5">
                        <a
                          href={`https://app.apollo.io/#/people?qKeywords=${encodeURIComponent(
                            `${lead.business_name} ${lead.city}`
                          )}`}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-950 hover:border-blue-500 px-2 py-1 text-[10px] font-semibold text-blue-300"
                        >
                          <ExternalLink className="h-3 w-3" /> Apollo Free
                        </a>
                        <button
                          type="button"
                          onClick={() => openOwnerEditor(lead)}
                          className="inline-flex items-center gap-1 rounded border border-cyan-500/40 bg-cyan-950/40 px-2 py-1 text-[10px] font-semibold text-cyan-300 hover:bg-cyan-900/50"
                        >
                          <UserPlus className="h-3 w-3" /> Save Owner
                        </button>
                        {apiKeysStatus.apollo_configured && (
                          <button
                            type="button"
                            disabled={busyLeadId === lead.id}
                            onClick={() => onEnrichApollo(lead.id)}
                            className="rounded border border-slate-700 bg-slate-950 hover:border-blue-500 px-2 py-1 text-[10px] font-semibold text-blue-300"
                          >
                            API Enrich
                          </button>
                        )}
                        <button
                          type="button"
                          disabled={busyLeadId === lead.id}
                          onClick={() => onGenerateDemo(lead.id)}
                          className="inline-flex items-center gap-1 rounded bg-blue-600 hover:bg-blue-500 px-2 py-1 text-[10px] font-semibold text-white"
                        >
                          <Sparkles className="h-3 w-3" /> Generate Demo
                        </button>
                        <button
                          type="button"
                          onClick={onJumpToCallList}
                          className="inline-flex items-center gap-1 rounded border border-emerald-500/40 bg-emerald-950/40 px-2 py-1 text-[10px] font-semibold text-emerald-300 hover:bg-emerald-900/50"
                        >
                          <PhoneCall className="h-3 w-3" /> Call Now
                        </button>
                        <button
                          type="button"
                          disabled={busyLeadId === lead.id}
                          onClick={() => onPromoteHot(lead.id)}
                          className="inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-950/40 px-2 py-1 text-[10px] font-semibold text-amber-300 hover:bg-amber-900/50"
                        >
                          <Flame className="h-3 w-3" /> Add to Hot Lead
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
