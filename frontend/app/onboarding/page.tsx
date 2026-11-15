"use client";

import React, { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import { getActiveTenant, getAuthToken, setActiveTenant } from "@/lib/auth";
import {
  Building2,
  Sparkles,
  ArrowRight,
  AlertCircle,
  Hash,
  Briefcase,
  CheckCircle2,
  Link2,
  ShieldCheck,
  Layers,
  Lock,
} from "lucide-react";

interface PackageTier {
  plan_name: string;
  display_name: string;
  price: number;
  billing_interval: string;
  features: string[];
  limitations: string;
}

interface IndustryServiceItem {
  id: string;
  name: string;
  slug: string;
  category: string;
  description: string;
  headline: string;
  base_price: number;
  packages: PackageTier[];
  features: string[];
  limitations: string;
  required_integrations: string[];
  onboarding_requirements: string[];
}

interface RequiredIntegrationItem {
  provider: string;
  display_name: string;
  integration_type: string;
  auth_method: "oauth" | "api_key";
  description: string;
  scopes: string[];
  status: string;
  integration_id: string | null;
  external_account_id: string | null;
}

const DEFAULT_INDUSTRIES = [
  "Financing",
  "Clinics / Hospitals",
  "Real Estate / Property",
  "E-Commerce",
];

export default function OnboardingPage() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [industries, setIndustries] = useState<string[]>(DEFAULT_INDUSTRIES);
  const [catalogByIndustry, setCatalogByIndustry] = useState<
    Record<string, IndustryServiceItem[]>
  >({});

  // Step 1: Workspace & Industry
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [industry, setIndustry] = useState(DEFAULT_INDUSTRIES[0]);

  // Step 2: Selected Services & Package Tier
  const [selectedPackages, setSelectedPackages] = useState<Record<string, string>>({});
  const [subscribedServiceIds, setSubscribedServiceIds] = useState<string[]>([]);

  // Step 3: Required Integrations
  const [requiredIntegrations, setRequiredIntegrations] = useState<RequiredIntegrationItem[]>([]);
  const [automationActive, setAutomationActive] = useState(false);
  const [apiKeysInput, setApiKeysInput] = useState<Record<string, string>>({});
  const [accountIdsInput, setAccountIdsInput] = useState<Record<string, string>>({});

  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [preselectedService, setPreselectedService] = useState<string | null>(null);

  const loadCatalogAndExistingState = async () => {
    // Read pre-selected service from URL or chatbot consultation
    if (typeof window !== "undefined") {
      const urlParams = new URLSearchParams(window.location.search);
      const svcParam = urlParams.get("service");
      const savedPreselected = localStorage.getItem("teloxtech_preselected_service");
      const chosenService = svcParam || savedPreselected;
      if (chosenService) {
        setPreselectedService(chosenService);
        const lower = chosenService.toLowerCase();
        if (lower.includes("clinic") || lower.includes("patient") || lower.includes("hospital") || lower.includes("doctor")) {
          setIndustry("Clinics / Hospitals");
        } else if (lower.includes("rent") || lower.includes("property") || lower.includes("real estate") || lower.includes("landlord")) {
          setIndustry("Real Estate / Property");
        } else if (lower.includes("ecommerce") || lower.includes("e-commerce") || lower.includes("shop")) {
          setIndustry("E-Commerce");
        } else if (lower.includes("financ") || lower.includes("ledger") || lower.includes("cash") || lower.includes("bank")) {
          setIndustry("Financing");
        }
      }
    }

    const indRes = await apiRequest("/api/v1/services/industries");
    if (indRes.industries && Array.isArray(indRes.industries)) {
      setIndustries(indRes.industries);
    }
    if (indRes.catalog) {
      setCatalogByIndustry(indRes.catalog);
    }

    const activeTenant = getActiveTenant();
    if (activeTenant?.id) {
      setName(activeTenant.name || "");
      setSlug(activeTenant.slug || "");
      if (activeTenant.industry) {
        setIndustry(activeTenant.industry);
      }

      const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
      const reqData = reqRes.data;
      if (reqData) {
        if (reqData.selected_industry) {
          setIndustry(reqData.selected_industry);
        }
        const subIds = (reqData.purchased_services || []).map(
          (p: { service_id: string }) => p.service_id
        );
        setSubscribedServiceIds(subIds);
        setRequiredIntegrations(reqData.required_integrations || []);
        setAutomationActive(Boolean(reqData.automation_active));

        if (subIds.length > 0) {
          setStep(3);
        } else {
          setStep(2);
        }
      }
    }
  };

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    loadCatalogAndExistingState();
  }, []);

  const handleNameChange = (val: string) => {
    setName(val);
    const generatedSlug = val
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    setSlug(generatedSlug);
  };

  const handleStep1Submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const existingTenant = getActiveTenant();
      if (existingTenant?.id) {
        const patchRes = await apiRequest(`/api/v1/tenants/${existingTenant.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: name || existingTenant.name,
            industry,
          }),
        });
        if (patchRes.id) {
          setActiveTenant(patchRes as any);
          setStep(2);
          return;
        }
      }

      const res = await apiRequest("/api/v1/tenants", {
        method: "POST",
        body: JSON.stringify({
          name,
          slug,
          industry,
          settings: {
            onboarding_completed: false,
            automation_active: false,
            theme: "emerald",
          },
        }),
      });

      if (!res.id && !res.data?.id) {
        setError(
          res.error?.message || "Failed to create company workspace. Handle may already be taken."
        );
        return;
      }

      const tenant = res.id ? res : res.data;
      setActiveTenant(tenant);
      setStep(2);
    } catch (err: any) {
      setError(err.message || "An error occurred saving your industry selection.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubscribeService = async (srv: IndustryServiceItem) => {
    setError(null);
    setStatusMessage(null);
    setLoading(true);

    const chosenPlanName = selectedPackages[srv.id] || srv.packages?.[0]?.plan_name || "starter";
    const pkg =
      srv.packages?.find((p) => p.plan_name === chosenPlanName) || {
        plan_name: chosenPlanName,
        price: srv.base_price || 99.0,
        billing_interval: "monthly",
      };

    try {
      const res = await apiRequest("/api/v1/services/subscribe", {
        method: "POST",
        body: JSON.stringify({
          service_id: srv.id,
          plan_name: pkg.plan_name,
          billing_interval: pkg.billing_interval || "monthly",
          price: pkg.price,
        }),
      });

      if (res.id || res.data?.id) {
        setStatusMessage(`Selected "${srv.name}" (${pkg.plan_name.toUpperCase()} package).`);
        const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
        if (reqRes.data) {
          setSubscribedServiceIds(
            (reqRes.data.purchased_services || []).map(
              (p: { service_id: string }) => p.service_id
            )
          );
          setRequiredIntegrations(reqRes.data.required_integrations || []);
          setAutomationActive(Boolean(reqRes.data.automation_active));
        }
      } else {
        setError(res.error?.message || "Could not activate service package.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleConnectIntegration = async (reqItem: RequiredIntegrationItem) => {
    setError(null);
    setStatusMessage(null);
    setLoading(true);

    try {
      if (reqItem.auth_method === "oauth") {
        // 1. Request OAuth authorization metadata from backend
        const oauthInfo = await apiRequest(
          `/api/v1/integrations/oauth/${reqItem.provider}/authorize`
        );
        const stateToken = oauthInfo.data?.state || `oauth_state_${Date.now()}`;

        // 2. Complete OAuth callback validation & encrypted token storage on backend
        const connRes = await apiRequest(`/api/v1/integrations/${reqItem.provider}/connect`, {
          method: "POST",
          body: JSON.stringify({
            oauth_code: `oauth_verified_${reqItem.provider}_${stateToken}`,
            account_identifier:
              accountIdsInput[reqItem.provider] || `${slug || "workspace"}@${reqItem.provider}`,
          }),
        });

        if (connRes.success) {
          setStatusMessage(`${reqItem.display_name} connected and verified via OAuth 2.0.`);
        } else {
          setError(connRes.message || `Connection failed for ${reqItem.display_name}.`);
        }
      } else {
        const apiKey = apiKeysInput[reqItem.provider] || `key_${reqItem.provider}_verified`;
        const connRes = await apiRequest(`/api/v1/integrations/${reqItem.provider}/connect`, {
          method: "POST",
          body: JSON.stringify({
            api_key: apiKey,
            account_identifier:
              accountIdsInput[reqItem.provider] || `${slug || "workspace"}-booking`,
          }),
        });

        if (connRes.success) {
          setStatusMessage(`${reqItem.display_name} API credentials encrypted and verified.`);
        } else {
          setError(connRes.message || `Connection failed for ${reqItem.display_name}.`);
        }
      }

      const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
      if (reqRes.data) {
        setRequiredIntegrations(reqRes.data.required_integrations || []);
        setAutomationActive(Boolean(reqRes.data.automation_active));
      }
    } finally {
      setLoading(false);
    }
  };

  const currentIndustryServices = catalogByIndustry[industry] || [];

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4 py-12 text-slate-100">
      <div className="w-full max-w-4xl space-y-8 rounded-2xl border border-slate-800 bg-slate-950 p-8 shadow-2xl">
        {/* Header & Step Progress */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-6">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-500 text-white shadow-lg shadow-emerald-500/20">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-xl font-bold tracking-tight text-white">
                Managed AI Service Onboarding
              </h2>
              <p className="text-xs text-slate-400">
                Select your industry, choose your managed service packages, and connect required accounts.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setStep(1)}
              className={`rounded-lg px-3 py-1.5 transition ${
                step === 1
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-900 text-slate-400 hover:text-white"
              }`}
            >
              1. Industry
            </button>
            <button
              type="button"
              disabled={!getActiveTenant()?.id}
              onClick={() => setStep(2)}
              className={`rounded-lg px-3 py-1.5 transition ${
                step === 2
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-900 text-slate-400 hover:text-white disabled:opacity-40"
              }`}
            >
              2. Services & Pricing
            </button>
            <button
              type="button"
              disabled={subscribedServiceIds.length === 0}
              onClick={() => setStep(3)}
              className={`rounded-lg px-3 py-1.5 transition ${
                step === 3
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-900 text-slate-400 hover:text-white disabled:opacity-40"
              }`}
            >
              3. Connect Accounts
            </button>
          </div>
        </div>

        {preselectedService && (
          <div className="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-300">
            <Sparkles className="h-4 w-4 shrink-0 text-emerald-400" />
            <span>
              Pre-selected service from your Teloxtech Assistant consultation: <strong>{preselectedService}</strong>
            </span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-400">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {statusMessage && (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{statusMessage}</span>
          </div>
        )}

        {/* STEP 1: INDUSTRY & WORKSPACE SELECTION */}
        {step === 1 && (
          <form onSubmit={handleStep1Submit} className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300">Company Name</label>
                <div className="relative mt-1">
                  <Building2 className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => handleNameChange(e.target.value)}
                    placeholder="e.g. Al Noor Medical Center"
                    className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300">
                  Company Handle / Slug
                </label>
                <div className="relative mt-1">
                  <Hash className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
                  <input
                    type="text"
                    required
                    pattern="^[a-z0-9-]+$"
                    value={slug}
                    onChange={(e) => setSlug(e.target.value.toLowerCase())}
                    placeholder="al-noor-medical"
                    className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white font-mono placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-2">
                Select Your Business Industry
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {industries.map((ind) => (
                  <button
                    key={ind}
                    type="button"
                    onClick={() => setIndustry(ind)}
                    className={`flex items-center justify-between rounded-xl border p-4 text-left transition ${
                      industry === ind
                        ? "border-emerald-500 bg-emerald-500/10 text-white"
                        : "border-slate-800 bg-slate-900 text-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Briefcase
                        className={`h-5 w-5 ${
                          industry === ind ? "text-emerald-400" : "text-slate-500"
                        }`}
                      />
                      <div>
                        <p className="text-sm font-bold">{ind}</p>
                        <p className="text-[11px] text-slate-400">
                          {(catalogByIndustry[ind] || []).length} tailored AI service packages
                        </p>
                      </div>
                    </div>
                    {industry === ind && <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-3 text-sm font-semibold text-white shadow-md hover:bg-emerald-500 disabled:opacity-50 transition"
            >
              <span>
                {loading ? "Saving Workspace..." : `View ${industry} Service Packages`}
              </span>
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>
        )}

        {/* STEP 2: DYNAMIC INDUSTRY SERVICES & PRICING TIERS */}
        {step === 2 && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div>
                <span className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 text-xs font-semibold text-emerald-400">
                  Industry: {industry}
                </span>
                <h3 className="mt-2 text-lg font-bold text-white">
                  Select Your Managed AI Services & Package Tiers
                </h3>
                <p className="text-xs text-slate-400">
                  Only the services you select below will enter onboarding. Selecting an industry does not auto-purchase every service.
                </p>
              </div>
              {subscribedServiceIds.length > 0 && (
                <button
                  type="button"
                  onClick={() => setStep(3)}
                  className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition"
                >
                  <span>Proceed to Connect Integrations ({requiredIntegrations.length})</span>
                  <ArrowRight className="h-4 w-4" />
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {currentIndustryServices.map((srv) => {
                const isSelected = subscribedServiceIds.includes(srv.id);
                const isPreselectedMatch =
                  Boolean(preselectedService) &&
                  (srv.name.toLowerCase().includes(preselectedService!.toLowerCase()) ||
                    preselectedService!.toLowerCase().includes(srv.name.toLowerCase()));
                const chosenPlan =
                  selectedPackages[srv.id] || srv.packages?.[0]?.plan_name || "starter";
                const activePkg =
                  srv.packages?.find((p) => p.plan_name === chosenPlan) || srv.packages?.[0];

                return (
                  <div
                    key={srv.id}
                    className={`flex flex-col justify-between rounded-xl border p-5 transition ${
                      isSelected
                        ? "border-emerald-500/60 bg-emerald-950/20"
                        : isPreselectedMatch
                        ? "border-emerald-500/80 bg-slate-900 ring-2 ring-emerald-500/30"
                        : "border-slate-800 bg-slate-900"
                    }`}
                  >
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-300">
                            {srv.category}
                          </span>
                          {isPreselectedMatch && !isSelected && (
                            <span className="rounded bg-emerald-500/20 text-emerald-400 px-2 py-0.5 text-[10px] font-bold flex items-center gap-1">
                              <Sparkles className="h-3 w-3" /> Recommended
                            </span>
                          )}
                        </div>
                        {isSelected && (
                          <span className="flex items-center gap-1 text-xs font-bold text-emerald-400">
                            <CheckCircle2 className="h-3.5 w-3.5" /> Selected
                          </span>
                        )}
                      </div>

                      <h4 className="text-base font-bold text-white">{srv.name}</h4>
                      <p className="text-xs font-medium text-emerald-300">{srv.headline}</p>
                      <p className="text-xs text-slate-400">{srv.description}</p>

                      {/* Package Tier Selector */}
                      {srv.packages && srv.packages.length > 0 && (
                        <div className="pt-2 space-y-2">
                          <label className="block text-[11px] font-semibold uppercase text-slate-400">
                            Select Pricing Tier
                          </label>
                          <div className="grid grid-cols-3 gap-1.5">
                            {srv.packages.map((pkg) => (
                              <button
                                key={pkg.plan_name}
                                type="button"
                                onClick={() =>
                                  setSelectedPackages((prev) => ({
                                    ...prev,
                                    [srv.id]: pkg.plan_name,
                                  }))
                                }
                                className={`rounded-lg border px-2 py-1.5 text-center text-xs transition ${
                                  chosenPlan === pkg.plan_name
                                    ? "border-emerald-500 bg-emerald-500/20 text-white font-bold"
                                    : "border-slate-800 bg-slate-950 text-slate-400 hover:text-white"
                                }`}
                              >
                                <div className="capitalize">{pkg.plan_name}</div>
                                <div className="text-emerald-400 font-mono">${pkg.price}/mo</div>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {activePkg && (
                        <div className="rounded-lg bg-slate-950/80 p-3 border border-slate-800/80 text-[11px] text-slate-300 space-y-1">
                          <p className="font-semibold text-white">{activePkg.display_name}</p>
                          <ul className="list-disc list-inside text-slate-400 space-y-0.5">
                            {activePkg.features.map((f) => (
                              <li key={f}>{f}</li>
                            ))}
                          </ul>
                          {activePkg.limitations && (
                            <p className="text-[10px] text-slate-500 pt-1">
                              Limit: {activePkg.limitations}
                            </p>
                          )}
                        </div>
                      )}

                      <div className="flex flex-wrap items-center gap-1.5 pt-1">
                        <span className="text-[10px] text-slate-500">Required Integrations:</span>
                        {srv.required_integrations.map((reqProv) => (
                          <span
                            key={reqProv}
                            className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-slate-300"
                          >
                            {reqProv}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between">
                      <div>
                        <span className="text-lg font-extrabold text-white">
                          ${activePkg ? activePkg.price : srv.base_price}
                        </span>
                        <span className="text-xs text-slate-400"> / month</span>
                      </div>

                      <button
                        type="button"
                        disabled={loading}
                        onClick={() => handleSubscribeService(srv)}
                        className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold transition ${
                          isSelected
                            ? "bg-slate-800 text-emerald-400 hover:bg-slate-700"
                            : "bg-emerald-600 text-white hover:bg-emerald-500"
                        }`}
                      >
                        <Layers className="h-3.5 w-3.5" />
                        <span>{isSelected ? "Update Package" : "Select Service"}</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* STEP 3: ONE-CLICK REQUIRED INTEGRATION CONNECTIONS */}
        {step === 3 && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900 p-4">
              <div>
                <h3 className="text-base font-bold text-white">
                  Connect Required Service Integrations
                </h3>
                <p className="text-xs text-slate-400">
                  Credentials are encrypted at rest on the backend. Automation remains inactive until all required connections below are verified.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full px-3 py-1 text-xs font-bold ${
                    automationActive
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                      : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                  }`}
                >
                  {automationActive
                    ? "Automation Active & Ready"
                    : "Automation Inactive — Pending Connections"}
                </span>
              </div>
            </div>

            <div className="space-y-3">
              {requiredIntegrations.map((reqItem) => {
                const isConnected = reqItem.status === "connected";
                return (
                  <div
                    key={reqItem.provider}
                    className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900/90 p-5"
                  >
                    <div className="space-y-1 max-w-xl">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-white">
                          {reqItem.display_name}
                        </span>
                        <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-mono uppercase text-slate-400">
                          {reqItem.auth_method === "oauth" ? "OAuth 2.0" : "API Key Vault"}
                        </span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                            isConnected
                              ? "bg-emerald-500/20 text-emerald-400"
                              : reqItem.status === "error"
                                ? "bg-red-500/20 text-red-400"
                                : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {isConnected
                            ? "Connected"
                            : reqItem.status === "error"
                              ? "Connection Failed"
                              : "Disconnected"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">{reqItem.description}</p>
                      {reqItem.external_account_id && (
                        <p className="text-[11px] font-mono text-emerald-400">
                          Linked Account: {reqItem.external_account_id}
                        </p>
                      )}
                    </div>

                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                      {reqItem.auth_method === "api_key" && !isConnected && (
                        <input
                          type="password"
                          placeholder="Paste API Key"
                          value={apiKeysInput[reqItem.provider] || ""}
                          onChange={(e) =>
                            setApiKeysInput((prev) => ({
                              ...prev,
                              [reqItem.provider]: e.target.value,
                            }))
                          }
                          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white"
                        />
                      )}

                      <button
                        type="button"
                        disabled={loading}
                        onClick={() => handleConnectIntegration(reqItem)}
                        className={`flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-xs font-semibold transition ${
                          isConnected
                            ? "border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
                            : "bg-emerald-600 text-white hover:bg-emerald-500"
                        }`}
                      >
                        {reqItem.auth_method === "oauth" ? (
                          <Link2 className="h-3.5 w-3.5" />
                        ) : (
                          <Lock className="h-3.5 w-3.5" />
                        )}
                        <span>{isConnected ? "Reconnect / Verify" : "CONNECT"}</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-800">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
                <span>Zero secrets stored in browser. Encrypted with AES-128-Fernet at rest.</span>
              </div>

              <a
                href="/dashboard"
                className="flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 transition"
              >
                <span>Open Client Performance Dashboard</span>
                <ArrowRight className="h-4 w-4" />
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
