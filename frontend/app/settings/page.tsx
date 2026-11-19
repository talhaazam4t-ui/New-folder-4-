"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "../../components/shared/Navbar";
import { Sidebar } from "../../components/shared/Sidebar";
import { apiRequest } from "../../lib/api";
import { clearSession, getActiveTenant, getAuthToken } from "../../lib/auth";
import { ExternalLink, RefreshCw, Link2, CheckCircle2, AlertCircle } from "lucide-react";

interface IntegrationItem {
  id: string;
  provider: string;
  integration_type: string;
  status: string;
  external_account_id: string | null;
  configuration: Record<string, unknown>;
}

interface NotificationItem {
  id: string;
  channel: string;
  title: string;
  message: string;
  status: string;
  created_at: string;
}

export default function SettingsPage() {
  const [integrations, setIntegrations] = useState<IntegrationItem[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [simPhone, setSimPhone] = useState("+15550199911");
  const [simName, setSimName] = useState("Tenant Unit 4B");
  const [simMessage, setSimMessage] = useState("Paid rent $1800 for Unit 4B");
  const [simResult, setSimResult] = useState<Record<string, unknown> | null>(null);
  const [confirmationSlug, setConfirmationSlug] = useState("");
  const [purgeReason, setPurgeReason] = useState("Account termination requested by owner");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  const loadSettingsWorkspace = async () => {
    const [intRes, notifRes] = await Promise.all([
      apiRequest("/api/v1/integrations"),
      apiRequest("/api/v1/notifications"),
    ]);

    if (intRes.data && Array.isArray(intRes.data)) setIntegrations(intRes.data);
    if (notifRes.data && Array.isArray(notifRes.data)) setNotifications(notifRes.data);
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
        setErrorMessage(`OAuth authorization failed: ${errorDesc || oauthError}`);
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (connectedProvider && statusParam === "success") {
        setStatusMessage(`${connectedProvider.replace('_', ' ').toUpperCase()} successfully connected and verified via OAuth 2.0!`);
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (oauthCode && oauthState) {
        setStatusMessage("Completing OAuth 2.0 verification and token exchange...");
        try {
          const cbRes = await apiRequest("/api/v1/integrations/oauth/callback", {
            method: "POST",
            body: JSON.stringify({
              code: oauthCode,
              state: oauthState,
            }),
          });
          if (cbRes.success && cbRes.data) {
            sessionStorage.removeItem("talox_oauth_return_to");
            setStatusMessage(`${cbRes.data.display_name || "Service"} connected and verified via OAuth 2.0!`);
          } else {
            setErrorMessage(cbRes.error?.message || cbRes.message || "Failed to complete token exchange.");
          }
        } catch (err: any) {
          setErrorMessage(err.message || "OAuth callback processing error.");
        } finally {
          window.history.replaceState({}, document.title, window.location.pathname);
        }
      }

      await loadSettingsWorkspace();
    };

    checkOAuthCallback();
  }, []);

  const handleOAuthConnect = async (provider: string) => {
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const authInfo = await apiRequest(
        `/api/v1/integrations/oauth/${provider}/authorize?return_to=/settings`
      );
      if (authInfo.success && authInfo.data?.authorization_url) {
        if (typeof window !== "undefined") {
          sessionStorage.setItem("talox_oauth_return_to", "/settings");
        }
        window.location.href = authInfo.data.authorization_url;
      } else {
        setErrorMessage(authInfo.error?.message || `Failed to initiate OAuth for ${provider}`);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "OAuth redirect failed.");
    }
  };

  const handleTestConnection = async (integrationId: string, providerName: string) => {
    setErrorMessage(null);
    setStatusMessage(null);
    setVerifyingId(integrationId);
    try {
      const res = await apiRequest(`/api/v1/integrations/${integrationId}/test`, {
        method: "POST",
      });
      if (res.success && res.data?.status === "connected") {
        setStatusMessage(`${providerName.toUpperCase()} live connection verified active!`);
      } else {
        setErrorMessage(
          `${providerName.toUpperCase()} live check failed: ${
            res.data?.configuration?.last_test_result || "Token invalid. Please Reconnect."
          }`
        );
      }
      await loadSettingsWorkspace();
    } catch (err: any) {
      setErrorMessage(err.message || `Failed to verify ${providerName}.`);
    } finally {
      setVerifyingId(null);
    }
  };

  const handleSimulateInbound = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest("/api/v1/integrations/whatsapp/simulate", {
      method: "POST",
      body: JSON.stringify({
        sender_phone: simPhone,
        sender_name: simName,
        message_text: simMessage,
      }),
    });
    if (!res.error && res.data) {
      setSimResult(res.data);
      setStatusMessage("Processed inbound WhatsApp webhook message.");
      loadSettingsWorkspace();
    } else {
      setErrorMessage(res.error?.message || "Failed to process inbound WhatsApp event.");
    }
  };

  const handleMarkRead = async (id: string) => {
    setErrorMessage(null);
    const res = await apiRequest(`/api/v1/notifications/${id}/read`, { method: "PATCH" });
    if (res.error || res.success === false) {
      setErrorMessage(res.error?.message || "Failed to mark notification as read.");
      return;
    }
    loadSettingsWorkspace();
  };

  const handlePurgeTenant = async (e: React.FormEvent) => {
    e.preventDefault();
    const tenant = getActiveTenant();
    const tenantId = tenant?.id;
    if (!tenantId) return;
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest(`/api/v1/tenants/${tenantId}`, {
      method: "DELETE",
      body: JSON.stringify({
        confirmation_slug: confirmationSlug,
        reason: purgeReason,
      }),
    });
    if (res.success) {
      clearSession();
      window.location.href = "/login";
    } else {
      setErrorMessage(res.error?.message || "Account deletion failed: verify company handle.");
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Navbar />
      <div className="flex flex-1">
        <Sidebar currentPath="/settings" />
        <main className="flex-1 p-8 space-y-8 overflow-y-auto">
          <div>
            <h1 className="text-2xl font-bold text-white">Integrations, WhatsApp & Notifications</h1>
            <p className="text-slate-400 text-sm mt-1">
              Self-service Meta Embedded Signup for WhatsApp Business, automated financial/lead webhook routing, and notification center.
            </p>
          </div>

          {statusMessage && (
            <div className="flex items-center gap-2 p-4 rounded-lg bg-emerald-950/60 border border-emerald-700 text-emerald-200 text-sm">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              <span>{statusMessage}</span>
            </div>
          )}

          {errorMessage && (
            <div className="flex items-center gap-2 p-4 rounded-lg bg-red-950/60 border border-red-700 text-red-200 text-sm">
              <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
              <span>{errorMessage}</span>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Third-Party OAuth 2.0 & Cloud Integrations Manager */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white">
                    Third-Party OAuth 2.0 Integrations
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Live OAuth 2.0 redirects, token encryption at rest, and background token health verification.
                  </p>
                </div>
              </div>

              <div className="space-y-3 pt-2">
                {[
                  { id: "whatsapp", name: "WhatsApp Cloud API", provider: "whatsapp", auth: "Meta OAuth" },
                  { id: "google_calendar", name: "Google Calendar", provider: "google_calendar", auth: "Google OAuth" },
                  { id: "gmail", name: "Gmail / Email Provider", provider: "gmail", auth: "Google OAuth" },
                  { id: "google_business", name: "Google Business / Maps", provider: "google_business", auth: "Google OAuth" },
                ].map((item) => {
                  const existing = integrations.find((i) => i.provider === item.provider);
                  const isConnected = existing?.status === "connected";
                  const isError = existing?.status === "error";

                  return (
                    <div
                      key={item.id}
                      className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs"
                    >
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-white">{item.name}</span>
                          <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-400 font-mono">
                            {item.auth}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded font-medium text-[10px] uppercase ${
                              isConnected
                                ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800"
                                : isError
                                ? "bg-red-950/80 text-red-300 border border-red-800"
                                : "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {isConnected ? "Connected" : isError ? "Error" : "Disconnected"}
                          </span>
                        </div>
                        {existing?.external_account_id && (
                          <p className="text-[11px] font-mono text-emerald-400">
                            Linked: {existing.external_account_id}
                          </p>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {isConnected && existing?.id && (
                          <button
                            type="button"
                            disabled={verifyingId === existing.id}
                            onClick={() => handleTestConnection(existing.id, item.name)}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 transition disabled:opacity-50"
                            title="Verify live connection health"
                          >
                            <RefreshCw
                              className={`h-3 w-3 ${verifyingId === existing.id ? "animate-spin text-emerald-400" : ""}`}
                            />
                            <span>{verifyingId === existing.id ? "Verifying..." : "Verify"}</span>
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() => handleOAuthConnect(item.provider)}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded font-medium transition ${
                            isConnected
                              ? "border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
                              : "bg-emerald-600 hover:bg-emerald-500 text-white"
                          }`}
                        >
                          {isConnected ? <Link2 className="h-3 w-3" /> : <ExternalLink className="h-3 w-3" />}
                          <span>{isConnected || isError ? "Reconnect" : "Connect"}</span>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Inbound WhatsApp Financial & Lead Webhook Simulator */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <h2 className="text-lg font-semibold text-white">
                WhatsApp Webhook Processor (Live & Sandbox Test)
              </h2>
              <p className="text-xs text-slate-400">
                Unambiguous payments record to the ledger; ambiguous financial messages automatically route to Human Approval.
              </p>
              <form onSubmit={handleSimulateInbound} className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="text"
                    required
                    value={simName}
                    onChange={(e) => setSimName(e.target.value)}
                    placeholder="Sender Name"
                    className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                  />
                  <input
                    type="text"
                    required
                    value={simPhone}
                    onChange={(e) => setSimPhone(e.target.value)}
                    placeholder="Sender Phone"
                    className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                  />
                </div>
                <textarea
                  rows={2}
                  required
                  value={simMessage}
                  onChange={(e) => setSimMessage(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                />
                <button
                  type="submit"
                  className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
                >
                  Process Inbound WhatsApp Event
                </button>
              </form>
              {simResult && (
                <pre className="p-3 rounded bg-slate-950 border border-slate-800 text-xs text-slate-300 overflow-x-auto">
                  {JSON.stringify(simResult, null, 2)}
                </pre>
              )}
            </div>
          </div>

          {/* Notification Center */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-5 border-b border-slate-800">
              <h2 className="text-lg font-semibold text-white">
                Workspace Notification Center ({notifications.length})
              </h2>
            </div>
            <div className="divide-y divide-slate-800">
              {notifications.map((n) => (
                <div key={n.id} className="p-4 flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-indigo-300 text-xs uppercase">
                        {n.channel}
                      </span>
                      <span className="font-medium text-white text-sm">{n.title}</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">{n.message}</p>
                  </div>
                  {n.status === "unread" ? (
                    <button
                      onClick={() => handleMarkRead(n.id)}
                      className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
                    >
                      Mark Read
                    </button>
                  ) : (
                    <span className="text-xs text-slate-500">Read</span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Danger Zone: GDPR Account Termination & Cascading Data Purge */}
          <div className="bg-rose-950/20 border border-rose-900/60 rounded-xl p-6 space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-rose-300">
                Danger Zone — Account Termination & Cascading Data Purge (GDPR Compliance)
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Permanently deletes this company workspace and cascades deletion across all financial records, campaigns, leads, tasks, integrations, and usage telemetry.
              </p>
            </div>
            <form onSubmit={handlePurgeTenant} className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <input
                type="text"
                required
                placeholder="Type company slug to confirm"
                value={confirmationSlug}
                onChange={(e) => setConfirmationSlug(e.target.value)}
                className="rounded-lg bg-slate-950 border border-rose-800/60 px-3 py-2 text-sm text-white"
              />
              <input
                type="text"
                value={purgeReason}
                onChange={(e) => setPurgeReason(e.target.value)}
                placeholder="Reason for account termination"
                className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
              />
              <button
                type="submit"
                className="py-2 px-4 rounded-lg bg-rose-700 hover:bg-rose-600 text-white text-sm font-semibold"
              >
                Permanently Purge Account & All Data
              </button>
            </form>
          </div>
        </main>
      </div>
    </div>
  );
}
