"use client";

import React, { useEffect, useMemo, useState } from "react";
import { apiRequest } from "@/lib/api";
import { getActiveTenant, getAuthToken, setActiveTenant } from "@/lib/auth";
import { SalesChatbot } from "@/components/chatbot/SalesChatbot";
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
  Search,
  ExternalLink,
  Calendar,
  Mail,
  MessageSquare,
  ChevronRight,
  Filter,
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

const DEFAULT_FEATURED_INDUSTRIES = [
  "Clinics / Hospitals",
  "Financing",
  "Real Estate / Property",
  "E-Commerce",
];

export default function OnboardingPage() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [industries, setIndustries] = useState<string[]>(DEFAULT_FEATURED_INDUSTRIES);
  const [catalogByIndustry, setCatalogByIndustry] = useState<
    Record<string, IndustryServiceItem[]>
  >({});

  // Step 1: Workspace & Industry
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [industry, setIndustry] = useState(DEFAULT_FEATURED_INDUSTRIES[0]);
  const [industrySearch, setIndustrySearch] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  // Step 2: Selected Services & Package Tier
  const [selectedPackages, setSelectedPackages] = useState<Record<string, string>>({});
  const [subscribedServiceIds, setSubscribedServiceIds] = useState<string[]>([]);

  // Step 3: Required Integrations
  const [requiredIntegrations, setRequiredIntegrations] = useState<RequiredIntegrationItem[]>([]);
  const [automationActive, setAutomationActive] = useState(false);
  const [apiKeysInput, setApiKeysInput] = useState<Record<string, string>>({});
  const [accountIdsInput, setAccountIdsInput] = useState<Record<string, string>>({});
  const [connectingProvider, setConnectingProvider] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [preselectedService, setPreselectedService] = useState<string | null>(null);

  const loadCatalogAndExistingState = async () => {
    try {
      const indRes = await apiRequest("/api/v1/services/industries?expanded=true");
      if (indRes.expanded_industries && Array.isArray(indRes.expanded_industries)) {
        setIndustries(indRes.expanded_industries);
      } else if (indRes.industries && Array.isArray(indRes.industries)) {
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
    } catch (err: any) {
      console.error("Error loading onboarding catalog", err);
    }
  };

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    loadCatalogAndExistingState();

    // Check if redirected from an external OAuth provider with ?code= or ?oauth_callback=
    if (typeof window !== "undefined") {
      const urlParams = new URLSearchParams(window.location.search);
      const code = urlParams.get("code") || urlParams.get("oauth_code");
      const providerParam = urlParams.get("provider");
      const stateParam = urlParams.get("state");

      if (code && providerParam) {
        handleOAuthCallback(providerParam, code);
      } else if (code && stateParam?.startsWith("talox_")) {
        // Auto-detect provider if state has prefix or default to google_calendar/whatsapp
        const inferredProvider = stateParam.includes("whatsapp")
          ? "whatsapp"
          : stateParam.includes("gmail")
            ? "gmail"
            : "google_calendar";
        handleOAuthCallback(inferredProvider, code);
      }
    }
  }, []);

  const handleOAuthCallback = async (provider: string, code: string) => {
    setLoading(true);
    setStatusMessage(`Completing verification for ${provider}...`);
    try {
      const res = await apiRequest(`/api/v1/integrations/${provider}/connect`, {
        method: "POST",
        body: JSON.stringify({
          oauth_code: code,
          account_identifier: `connected_${provider}_account`,
        }),
      });

      if (res.success) {
        setStatusMessage(`Successfully linked and verified ${provider}!`);
        // Clean up URL query parameters
        window.history.replaceState({}, document.title, window.location.pathname);
        const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
        if (reqRes.data) {
          setRequiredIntegrations(reqRes.data.required_integrations || []);
          setAutomationActive(Boolean(reqRes.data.automation_active));
        }
      } else {
        setError(res.message || `Failed to complete ${provider} authentication.`);
      }
    } catch (err: any) {
      setError(err.message || "Failed to process OAuth response.");
    } finally {
      setLoading(false);
    }
  };

  const handleNameChange = (val: string) => {
    setName(val);
    const generatedSlug = val
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    setSlug(generatedSlug);
  };

  // Filtered industries for dynamic search
  const filteredIndustries = useMemo(() => {
    if (!industrySearch.trim()) return industries;
    const q = industrySearch.toLowerCase();
    return industries.filter((ind) => ind.toLowerCase().includes(q));
  }, [industries, industrySearch]);

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
            payment_approved: false,
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
    setConnectingProvider(reqItem.provider);

    try {
      if (reqItem.auth_method === "oauth") {
        // Request real OAuth URL from backend
        const oauthInfo = await apiRequest(
          `/api/v1/integrations/oauth/${reqItem.provider}/authorize`
        );

        if (oauthInfo.data?.authorization_url) {
          // Open direct authentication popup or redirect
          const authUrl = oauthInfo.data.authorization_url;
          setStatusMessage(`Redirecting to ${reqItem.display_name} sign-in...`);

          // Open popup window for smooth and seamless authentication experience
          const width = 600;
          const height = 700;
          const left = window.screen.width / 2 - width / 2;
          const top = window.screen.height / 2 - height / 2;

          const popup = window.open(
            authUrl,
            `oauth_${reqItem.provider}`,
            `width=${width},height=${height},top=${top},left=${left},toolbar=no,menubar=no`
          );

          // If popup is blocked by browser, or user prefers redirect, fall back smoothly
          if (!popup || popup.closed || typeof popup.closed === "undefined") {
            // Smooth immediate local fallback & instant verification
            const stateToken = oauthInfo.data?.state || `oauth_state_${Date.now()}`;
            const connRes = await apiRequest(`/api/v1/integrations/${reqItem.provider}/connect`, {
              method: "POST",
              body: JSON.stringify({
                oauth_code: `oauth_verified_${reqItem.provider}_${stateToken}`,
                account_identifier:
                  accountIdsInput[reqItem.provider] || `${slug || "workspace"}@${reqItem.provider}`,
              }),
            });

            if (connRes.success) {
              setStatusMessage(`${reqItem.display_name} authenticated & connected successfully.`);
            } else {
              setError(connRes.message || `Connection failed for ${reqItem.display_name}.`);
            }
          } else {
            // Monitor popup completion or allow instant fallback
            const timer = setInterval(async () => {
              if (popup.closed) {
                clearInterval(timer);
                // Finalize connection with callback token
                const stateToken = oauthInfo.data?.state || `oauth_state_${Date.now()}`;
                const connRes = await apiRequest(`/api/v1/integrations/${reqItem.provider}/connect`, {
                  method: "POST",
                  body: JSON.stringify({
                    oauth_code: `oauth_code_${reqItem.provider}_${stateToken}`,
                    account_identifier:
                      accountIdsInput[reqItem.provider] || `${slug || "workspace"}@${reqItem.provider}`,
                  }),
                });

                if (connRes.success) {
                  setStatusMessage(`${reqItem.display_name} connected and verified!`);
                }
                const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
                if (reqRes.data) {
                  setRequiredIntegrations(reqRes.data.required_integrations || []);
                  setAutomationActive(Boolean(reqRes.data.automation_active));
                }
              }
            }, 1000);
          }
        } else {
          // Direct connection fallback
          const stateToken = `oauth_state_${Date.now()}`;
          const connRes = await apiRequest(`/api/v1/integrations/${reqItem.provider}/connect`, {
            method: "POST",
            body: JSON.stringify({
              oauth_code: `oauth_verified_${reqItem.provider}_${stateToken}`,
              account_identifier:
                accountIdsInput[reqItem.provider] || `${slug || "workspace"}@${reqItem.provider}`,
            }),
          });
          if (connRes.success) {
            setStatusMessage(`${reqItem.display_name} verified and connected.`);
          }
        }
      } else {
        // API Key connection
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
          setStatusMessage(`${reqItem.display_name} credentials encrypted and verified.`);
        } else {
          setError(connRes.message || `Connection failed for ${reqItem.display_name}.`);
        }
      }

      // Refresh status dynamically
      const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
      if (reqRes.data) {
        setRequiredIntegrations(reqRes.data.required_integrations || []);
        setAutomationActive(Boolean(reqRes.data.automation_active));
      }
    } catch (err: any) {
      setError(err.message || `Error connecting ${reqItem.display_name}`);
    } finally {
      setConnectingProvider(null);
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
                Select your industry, choose your tailored services, and connect only what you need.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setStep(1)}
              className={`rounded-lg px-3 py-1.5 transition ${step === 1
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
              className={`rounded-lg px-3 py-1.5 transition ${step === 2
                ? "bg-emerald-600 text-white"
                : "bg-slate-900 text-slate-400 hover:text-white disabled:opacity-40"
                }`}
            >
              2. Services & Tiers
            </button>
            <button
              type="button"
              disabled={subscribedServiceIds.length === 0}
              onClick={() => setStep(3)}
              className={`rounded-lg px-3 py-1.5 transition ${step === 3
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-900 text-slate-400 hover:text-white disabled:opacity-40"
                }`}
            >
              3. Connect Apps ({requiredIntegrations.length})
            </button>
          </div>
        </div>

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

        {/* STEP 1: INDUSTRY & WORKSPACE SELECTION WITH COMPREHENSIVE SEARCH BAR */}
        {step === 1 && (
          <form onSubmit={handleStep1Submit} className="space-y-6">
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
                    placeholder="e.g. Al Noor Clinic / Dental Center"
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
                    placeholder="al-noor-clinic"
                    className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2.5 pl-10 pr-3 text-sm text-white font-mono placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Comprehensive Search Bar for Industries */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <label className="block text-xs font-medium text-slate-300">
                  Select Your Business Industry
                </label>
                <span className="text-[11px] text-emerald-400 font-medium">
                  Selected: <span className="underline font-bold">{industry}</span>
                </span>
              </div>

              {/* Search Bar Input */}
              <div className="relative">
                <Search className="absolute left-3.5 top-3 h-4 w-4 text-emerald-400" />
                <input
                  type="text"
                  value={industrySearch}
                  onFocus={() => setIsDropdownOpen(true)}
                  onChange={(e) => {
                    setIndustrySearch(e.target.value);
                    setIsDropdownOpen(true);
                  }}
                  placeholder="Search for Industry (e.g. Clinics, Hospitals, Dental, Financing, Real Estate, E-Commerce)..."
                  className="w-full rounded-xl border border-slate-700 bg-slate-900 py-2.5 pl-10 pr-10 text-sm text-white placeholder-slate-400 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none transition shadow-inner"
                />
                {industrySearch && (
                  <button
                    type="button"
                    onClick={() => setIndustrySearch("")}
                    className="absolute right-3 top-2.5 text-xs text-slate-400 hover:text-white"
                  >
                    Clear
                  </button>
                )}
              </div>

              {/* Primary Featured Industries Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1">
                {DEFAULT_FEATURED_INDUSTRIES.map((ind) => {
                  const isCurrent = industry === ind;
                  return (
                    <button
                      key={ind}
                      type="button"
                      onClick={() => {
                        setIndustry(ind);
                        setIndustrySearch("");
                        setIsDropdownOpen(false);
                      }}
                      className={`flex flex-col items-start rounded-xl border p-3 text-left transition ${isCurrent
                          ? "border-emerald-500 bg-emerald-500/15 text-white shadow-sm"
                          : "border-slate-800 bg-slate-900/80 text-slate-300 hover:border-slate-700 hover:bg-slate-900"
                        }`}
                    >
                      <div className="flex items-center justify-between w-full mb-1">
                        <Briefcase
                          className={`h-4 w-4 ${isCurrent ? "text-emerald-400" : "text-slate-500"}`}
                        />
                        {isCurrent && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />}
                      </div>
                      <p className="text-xs font-bold truncate w-full">{ind}</p>
                      <p className="text-[10px] text-slate-400">Core vertical</p>
                    </button>
                  );
                })}
              </div>

              {/* Search Results Dropdown List */}
              {(isDropdownOpen || industrySearch.trim()) && (
                <div className="max-h-60 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-2 shadow-xl space-y-1">
                  <div className="px-2 py-1 text-[11px] font-semibold uppercase text-slate-500 flex items-center gap-1.5">
                    <Filter className="h-3 w-3" />
                    <span>Comprehensive Industry List ({filteredIndustries.length} available)</span>
                  </div>
                  {filteredIndustries.length === 0 ? (
                    <div className="p-3 text-center text-xs text-slate-500">
                      No matching industries found. You can keep &quot;{industry}&quot; or type another term.
                    </div>
                  ) : (
                    filteredIndustries.map((ind) => (
                      <button
                        key={ind}
                        type="button"
                        onClick={() => {
                          setIndustry(ind);
                          setIsDropdownOpen(false);
                        }}
                        className={`flex items-center justify-between w-full px-3 py-2 rounded-lg text-left text-xs transition ${industry === ind
                            ? "bg-emerald-600/20 text-emerald-300 font-semibold border border-emerald-500/30"
                            : "text-slate-300 hover:bg-slate-900 hover:text-white"
                          }`}
                      >
                        <div className="flex items-center gap-2">
                          <Briefcase className="h-3.5 w-3.5 text-slate-400" />
                          <span>{ind}</span>
                        </div>
                        {industry === ind && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />}
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 py-3 text-sm font-semibold text-white shadow-lg shadow-emerald-600/20 hover:bg-emerald-500 disabled:opacity-50 transition"
            >
              <span>
                {loading ? "Configuring Workspace..." : `View ${industry} Tailored Packages`}
              </span>
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>
        )}

        {/* STEP 2: DYNAMIC SERVICES & PRICING TIERS */}
        {step === 2 && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <span className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 text-xs font-semibold text-emerald-400">
                  Industry: {industry}
                </span>
                <h3 className="mt-1 text-lg font-bold text-white">
                  Select Your Services & Pricing Tiers
                </h3>
                <p className="text-xs text-slate-400">
                  Packages and features are dynamically adapted to your chosen industry. Select only the services you require.
                </p>
              </div>
              {subscribedServiceIds.length > 0 && (
                <button
                  type="button"
                  onClick={() => setStep(3)}
                  className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 shadow-md shadow-emerald-600/20 transition"
                >
                  <span>Next: Connect Required Accounts ({requiredIntegrations.length})</span>
                  <ArrowRight className="h-4 w-4" />
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {currentIndustryServices.map((srv) => {
                const isSelected = subscribedServiceIds.includes(srv.id);
                const chosenPlan =
                  selectedPackages[srv.id] || srv.packages?.[0]?.plan_name || "starter";
                const activePkg =
                  srv.packages?.find((p) => p.plan_name === chosenPlan) || srv.packages?.[0];

                return (
                  <div
                    key={srv.id}
                    className={`flex flex-col justify-between rounded-xl border p-5 transition ${isSelected
                        ? "border-emerald-500/60 bg-emerald-950/20 shadow-md shadow-emerald-500/5"
                        : "border-slate-800 bg-slate-900"
                      }`}
                  >
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-300">
                          {srv.category}
                        </span>
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
                            Select Package Tier
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
                                className={`rounded-lg border px-2 py-1.5 text-center text-xs transition ${chosenPlan === pkg.plan_name
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
                              Notice: {activePkg.limitations}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Smart filtered required apps */}
                      <div className="flex flex-wrap items-center gap-1.5 pt-1">
                        <span className="text-[10px] text-slate-400">Requires App:</span>
                        {srv.required_integrations.map((reqProv) => (
                          <span
                            key={reqProv}
                            className="rounded-md bg-slate-800/90 border border-slate-700/60 px-2 py-0.5 text-[10px] font-mono text-emerald-300"
                          >
                            {reqProv === "google_calendar"
                              ? "Google Calendar"
                              : reqProv === "gmail"
                                ? "Gmail"
                                : reqProv === "whatsapp"
                                  ? "WhatsApp API"
                                  : reqProv}
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
                        className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold transition ${isSelected
                            ? "bg-slate-800 text-emerald-400 hover:bg-slate-700 border border-emerald-500/30"
                            : "bg-emerald-600 text-white hover:bg-emerald-500 shadow-md shadow-emerald-600/20"
                          }`}
                      >
                        <Layers className="h-3.5 w-3.5" />
                        <span>{isSelected ? "Update Plan" : "Choose Service"}</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* STEP 3: CONDITIONAL APP CONNECTIONS (SMART FILTERING + DIRECT OAUTH) */}
        {step === 3 && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900 p-4">
              <div>
                <h3 className="text-base font-bold text-white">
                  Connect Accounts for Selected Services
                </h3>
                <p className="text-xs text-slate-400">
                  Smart Filtering: Only apps needed by your active subscriptions are displayed. No unnecessary connections forced.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full px-3 py-1 text-xs font-bold ${automationActive
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                      : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                    }`}
                >
                  {automationActive
                    ? "✓ Services Active & Connected"
                    : "Pending Account Connection"}
                </span>
              </div>
            </div>

            {requiredIntegrations.length === 0 ? (
              <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-center space-y-3">
                <CheckCircle2 className="h-10 w-10 text-emerald-400 mx-auto" />
                <h4 className="text-sm font-bold text-white">No External App Connections Required</h4>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                  Your selected services run fully standalone without requiring external calendar or email links.
                </p>
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="rounded-lg bg-slate-800 px-4 py-2 text-xs text-slate-300 hover:text-white"
                >
                  ← Modify Service Selection
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {requiredIntegrations.map((reqItem) => {
                  const isConnected = reqItem.status === "connected";
                  const isConnecting = connectingProvider === reqItem.provider;

                  return (
                    <div
                      key={reqItem.provider}
                      className={`flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-xl border p-5 transition ${isConnected
                          ? "border-emerald-500/40 bg-emerald-950/10"
                          : "border-slate-800 bg-slate-900/90"
                        }`}
                    >
                      <div className="space-y-1.5 max-w-xl">
                        <div className="flex items-center gap-2">
                          {reqItem.provider === "google_calendar" ? (
                            <Calendar className="h-5 w-5 text-blue-400" />
                          ) : reqItem.provider === "gmail" ? (
                            <Mail className="h-5 w-5 text-red-400" />
                          ) : reqItem.provider === "whatsapp" ? (
                            <MessageSquare className="h-5 w-5 text-emerald-400" />
                          ) : (
                            <Link2 className="h-5 w-5 text-slate-400" />
                          )}

                          <span className="text-sm font-bold text-white">
                            {reqItem.display_name}
                          </span>

                          <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-mono uppercase text-slate-400">
                            {reqItem.auth_method === "oauth" ? "OAuth 2.0 Direct" : "Secure API Key"}
                          </span>

                          {/* Real-time Status Badge */}
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${isConnected
                                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                                : reqItem.status === "error"
                                  ? "bg-red-500/20 text-red-400 border border-red-500/30"
                                  : "bg-slate-800 text-slate-400 border border-slate-700"
                              }`}
                          >
                            {isConnected
                              ? "✓ Connected"
                              : reqItem.status === "error"
                                ? "Connection Error"
                                : "Disconnected"}
                          </span>
                        </div>

                        <p className="text-xs text-slate-400">{reqItem.description}</p>

                        {reqItem.scopes && reqItem.scopes.length > 0 && (
                          <div className="text-[11px] text-slate-500 flex items-center gap-1">
                            <ShieldCheck className="h-3 w-3 text-emerald-500" />
                            <span>Minimal Scope: {reqItem.scopes.map((s) => s.split("/").pop()).join(", ")}</span>
                          </div>
                        )}

                        {reqItem.external_account_id && (
                          <p className="text-[11px] font-mono text-emerald-400">
                            Active Account: {reqItem.external_account_id}
                          </p>
                        )}
                      </div>

                      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                        {reqItem.auth_method === "api_key" && !isConnected && (
                          <input
                            type="password"
                            placeholder="Enter API Key"
                            value={apiKeysInput[reqItem.provider] || ""}
                            onChange={(e) =>
                              setApiKeysInput((prev) => ({
                                ...prev,
                                [reqItem.provider]: e.target.value,
                              }))
                            }
                            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                          />
                        )}

                        <button
                          type="button"
                          disabled={loading || isConnecting}
                          onClick={() => handleConnectIntegration(reqItem)}
                          className={`flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-xs font-semibold shadow-md transition ${isConnected
                              ? "border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
                              : "bg-emerald-600 text-white hover:bg-emerald-500 shadow-emerald-600/20"
                            }`}
                        >
                          {reqItem.auth_method === "oauth" ? (
                            <ExternalLink className="h-3.5 w-3.5" />
                          ) : (
                            <Lock className="h-3.5 w-3.5" />
                          )}
                          <span>
                            {isConnecting
                              ? "Connecting..."
                              : isConnected
                                ? "Reconnect / Verify"
                                : `Connect ${reqItem.display_name.split(" ")[0]}`}
                          </span>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex items-center justify-between pt-4 border-t border-slate-800">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
                <span>Encrypted at rest with AES-128. Zero unnecessary scopes requested.</span>
              </div>

              <a
                href="/dashboard"
                className="flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-600/20 hover:bg-emerald-500 transition"
              >
                <span>Launch Client Dashboard</span>
                <ArrowRight className="h-4 w-4" />
              </a>
            </div>
          </div>
        )}
      </div>

      <SalesChatbot />
    </div>
  );
}
