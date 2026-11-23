"use client";

import React, { useCallback, useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import {
  getActiveTenant,
  getAuthToken,
  setActiveTenant,
  SUPPORT_WHATSAPP_NUMBER,
  SUPPORT_WHATSAPP_LINK,
} from "@/lib/auth";
import { normalizeServiceSlug, getCanonicalServiceMeta } from "@/lib/services";
import { SupportRequestModal } from "@/components/shared/SupportRequestModal";
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
  RefreshCw,
  ExternalLink,
  Trash2,
  LifeBuoy,
  MessageSquare,
  PhoneCall,
  PhoneForwarded,
  CalendarCheck2,
  Copy,
  Check,
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
  const [subscribedMap, setSubscribedMap] = useState<
    Record<string, { subscriptionId: string; planName: string }>
  >({});
  const [purchasedSlugs, setPurchasedSlugs] = useState<string[]>([]);
  const subscribedServiceIds = Object.keys(subscribedMap);
  const hasOfficeReceptionist = purchasedSlugs.includes("office-receptionist");

  // Step 3: Dynamic Office Receptionist (AI Voice Agent) Setup
  const [recepBusinessName, setRecepBusinessName] = useState("");
  const [recepOperatingHours, setRecepOperatingHours] = useState("Mon-Fri 9:00 AM - 6:00 PM");
  const [recepFallbackPhone, setRecepFallbackPhone] = useState("");
  const [recepGreeting, setRecepGreeting] = useState(
    "Hello! Thank you for calling. I'm your AI receptionist — how can I assist you today?"
  );
  const [recepFaqs, setRecepFaqs] = useState("");
  const [recepCalcomUrl, setRecepCalcomUrl] = useState("");
  const [recepCalcomEventTypeId, setRecepCalcomEventTypeId] = useState("");
  const [recepCalcomApiKey, setRecepCalcomApiKey] = useState("");
  const [recepSaving, setRecepSaving] = useState(false);
  const [recepConfig, setRecepConfig] = useState<any>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  // Step 3: Required Integrations
  const [requiredIntegrations, setRequiredIntegrations] = useState<RequiredIntegrationItem[]>([]);
  const [automationActive, setAutomationActive] = useState(false);
  const [apiKeysInput, setApiKeysInput] = useState<Record<string, string>>({});
  const [accountIdsInput, setAccountIdsInput] = useState<Record<string, string>>({});
  const [webhookUrlsInput, setWebhookUrlsInput] = useState<Record<string, string>>({});
  const [verifyingProvider, setVerifyingProvider] = useState<string | null>(null);
  const [oauthUnavailableByProvider, setOauthUnavailableByProvider] = useState<
    Record<string, string>
  >({});
  const [showDirectWhatsApp, setShowDirectWhatsApp] = useState(false);
  const [directWaPhoneId, setDirectWaPhoneId] = useState("");
  const [directWaWabaId, setDirectWaWabaId] = useState("");
  const [directWaToken, setDirectWaToken] = useState("");

  // Support Modal State
  const [supportModalOpen, setSupportModalOpen] = useState(false);
  const [supportDefaults, setSupportDefaults] = useState<{
    subject: string;
    category: string;
    message: string;
    provider?: string;
  }>({
    subject: "",
    category: "integration_setup",
    message: "",
  });

  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [preselectedService, setPreselectedService] = useState<string | null>(null);

  const syncOnboardingRequirements = useCallback((reqData: any) => {
    const nextMap: Record<string, { subscriptionId: string; planName: string }> = {};
    const slugs: string[] = [];
    const purchased = Array.isArray(reqData?.purchased_services) ? reqData.purchased_services : [];
    for (const p of purchased) {
      if (p?.service_id && p?.subscription_id) {
        nextMap[p.service_id] = {
          subscriptionId: p.subscription_id,
          planName: (p.plan_name || "starter").toLowerCase(),
        };
      }
      if (p?.service_slug) {
        slugs.push(String(p.service_slug).toLowerCase());
      }
    }
    setSubscribedMap(nextMap);
    setPurchasedSlugs(slugs);
    setSelectedPackages((prev) => {
      const merged = { ...prev };
      for (const [serviceId, sub] of Object.entries(nextMap)) {
        if (!merged[serviceId]) {
          merged[serviceId] = sub.planName;
        }
      }
      return merged;
    });
    setRequiredIntegrations(reqData?.required_integrations || []);
    setAutomationActive(Boolean(reqData?.automation_active));
    return Object.keys(nextMap);
  }, []);

  const loadCatalogAndExistingState = useCallback(async () => {
    // Read pre-selected service from URL or chatbot consultation
    if (typeof window !== "undefined") {
      const urlParams = new URLSearchParams(window.location.search);
      const svcParam = urlParams.get("service");
      const savedPreselected = localStorage.getItem("teloxtech_preselected_service");
      const chosenService = svcParam || savedPreselected;
      if (chosenService) {
        const lower = chosenService.toLowerCase();
        const normalizedSlug = normalizeServiceSlug(chosenService) || chosenService;
        setPreselectedService(normalizedSlug);

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
        const subIds = syncOnboardingRequirements(reqData);

        const purchased = Array.isArray(reqData.purchased_services) ? reqData.purchased_services : [];
        const hasRecep = purchased.some(
          (p: any) => String(p?.service_slug || "").toLowerCase() === "office-receptionist"
        );
        if (hasRecep) {
          const recepRes = await apiRequest("/api/v1/receptionist/config");
          if (recepRes.success && recepRes.data) {
            const rc = recepRes.data;
            setRecepConfig(rc);
            setRecepBusinessName(rc.business_name || activeTenant.name || "");
            setRecepOperatingHours(rc.operating_hours || "Mon-Fri 9:00 AM - 6:00 PM");
            setRecepFallbackPhone(rc.fallback_phone_number || "");
            setRecepGreeting(
              rc.greeting_message ||
                `Hello! Thank you for calling ${activeTenant.name || "our office"}. How can I help you today?`
            );
            setRecepFaqs(rc.faqs_knowledge_base || "");
            setRecepCalcomUrl(rc.calcom_booking_url || "");
            setRecepCalcomEventTypeId(rc.calcom_event_type_id || "");
          } else {
            setRecepBusinessName(activeTenant.name || "");
          }
        }

        if (subIds.length > 0) {
          setStep(3);
        } else {
          setStep(2);
        }
      }
    }
  }, [syncOnboardingRequirements]);

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }

    const checkOAuthCallback = async () => {
      if (typeof window === "undefined") return;
      const urlParams = new URLSearchParams(window.location.search);
      const oauthCode = urlParams.get("code");
      const oauthState = urlParams.get("state");
      const oauthError = urlParams.get("error");
      const errorDesc = urlParams.get("error_description");
      const connectedProvider = urlParams.get("connected");
      const statusParam = urlParams.get("status");

      if (oauthError) {
        sessionStorage.removeItem("talox_oauth_return_to");
        setError(`OAuth authorization was denied or failed: ${errorDesc || oauthError}`);
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (connectedProvider && statusParam === "success") {
        const storedReturnTo =
          sessionStorage.getItem("talox_oauth_return_to") || urlParams.get("return_to");
        sessionStorage.removeItem("talox_oauth_return_to");
        if (
          storedReturnTo &&
          storedReturnTo.startsWith("/") &&
          !storedReturnTo.startsWith("//") &&
          storedReturnTo !== "/onboarding"
        ) {
          window.location.href = `${storedReturnTo}?connected=${encodeURIComponent(
            connectedProvider
          )}&status=success`;
          return;
        }
        setStatusMessage(
          `${connectedProvider.replace("_", " ").toUpperCase()} successfully connected and verified via OAuth 2.0!`
        );
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (oauthCode && oauthState) {
        setLoading(true);
        setStatusMessage("Completing OAuth 2.0 token exchange and security verification...");
        try {
          const cbRes = await apiRequest("/api/v1/integrations/oauth/callback", {
            method: "POST",
            body: JSON.stringify({
              code: oauthCode,
              state: oauthState,
            }),
          });
          if (cbRes.success && cbRes.data) {
            const storedReturnTo =
              sessionStorage.getItem("talox_oauth_return_to") || urlParams.get("return_to");
            sessionStorage.removeItem("talox_oauth_return_to");
            if (
              storedReturnTo &&
              storedReturnTo.startsWith("/") &&
              !storedReturnTo.startsWith("//") &&
              storedReturnTo !== "/onboarding"
            ) {
              const providerParam = cbRes.data.provider || "oauth";
              window.location.href = `${storedReturnTo}?connected=${encodeURIComponent(
                providerParam
              )}&status=success`;
              return;
            }
            setStatusMessage(
              `${cbRes.data.display_name || "Integration"} securely connected and verified via OAuth 2.0!`
            );
          } else {
            sessionStorage.removeItem("talox_oauth_return_to");
            setError(
              cbRes.error?.message ||
                cbRes.message ||
                "Failed to complete OAuth 2.0 token exchange."
            );
          }
        } catch (err: any) {
          sessionStorage.removeItem("talox_oauth_return_to");
          setError(err.message || "OAuth 2.0 callback processing error.");
        } finally {
          setLoading(false);
          window.history.replaceState({}, document.title, window.location.pathname);
        }
      }

      await loadCatalogAndExistingState();
    };

    checkOAuthCallback();
  }, [loadCatalogAndExistingState]);

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
        const updatedTenant = patchRes.id ? patchRes : patchRes.data;
        if (!patchRes.error && updatedTenant?.id) {
          setActiveTenant(updatedTenant as any);
          setStep(2);
          return;
        }
        setError(patchRes.error?.message || "Failed to update company workspace settings.");
        return;
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

    const existingSub = subscribedMap[srv.id];
    const chosenPlanName = (
      selectedPackages[srv.id] ||
      srv.packages?.[0]?.plan_name ||
      "starter"
    ).toLowerCase();

    if (existingSub && existingSub.planName === chosenPlanName) {
      setStatusMessage(
        `"${srv.name}" (${chosenPlanName.toUpperCase()}) is already selected.`
      );
      return;
    }

    setLoading(true);
    const pkg =
      srv.packages?.find((p) => p.plan_name.toLowerCase() === chosenPlanName) || {
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
        setStatusMessage(
          existingSub
            ? `Updated "${srv.name}" to ${pkg.plan_name.toUpperCase()} tier.`
            : `Selected "${srv.name}" (${pkg.plan_name.toUpperCase()} package).`
        );
        const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
        if (reqRes.data) {
          syncOnboardingRequirements(reqRes.data);
        }
      } else {
        setError(res.error?.message || "Could not activate service package.");
      }
    } catch (err: any) {
      setError(err.message || "An error occurred while subscribing to the service package.");
    } finally {
      setLoading(false);
    }
  };

  const handleDeselectService = async (srv: IndustryServiceItem) => {
    const existingSub = subscribedMap[srv.id];
    if (!existingSub?.subscriptionId) return;

    setError(null);
    setStatusMessage(null);
    setLoading(true);

    try {
      const res = await apiRequest(
        `/api/v1/services/subscriptions/${existingSub.subscriptionId}/cancel`,
        { method: "POST" }
      );
      if (!res.error && (res.id || res.data?.id || res.status === "canceled")) {
        setStatusMessage(`Removed "${srv.name}" from your selected services.`);
        const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
        if (reqRes.data) {
          syncOnboardingRequirements(reqRes.data);
        }
      } else {
        setError(res.error?.message || `Failed to remove "${srv.name}".`);
      }
    } catch (err: any) {
      setError(err.message || `An error occurred removing "${srv.name}".`);
    } finally {
      setLoading(false);
    }
  };

  const openSupportForProvider = (provider: string, displayName: string) => {
    setSupportDefaults({
      subject: `Assisted Setup Request: ${displayName}`,
      category: "integration_setup",
      message: `Please assist with configuring ${displayName} (${provider}) for my workspace "${name || slug || "Workspace"}".`,
      provider,
    });
    setSupportModalOpen(true);
  };

  const handleConnectIntegration = async (reqItem: RequiredIntegrationItem) => {
    setError(null);
    setStatusMessage(null);
    setLoading(true);

    try {
      if (reqItem.auth_method === "oauth") {
        // 1. Request real OAuth authorization URL from backend
        setStatusMessage(`Initiating secure OAuth 2.0 authorization for ${reqItem.display_name}...`);
        const oauthInfo = await apiRequest(
          `/api/v1/integrations/oauth/${reqItem.provider}/authorize?return_to=/onboarding`
        );

        if (!oauthInfo.success || !oauthInfo.data?.authorization_url) {
          setStatusMessage(null);
          if (oauthInfo.error?.code === "OAUTH_NOT_CONFIGURED") {
            setOauthUnavailableByProvider((prev) => ({
              ...prev,
              [reqItem.provider]: reqItem.display_name,
            }));
          } else {
            setError(
              oauthInfo.error?.message ||
                `Failed to generate authorization URL for ${reqItem.display_name}.`
            );
          }
          return;
        }

        // 2. Persist state for verification
        if (typeof window !== "undefined") {
          sessionStorage.removeItem("talox_oauth_return_to");
          sessionStorage.setItem(
            "teloxtech_pending_oauth",
            JSON.stringify({
              provider: reqItem.provider,
              state: oauthInfo.data.state,
              timestamp: Date.now(),
            })
          );
          // 3. Trigger full external OAuth 2.0 redirect flow to provider login/consent page
          window.location.href = oauthInfo.data.authorization_url;
        }
      } else {
        const apiKey = (apiKeysInput[reqItem.provider] || "").trim();
        const accountId = (accountIdsInput[reqItem.provider] || "").trim();
        const webhookUrl = (webhookUrlsInput[reqItem.provider] || "").trim();
        if (!apiKey) {
          setError(`Please enter a valid API Key for ${reqItem.display_name} before connecting.`);
          setLoading(false);
          return;
        }
        const connRes = await apiRequest(`/api/v1/integrations/${reqItem.provider}/connect`, {
          method: "POST",
          body: JSON.stringify({
            api_key: apiKey,
            account_identifier:
              accountId || `${slug || "workspace"}-${reqItem.provider}`,
            configuration: webhookUrl ? { webhook_url: webhookUrl } : undefined,
          }),
        });

        if (connRes.success && connRes.data?.status === "connected") {
          setApiKeysInput((prev) => ({ ...prev, [reqItem.provider]: "" }));
          setStatusMessage(`${reqItem.display_name} API credentials encrypted and verified.`);
        } else {
          setError(
            connRes.error?.message ||
              connRes.message ||
              `Connection failed for ${reqItem.display_name}.`
          );
        }

        const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
        if (reqRes.data) {
          syncOnboardingRequirements(reqRes.data);
        }
      }
    } catch (err: any) {
      setError(err.message || `Failed to initiate connection for ${reqItem.display_name}.`);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyConnection = async (reqItem: RequiredIntegrationItem) => {
    if (!reqItem.integration_id) return;
    setError(null);
    setStatusMessage(null);
    setVerifyingProvider(reqItem.provider);

    try {
      const res = await apiRequest(`/api/v1/integrations/${reqItem.integration_id}/test`, {
        method: "POST",
      });

      if (res.success && res.data?.status === "connected") {
        setStatusMessage(`${reqItem.display_name} live connection is active and verified.`);
      } else {
        setError(
          `${reqItem.display_name} live verification failed: ${
            res.data?.configuration?.last_test_result || "Token invalid or expired. Reconnection needed."
          }`
        );
      }

      const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
      if (reqRes.data) {
        syncOnboardingRequirements(reqRes.data);
      }
    } catch (err: any) {
      setError(err.message || `Failed to verify connection for ${reqItem.display_name}.`);
    } finally {
      setVerifyingProvider(null);
    }
  };

  const handleSaveReceptionistOnboarding = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setStatusMessage(null);
    const effectiveBizName = (recepBusinessName || name || "").trim();
    if (!effectiveBizName || !recepFallbackPhone.trim()) {
      setError(
        "Please enter your Business Name and Personal / Fallback Phone Number for live human transfers."
      );
      return;
    }

    setRecepSaving(true);
    try {
      const payload: Record<string, unknown> = {
        business_name: effectiveBizName,
        operating_hours: recepOperatingHours.trim() || "Mon-Fri 9:00 AM - 6:00 PM",
        fallback_phone_number: recepFallbackPhone.trim(),
        greeting_message:
          recepGreeting.trim() ||
          `Hello! Thank you for calling ${effectiveBizName}. How can I help you today?`,
        faqs_knowledge_base: recepFaqs.trim(),
        calcom_booking_url: recepCalcomUrl.trim() || null,
        calcom_event_type_id: recepCalcomEventTypeId.trim() || null,
        auto_provision: true,
      };
      if (recepCalcomApiKey.trim()) {
        payload.calcom_api_key = recepCalcomApiKey.trim();
      }

      const res = await apiRequest("/api/v1/receptionist/config", {
        method: "PUT",
        body: JSON.stringify(payload),
      });

      if (res.success && res.data) {
        setRecepConfig(res.data);
        setRecepBusinessName(res.data.business_name || effectiveBizName);
        setRecepCalcomApiKey("");
        setStatusMessage(
          `Office Receptionist provisioned! Your assigned Telnyx AI number is ${
            res.data.telnyx_phone_number || "ready"
          }. Follow the Call Forwarding guide below to go live.`
        );
      } else {
        setError(
          res.error?.message || res.message || "Failed to provision Office Receptionist AI Agent."
        );
      }
    } catch (err: any) {
      setError(err.message || "Error saving Office Receptionist onboarding details.");
    } finally {
      setRecepSaving(false);
    }
  };

  const handleCopyDialCode = async (key: string, val: string) => {
    try {
      await navigator.clipboard.writeText(val);
      setCopiedCode(key);
      setTimeout(() => setCopiedCode(null), 2000);
    } catch {
      setStatusMessage(`Copy value: ${val}`);
    }
  };

  const handleDirectWhatsAppConnect = async () => {
    setError(null);
    setStatusMessage(null);
    const phoneId = directWaPhoneId.trim();
    const token = directWaToken.trim();
    if (!phoneId || !token) {
      setError("Please enter your Meta WhatsApp Phone Number ID and Permanent Access Token.");
      return;
    }
    setLoading(true);
    try {
      const connRes = await apiRequest("/api/v1/integrations/whatsapp/connect", {
        method: "POST",
        body: JSON.stringify({
          api_key: token,
          account_identifier: phoneId,
          configuration: {
            phone_number_id: phoneId,
            ...(directWaWabaId.trim() ? { waba_id: directWaWabaId.trim() } : {}),
            connection_mode: "direct_cloud_api",
          },
        }),
      });
      if (connRes.success && connRes.data?.status === "connected") {
        setDirectWaToken("");
        setShowDirectWhatsApp(false);
        setStatusMessage("WhatsApp Business Cloud API credentials encrypted and connected!");
      } else {
        setError(
          connRes.error?.message ||
            connRes.message ||
            "Failed to connect WhatsApp Cloud API credentials."
        );
      }
      const reqRes = await apiRequest("/api/v1/integrations/onboarding-requirements");
      if (reqRes.data) {
        syncOnboardingRequirements(reqRes.data);
      }
    } catch (err: any) {
      setError(err.message || "Error connecting WhatsApp Cloud API.");
    } finally {
      setLoading(false);
    }
  };

  const currentIndustryServices = catalogByIndustry[industry] || [];

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4 py-8 sm:py-12 text-slate-100">
      <div className="w-full max-w-4xl space-y-8 rounded-2xl border border-slate-800 bg-slate-950 p-4 sm:p-8 shadow-2xl">
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
              Pre-selected service:{" "}
              <strong>{getCanonicalServiceMeta(preselectedService)?.name || preselectedService}</strong>
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
                    pattern="^(?:[a-z0-9]|-)+$"
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
                          {(catalogByIndustry[ind] || []).length > 0
                            ? `${(catalogByIndustry[ind] || []).length} tailored AI service packages`
                            : "Tailored AI service packages"}
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
                  <span>
                    Continue with {subscribedServiceIds.length} selected service
                    {subscribedServiceIds.length === 1 ? "" : "s"}
                  </span>
                  <ArrowRight className="h-4 w-4" />
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {currentIndustryServices.map((srv) => {
                const activeSub = subscribedMap[srv.id];
                const isSelected = Boolean(activeSub);
                const normalizedSrvSlug = normalizeServiceSlug(srv.slug);
                const isPreselectedMatch =
                  Boolean(preselectedService) &&
                  ((normalizedSrvSlug && normalizedSrvSlug === preselectedService) ||
                    srv.slug.toLowerCase() === preselectedService!.toLowerCase() ||
                    srv.slug.toLowerCase().includes(preselectedService!.toLowerCase()) ||
                    srv.name.toLowerCase().includes(preselectedService!.toLowerCase()));
                const chosenPlan = (
                  selectedPackages[srv.id] ||
                  activeSub?.planName ||
                  srv.packages?.[0]?.plan_name ||
                  "starter"
                ).toLowerCase();
                const activePkg =
                  srv.packages?.find((p) => p.plan_name.toLowerCase() === chosenPlan) ||
                  srv.packages?.[0];
                const tierChanged = Boolean(activeSub && chosenPlan !== activeSub.planName);

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
                        {srv.required_integrations.length > 0 ? (
                          srv.required_integrations.map((reqProv) => (
                            <span
                              key={reqProv}
                              className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-slate-300"
                            >
                              {reqProv}
                            </span>
                          ))
                        ) : (
                          <span className="rounded bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                            Guided Voice Setup (Retell AI + Telnyx + Cal.com)
                          </span>
                        )}
                      </div>

                      {srv.onboarding_requirements && srv.onboarding_requirements.length > 0 && (
                        <div className="rounded-lg bg-slate-950/60 border border-slate-800/70 p-2.5 space-y-1">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                            Onboarding Checklist
                          </p>
                          <ul className="space-y-1 text-[11px] text-slate-300">
                            {srv.onboarding_requirements.map((reqText) => (
                              <li key={reqText} className="flex items-start gap-1.5">
                                <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0 mt-0.5" />
                                <span>{reqText}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    <div className="mt-4 pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <span className="text-lg font-extrabold text-white">
                          ${activePkg ? activePkg.price : srv.base_price}
                        </span>
                        <span className="text-xs text-slate-400"> / month</span>
                      </div>

                      <div className="flex items-center gap-2">
                        {isSelected && (
                          <button
                            type="button"
                            disabled={loading}
                            onClick={() => handleDeselectService(srv)}
                            className="flex items-center gap-1 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-300 hover:bg-red-500/20 disabled:opacity-50 transition"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            <span>Remove</span>
                          </button>
                        )}

                        {isSelected && !tierChanged ? (
                          <span className="flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-3.5 py-2 text-xs font-semibold text-emerald-300">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            <span>Selected ({activeSub?.planName})</span>
                          </span>
                        ) : (
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
                            <span>{isSelected ? "Update Tier" : "Select Service"}</span>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* STEP 3: DYNAMIC SERVICE SETUP & REQUIRED INTEGRATION CONNECTIONS */}
        {step === 3 && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900 p-4">
              <div>
                <h3 className="text-base font-bold text-white">
                  {hasOfficeReceptionist && requiredIntegrations.length === 0
                    ? "Configure Your Office Receptionist (AI Voice Agent)"
                    : hasOfficeReceptionist
                    ? "Configure Office Receptionist & Connect Required Integrations"
                    : "Connect Required Service Integrations"}
                </h3>
                <p className="text-xs text-slate-400">
                  {hasOfficeReceptionist && requiredIntegrations.length === 0
                    ? "Enter only the details needed for your Retell AI Voice Receptionist, Telnyx number assignment, Cal.com appointment booking, and live call transfer."
                    : "Credentials are encrypted at rest on the backend. Automation remains inactive until all required connections below are verified."}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full px-3 py-1 text-xs font-bold ${
                    automationActive || Boolean(recepConfig?.telnyx_phone_number)
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                      : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                  }`}
                >
                  {automationActive || Boolean(recepConfig?.telnyx_phone_number)
                    ? "Setup Active & Ready"
                    : "Pending Setup"}
                </span>
              </div>
            </div>

            {/* DYNAMIC OFFICE RECEPTIONIST ONBOARDING FLOW (shown ONLY when Office Receptionist tier is selected) */}
            {hasOfficeReceptionist && (
              <div className="rounded-2xl border border-emerald-500/30 bg-slate-900/95 p-5 sm:p-6 space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-800 pb-4">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/20 border border-emerald-500/30 text-emerald-400">
                      <PhoneCall className="h-4 w-4" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-white">
                        Office Receptionist — AI Voice Agent Onboarding
                      </h4>
                      <p className="text-[11px] text-slate-400">
                        Automatically provisions your Telnyx phone number, Retell AI voice agent,
                        Cal.com appointment tools, and live emergency transfer routing.
                      </p>
                    </div>
                  </div>
                  {recepConfig?.telnyx_phone_number && (
                    <span className="rounded-full bg-emerald-500/20 border border-emerald-500/30 px-3 py-1 text-[11px] font-mono font-bold text-emerald-300">
                      AI Number: {recepConfig.telnyx_phone_number}
                    </span>
                  )}
                </div>

                <form onSubmit={handleSaveReceptionistOnboarding} className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Business Name *
                      </label>
                      <input
                        type="text"
                        required
                        value={recepBusinessName || name}
                        onChange={(e) => setRecepBusinessName(e.target.value)}
                        placeholder="e.g. Al Noor Medical Center"
                        className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Operating Hours *
                      </label>
                      <input
                        type="text"
                        required
                        value={recepOperatingHours}
                        onChange={(e) => setRecepOperatingHours(e.target.value)}
                        placeholder="Mon-Fri 9:00 AM - 6:00 PM, Sat 10 AM - 2 PM"
                        className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Personal / Fallback Phone Number (Call Forwarding &amp; Emergency Human Transfers) *
                    </label>
                    <input
                      type="tel"
                      required
                      value={recepFallbackPhone}
                      onChange={(e) => setRecepFallbackPhone(e.target.value)}
                      placeholder="+14155550100 (or your business mobile number with country code)"
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-mono text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                    />
                    <p className="text-[11px] text-slate-500 mt-1">
                      If any caller requests a human or mentions an emergency, your AI Receptionist transfers the call live to this number.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Custom Greeting
                    </label>
                    <textarea
                      rows={2}
                      value={recepGreeting}
                      onChange={(e) => setRecepGreeting(e.target.value)}
                      placeholder="Hello! Thank you for calling Al Noor Medical Center. How can I help you today?"
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      FAQs &amp; Business Knowledge Base
                    </label>
                    <textarea
                      rows={4}
                      value={recepFaqs}
                      onChange={(e) => setRecepFaqs(e.target.value)}
                      placeholder={
                        "Q: What services do you offer?\nA: General consultations, checkups, and urgent care.\nQ: Where are you located?\nA: 120 Main St, Suite 400 (free parking available)."
                      }
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-4 space-y-3">
                    <div className="flex items-center gap-2 text-xs font-bold text-emerald-300">
                      <CalendarCheck2 className="h-4 w-4 text-emerald-400" />
                      <span>Cal.com Automated Appointment Booking</span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div>
                        <label className="block text-[11px] text-slate-400 mb-1">
                          Cal.com Booking Link
                        </label>
                        <input
                          type="url"
                          value={recepCalcomUrl}
                          onChange={(e) => setRecepCalcomUrl(e.target.value)}
                          placeholder="https://cal.com/your-office/30min"
                          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-slate-400 mb-1">
                          Event Type ID (optional)
                        </label>
                        <input
                          type="text"
                          value={recepCalcomEventTypeId}
                          onChange={(e) => setRecepCalcomEventTypeId(e.target.value)}
                          placeholder="e.g. 123456"
                          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-mono text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-slate-400 mb-1">
                          Cal.com API Key (encrypted)
                        </label>
                        <input
                          type="password"
                          value={recepCalcomApiKey}
                          onChange={(e) => setRecepCalcomApiKey(e.target.value)}
                          placeholder={
                            recepConfig?.calcom_api_key_configured
                              ? "•••••••• (saved)"
                              : "cal_live_... (optional)"
                          }
                          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-mono text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                        />
                      </div>
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={recepSaving}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-xs font-bold text-white shadow-md hover:bg-emerald-500 disabled:opacity-50 transition"
                  >
                    <PhoneCall className="h-4 w-4" />
                    <span>
                      {recepSaving
                        ? "Provisioning Telnyx Number & Retell AI Voice Agent..."
                        : recepConfig
                        ? "Update Office Receptionist & Refresh Call Forwarding Guide"
                        : "Provision AI Receptionist & Generate Call Forwarding Guide"}
                    </span>
                  </button>
                </form>

                {/* Automatically Generated Call Forwarding Setup Guide */}
                {recepConfig?.call_forwarding_guide?.assigned_ai_number && (
                  <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/30 p-4 sm:p-5 space-y-3.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-sm font-bold text-emerald-300">
                        <PhoneForwarded className="h-4 w-4 text-emerald-400" />
                        <span>Your Automatic Call Forwarding Setup Guide</span>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          handleCopyDialCode(
                            "onb-ai-num",
                            recepConfig.call_forwarding_guide.assigned_ai_number
                          )
                        }
                        className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-slate-950 px-2.5 py-1 text-xs font-mono font-bold text-emerald-300 hover:bg-emerald-500/10"
                      >
                        <span>{recepConfig.call_forwarding_guide.assigned_ai_number}</span>
                        {copiedCode === "onb-ai-num" ? (
                          <Check className="h-3.5 w-3.5" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>

                    {recepConfig.call_forwarding_guide.quick_dial_codes && (
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                        {[
                          {
                            k: "all",
                            label: "Forward All Calls",
                            val: recepConfig.call_forwarding_guide.quick_dial_codes
                              .forward_all_calls_gsm,
                          },
                          {
                            k: "missed",
                            label: "Missed Calls Only",
                            val: recepConfig.call_forwarding_guide.quick_dial_codes
                              .forward_when_unanswered_gsm,
                          },
                          {
                            k: "off",
                            label: "Turn Off Forwarding",
                            val: recepConfig.call_forwarding_guide.quick_dial_codes
                              .disable_forwarding_gsm,
                          },
                        ].map((item) => (
                          <div
                            key={item.k}
                            className="rounded-lg border border-slate-800 bg-slate-950 p-2.5 flex items-center justify-between gap-2"
                          >
                            <div>
                              <p className="text-[10px] text-slate-400 uppercase">{item.label}</p>
                              <p className="font-mono font-bold text-white">{item.val}</p>
                            </div>
                            <button
                              type="button"
                              onClick={() => handleCopyDialCode(item.k, item.val)}
                              className="rounded p-1 text-slate-400 hover:text-emerald-400"
                              title="Copy dial code"
                            >
                              {copiedCode === item.k ? (
                                <Check className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <Copy className="h-3.5 w-3.5" />
                              )}
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    {Array.isArray(recepConfig.call_forwarding_guide.steps) && (
                      <ol className="space-y-1 text-xs text-slate-200 leading-relaxed">
                        {recepConfig.call_forwarding_guide.steps.map((st: string, i: number) => (
                          <li key={i}>{st}</li>
                        ))}
                      </ol>
                    )}

                    {recepConfig.call_forwarding_guide.ios_android_menu_tip && (
                      <p className="text-[11px] text-emerald-200/90 border-t border-emerald-500/20 pt-2.5">
                        <strong>iPhone / Android Settings:</strong>{" "}
                        {recepConfig.call_forwarding_guide.ios_android_menu_tip}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="space-y-3">
              {requiredIntegrations.map((reqItem) => {
                const isConnected = reqItem.status === "connected";
                const isOAuthUnavailable = Boolean(oauthUnavailableByProvider[reqItem.provider]);
                return (
                  <div
                    key={reqItem.provider}
                    className="rounded-xl border border-slate-800 bg-slate-900/90 p-5 space-y-4"
                  >
                    <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                      <div className="space-y-1 max-w-xl">
                        <div className="flex flex-wrap items-center gap-2">
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

                      <div className="flex flex-col gap-2 w-full lg:w-auto lg:min-w-[280px]">
                        {reqItem.auth_method === "api_key" && (
                          <div className="grid grid-cols-1 gap-2">
                            <input
                              type="text"
                              placeholder="Account Identifier / Booking Handle (e.g. clinic-cal-01)"
                              value={accountIdsInput[reqItem.provider] || ""}
                              onChange={(e) =>
                                setAccountIdsInput((prev) => ({
                                  ...prev,
                                  [reqItem.provider]: e.target.value,
                                }))
                              }
                              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                            />
                            <input
                              type="url"
                              placeholder="Webhook Callback URL (optional)"
                              value={webhookUrlsInput[reqItem.provider] || ""}
                              onChange={(e) =>
                                setWebhookUrlsInput((prev) => ({
                                  ...prev,
                                  [reqItem.provider]: e.target.value,
                                }))
                              }
                              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                            />
                            <input
                              type="password"
                              placeholder={
                                isConnected ? "Paste new API Key to reconnect" : "Paste API Key *"
                              }
                              value={apiKeysInput[reqItem.provider] || ""}
                              onChange={(e) =>
                                setApiKeysInput((prev) => ({
                                  ...prev,
                                  [reqItem.provider]: e.target.value,
                                }))
                              }
                              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                            />
                          </div>
                        )}

                        {isConnected ? (
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              disabled={loading || verifyingProvider === reqItem.provider}
                              onClick={() => handleVerifyConnection(reqItem)}
                              className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 disabled:opacity-50 transition"
                              title="Test live connection and token freshness"
                            >
                              <RefreshCw
                                className={`h-3.5 w-3.5 ${
                                  verifyingProvider === reqItem.provider ? "animate-spin text-emerald-400" : ""
                                }`}
                              />
                              <span>
                                {verifyingProvider === reqItem.provider
                                  ? "Verifying..."
                                  : "Verify Live"}
                              </span>
                            </button>
                            <button
                              type="button"
                              disabled={loading}
                              onClick={() => handleConnectIntegration(reqItem)}
                              className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50 transition"
                              title="Re-authenticate with provider"
                            >
                              <Link2 className="h-3.5 w-3.5" />
                              <span>Reconnect</span>
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            disabled={loading}
                            onClick={() => handleConnectIntegration(reqItem)}
                            className="flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 transition"
                          >
                            {reqItem.auth_method === "oauth" ? (
                              <ExternalLink className="h-3.5 w-3.5" />
                            ) : (
                              <Lock className="h-3.5 w-3.5" />
                            )}
                            <span>
                              {reqItem.auth_method === "oauth"
                                ? `Authorize ${reqItem.display_name}`
                                : "Save & Connect"}
                            </span>
                          </button>
                        )}
                        {reqItem.provider === "whatsapp" && (
                          <button
                            type="button"
                            onClick={() => setShowDirectWhatsApp((prev) => !prev)}
                            className="text-[11px] font-semibold text-emerald-400 hover:text-emerald-300 text-center underline underline-offset-2"
                          >
                            {showDirectWhatsApp
                              ? "Hide Direct Cloud API Form"
                              : "Or Connect via WhatsApp Cloud API Token"}
                          </button>
                        )}
                      </div>
                    </div>

                    {reqItem.provider === "whatsapp" && showDirectWhatsApp && (
                      <div className="rounded-xl border border-emerald-500/30 bg-slate-950/90 p-4 space-y-3 text-xs">
                        <div>
                          <p className="font-bold text-emerald-300">
                            Direct WhatsApp Business Cloud API Connection (Instant)
                          </p>
                          <p className="text-[11px] text-slate-400">
                            Paste your Meta Cloud API Phone Number ID and Permanent System User Token — encrypted at rest on the backend without waiting for Meta Embedded Signup review.
                          </p>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                          <input
                            type="text"
                            placeholder="Phone Number ID *"
                            value={directWaPhoneId}
                            onChange={(e) => setDirectWaPhoneId(e.target.value)}
                            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-mono text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                          />
                          <input
                            type="text"
                            placeholder="WABA ID (optional)"
                            value={directWaWabaId}
                            onChange={(e) => setDirectWaWabaId(e.target.value)}
                            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-mono text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                          />
                          <input
                            type="password"
                            placeholder="Permanent Access Token *"
                            value={directWaToken}
                            onChange={(e) => setDirectWaToken(e.target.value)}
                            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-mono text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                          />
                        </div>
                        <div className="flex justify-end">
                          <button
                            type="button"
                            disabled={loading}
                            onClick={handleDirectWhatsAppConnect}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 transition"
                          >
                            <Lock className="h-3.5 w-3.5" />
                            <span>Save &amp; Connect WhatsApp Cloud API</span>
                          </button>
                        </div>
                      </div>
                    )}

                    {isOAuthUnavailable && (
                      <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 space-y-2.5 text-xs">
                        <p className="font-bold text-amber-300">
                          One-Click OAuth Setup Not Enabled Yet — Sandbox &amp; Assisted Setup Available
                        </p>
                        <p className="text-slate-300 leading-relaxed">
                          Direct {reqItem.display_name} OAuth sign-in is not yet configured on this server environment.
                          Your workspace remains safe in Sandbox Mode, and our engineering team can connect your account for you.
                        </p>
                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          <button
                            type="button"
                            onClick={() => openSupportForProvider(reqItem.provider, reqItem.display_name)}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-bold text-slate-950 hover:bg-amber-400 transition"
                          >
                            <LifeBuoy className="h-3.5 w-3.5" />
                            <span>Request Setup Support</span>
                          </button>
                          <a
                            href={SUPPORT_WHATSAPP_LINK}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/20 transition"
                          >
                            <MessageSquare className="h-3.5 w-3.5" />
                            <span>WhatsApp: {SUPPORT_WHATSAPP_NUMBER}</span>
                          </a>
                          <a
                            href="/dashboard"
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800 transition"
                          >
                            <span>Continue to Dashboard</span>
                            <ArrowRight className="h-3 w-3" />
                          </a>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-slate-800">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Zero secrets stored in browser. Encrypted with AES-128-Fernet at rest.</span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {hasOfficeReceptionist && (
                  <a
                    href="/receptionist"
                    className="flex items-center justify-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-4 py-2.5 text-sm font-semibold text-emerald-300 hover:bg-emerald-500/25 transition"
                  >
                    <PhoneCall className="h-4 w-4" />
                    <span>Open Office Receptionist</span>
                  </a>
                )}
                <a
                  href="/dashboard"
                  className="flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 transition"
                >
                  <span>Open Client Performance Dashboard</span>
                  <ArrowRight className="h-4 w-4" />
                </a>
              </div>
            </div>
          </div>
        )}
      </div>

      <SupportRequestModal
        isOpen={supportModalOpen}
        onClose={() => setSupportModalOpen(false)}
        defaultSubject={supportDefaults.subject}
        defaultCategory={supportDefaults.category}
        defaultMessage={supportDefaults.message}
        defaultProvider={supportDefaults.provider}
      />
    </div>
  );
}
