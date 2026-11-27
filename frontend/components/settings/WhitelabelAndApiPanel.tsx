"use client";

import React, { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import { Palette, KeyRound, Plus, Trash2, Copy, CheckCircle2, Building2 } from "lucide-react";

interface WhitelabelAndApiPanelProps {
  onStatusMessage: (msg: string) => void;
  onErrorMessage: (msg: string) => void;
}

export function WhitelabelAndApiPanel({
  onStatusMessage,
  onErrorMessage,
}: WhitelabelAndApiPanelProps) {
  const [whitelabel, setWhitelabel] = useState({
    brand_name: "Talox Tech Stream",
    logo_url: "",
    primary_color: "#2563EB",
    accent_color: "#10B981",
    custom_domain: "",
    support_email: "",
    hide_powered_by: false,
    agency_reseller_enabled: false,
  });
  const [savingWl, setSavingWl] = useState(false);

  // Agency Sub-Tenant Form
  const [subForm, setSubForm] = useState({
    client_name: "",
    client_slug: "",
    industry: "Clinics / Hospitals",
  });
  const [creatingSub, setCreatingSub] = useState(false);

  // Scoped Developer API Keys
  const [apiKeys, setApiKeys] = useState<any[]>([]);
  const [keyName, setKeyName] = useState("Production Integration Key");
  const [newlyCreatedSecret, setNewlyCreatedSecret] = useState<string | null>(null);
  const [creatingKey, setCreatingKey] = useState(false);

  const loadPhase5Settings = async () => {
    const [wlRes, keysRes] = await Promise.all([
      apiRequest("/api/v1/whitelabel/config"),
      apiRequest("/api/v1/developer/keys"),
    ]);

    if (wlRes.data) {
      setWhitelabel({
        brand_name: wlRes.data.brand_name || "Talox Tech Stream",
        logo_url: wlRes.data.logo_url || "",
        primary_color: wlRes.data.primary_color || "#2563EB",
        accent_color: wlRes.data.accent_color || "#10B981",
        custom_domain: wlRes.data.custom_domain || "",
        support_email: wlRes.data.support_email || "",
        hide_powered_by: Boolean(wlRes.data.hide_powered_by),
        agency_reseller_enabled: Boolean(wlRes.data.agency_reseller_enabled),
      });
    }
    if (keysRes.data?.items && Array.isArray(keysRes.data.items)) {
      setApiKeys(keysRes.data.items);
    }
  };

  useEffect(() => {
    loadPhase5Settings();
  }, []);

  const handleSaveWhitelabel = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingWl(true);
    try {
      const res = await apiRequest("/api/v1/whitelabel/config", {
        method: "PUT",
        body: JSON.stringify({
          ...whitelabel,
          custom_domain: whitelabel.custom_domain.trim() || null,
          logo_url: whitelabel.logo_url.trim() || null,
          support_email: whitelabel.support_email.trim() || null,
        }),
      });
      if (res.data && !res.error) {
        onStatusMessage("White-Label branding, custom domain, and reseller settings saved!");
        await loadPhase5Settings();
      } else {
        onErrorMessage(res.error?.message || "Failed to update White-Label settings.");
      }
    } finally {
      setSavingWl(false);
    }
  };

  const handleCreateSubtenant = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subForm.client_name.trim() || !subForm.client_slug.trim()) return;
    setCreatingSub(true);
    try {
      const res = await apiRequest("/api/v1/whitelabel/agency/subtenants", {
        method: "POST",
        body: JSON.stringify(subForm),
      });
      if (res.data && !res.error) {
        onStatusMessage(
          `Agency sub-tenant "${res.data.name}" (/${res.data.slug}) provisioned with inherited branding!`
        );
        setSubForm({ client_name: "", client_slug: "", industry: "Clinics / Hospitals" });
      } else {
        onErrorMessage(res.error?.message || "Enable Agency Reseller mode first before creating sub-tenants.");
      }
    } finally {
      setCreatingSub(false);
    }
  };

  const handleCreateApiKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyName.trim()) return;
    setCreatingKey(true);
    try {
      const res = await apiRequest("/api/v1/developer/keys", {
        method: "POST",
        body: JSON.stringify({
          name: keyName.trim(),
          scopes: ["agents:invoke", "leads:read", "finance:read", "compliance:audit"],
          rate_limit_per_minute: 120,
        }),
      });
      if (res.data?.api_key) {
        setNewlyCreatedSecret(res.data.api_key);
        onStatusMessage("New Metered Developer API Key generated! Copy it now — it is shown only once.");
        await loadPhase5Settings();
      } else {
        onErrorMessage(res.error?.message || "Failed to generate API key.");
      }
    } finally {
      setCreatingKey(false);
    }
  };

  const handleRevokeApiKey = async (keyId: string) => {
    const res = await apiRequest(`/api/v1/developer/keys/${keyId}`, {
      method: "DELETE",
    });
    if (!res.error) {
      onStatusMessage("Developer API Key revoked immediately.");
      await loadPhase5Settings();
    } else {
      onErrorMessage(res.error?.message || "Failed to revoke API key.");
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* 1. Multi-Tenant White-Label Branding & Agency Reseller Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Palette className="h-4 w-4 text-emerald-400" />
              White-Label Branding &amp; Custom Domain Engine
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Customize your workspace brand name, colors, custom domain, and Agency Reseller sub-tenant provisioning.
            </p>
          </div>
        </div>

        <form onSubmit={handleSaveWhitelabel} className="space-y-3 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Brand / Agency Name</label>
              <input
                type="text"
                required
                value={whitelabel.brand_name}
                onChange={(e) => setWhitelabel({ ...whitelabel, brand_name: e.target.value })}
                className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Custom Domain (CNAME)</label>
              <input
                type="text"
                placeholder="portal.youragency.com"
                value={whitelabel.custom_domain}
                onChange={(e) => setWhitelabel({ ...whitelabel, custom_domain: e.target.value })}
                className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-white font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Primary Hex Color</label>
              <input
                type="text"
                value={whitelabel.primary_color}
                onChange={(e) => setWhitelabel({ ...whitelabel, primary_color: e.target.value })}
                className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-white font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">Accent Hex Color</label>
              <input
                type="text"
                value={whitelabel.accent_color}
                onChange={(e) => setWhitelabel({ ...whitelabel, accent_color: e.target.value })}
                className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-white font-mono"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4 pt-1">
            <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={whitelabel.hide_powered_by}
                onChange={(e) => setWhitelabel({ ...whitelabel, hide_powered_by: e.target.checked })}
              />
              <span>Hide &ldquo;Powered by TaloxTech&rdquo; Badge</span>
            </label>
            <label className="flex items-center gap-2 text-emerald-300 cursor-pointer">
              <input
                type="checkbox"
                checked={whitelabel.agency_reseller_enabled}
                onChange={(e) =>
                  setWhitelabel({ ...whitelabel, agency_reseller_enabled: e.target.checked })
                }
              />
              <span>Enable Agency Reseller Mode (Sub-Tenants)</span>
            </label>
          </div>

          <button
            type="submit"
            disabled={savingWl}
            className="w-full py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition"
          >
            {savingWl ? "Saving White-Label Config..." : "Save White-Label Branding"}
          </button>
        </form>

        {whitelabel.agency_reseller_enabled && (
          <form
            onSubmit={handleCreateSubtenant}
            className="pt-3 border-t border-slate-800 space-y-2.5 text-xs"
          >
            <p className="font-semibold text-emerald-300 flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5" />
              <span>Provision Downstream Agency Client Sub-Tenant</span>
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <input
                type="text"
                required
                placeholder="Client Name"
                value={subForm.client_name}
                onChange={(e) => setSubForm({ ...subForm, client_name: e.target.value })}
                className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-1.5 text-white"
              />
              <input
                type="text"
                required
                placeholder="client-slug"
                value={subForm.client_slug}
                onChange={(e) => setSubForm({ ...subForm, client_slug: e.target.value })}
                className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-1.5 text-white font-mono"
              />
              <button
                type="submit"
                disabled={creatingSub}
                className="rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 font-bold text-white"
              >
                {creatingSub ? "Creating..." : "+ Add Sub-Tenant"}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* 2. Metered API-as-a-Service Developer Keys (X-Talox-API-Key) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
        <div className="border-b border-slate-800 pb-3">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-emerald-400" />
            Metered API-as-a-Service Developer Keys
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Generate scoped SHA-256 developer keys (<code className="text-emerald-300">X-Talox-API-Key</code>) to invoke the Central Orchestrator, CRM Leads, and Financial Forecasts externally.
          </p>
        </div>

        <form onSubmit={handleCreateApiKey} className="flex gap-2 text-xs">
          <input
            type="text"
            required
            value={keyName}
            onChange={(e) => setKeyName(e.target.value)}
            placeholder="Key Label (e.g. Zapier / Custom ERP Webhook)"
            className="flex-1 rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-white"
          />
          <button
            type="submit"
            disabled={creatingKey}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-4 py-2 font-bold text-white"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>{creatingKey ? "Generating..." : "Create API Key"}</span>
          </button>
        </form>

        {newlyCreatedSecret && (
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/40 p-3 space-y-1.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-emerald-300 flex items-center gap-1">
                <CheckCircle2 className="h-3.5 w-3.5" /> Copy Your Secret API Key (Shown Once)
              </span>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(newlyCreatedSecret);
                  onStatusMessage("API key copied to clipboard!");
                }}
                className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-[11px] font-bold text-white"
              >
                <Copy className="h-3 w-3" /> Copy
              </button>
            </div>
            <p className="font-mono text-[11px] text-white break-all bg-slate-950 p-2 rounded border border-slate-800">
              {newlyCreatedSecret}
            </p>
          </div>
        )}

        <div className="space-y-2 max-h-56 overflow-y-auto">
          {apiKeys.length === 0 ? (
            <p className="text-xs text-slate-500 italic py-2">
              No developer API keys created yet.
            </p>
          ) : (
            apiKeys.map((k) => (
              <div
                key={k.id}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white">{k.name}</span>
                    <span className="font-mono text-[11px] text-emerald-400">{k.key_prefix}...</span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                        k.is_active
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-red-500/20 text-red-300"
                      }`}
                    >
                      {k.is_active ? "Active" : "Revoked"}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-400 font-mono mt-0.5">
                    Calls: {k.total_calls} • Tokens Metered: {k.total_tokens_metered} • Scopes:{" "}
                    {(k.scopes || []).join(", ")}
                  </p>
                </div>
                {k.is_active && (
                  <button
                    type="button"
                    onClick={() => handleRevokeApiKey(k.id)}
                    className="inline-flex items-center gap-1 rounded border border-red-500/30 bg-red-500/10 px-2.5 py-1 text-[11px] text-red-300 hover:bg-red-500/20"
                  >
                    <Trash2 className="h-3 w-3" />
                    <span>Revoke</span>
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
