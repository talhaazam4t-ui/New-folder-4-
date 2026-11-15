"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "../../components/shared/Navbar";
import { Sidebar } from "../../components/shared/Sidebar";
import { apiRequest } from "../../lib/api";
import { clearSession, getActiveTenant, getAuthToken } from "../../lib/auth";

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
  const [oauthCode, setOauthCode] = useState("meta_auth_code_sandbox_9912");
  const [simPhone, setSimPhone] = useState("+15550199911");
  const [simName, setSimName] = useState("Tenant Unit 4B");
  const [simMessage, setSimMessage] = useState("Paid rent $1800 for Unit 4B");
  const [simResult, setSimResult] = useState<Record<string, unknown> | null>(null);
  const [confirmationSlug, setConfirmationSlug] = useState("");
  const [purgeReason, setPurgeReason] = useState("Account termination requested by owner");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

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
    loadSettingsWorkspace();
  }, []);

  const handleConnectWhatsApp = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMessage(null);
    const res = await apiRequest("/api/v1/integrations/whatsapp/connect", {
      method: "POST",
      body: JSON.stringify({ oauth_code: oauthCode }),
    });
    if (res.success) {
      setStatusMessage("WhatsApp Business Account connected via Meta Embedded Signup!");
      loadSettingsWorkspace();
    } else {
      setStatusMessage(res.error?.message || "Failed to connect WhatsApp.");
    }
  };

  const handleSimulateInbound = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMessage(null);
    const res = await apiRequest("/api/v1/integrations/whatsapp/simulate", {
      method: "POST",
      body: JSON.stringify({
        sender_phone: simPhone,
        sender_name: simName,
        message_text: simMessage,
      }),
    });
    if (res.data) {
      setSimResult(res.data);
      setStatusMessage("Processed inbound WhatsApp webhook message.");
      loadSettingsWorkspace();
    }
  };

  const handleMarkRead = async (id: string) => {
    await apiRequest(`/api/v1/notifications/${id}/read`, { method: "PATCH" });
    loadSettingsWorkspace();
  };

  const handlePurgeTenant = async (e: React.FormEvent) => {
    e.preventDefault();
    const tenant = getActiveTenant();
    const tenantId = tenant?.id;
    if (!tenantId) return;
    setStatusMessage(null);
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
      setStatusMessage(res.error?.message || "Account deletion failed: verify company handle.");
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Navbar />
      <div className="flex flex-1">
        <Sidebar />
        <main className="flex-1 p-8 space-y-8 overflow-y-auto">
          <div>
            <h1 className="text-2xl font-bold text-white">Integrations, WhatsApp & Notifications</h1>
            <p className="text-slate-400 text-sm mt-1">
              Self-service Meta Embedded Signup for WhatsApp Business, automated financial/lead webhook routing, and notification center.
            </p>
          </div>

          {statusMessage && (
            <div className="p-4 rounded-lg bg-emerald-950/60 border border-emerald-700 text-emerald-200 text-sm">
              {statusMessage}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Meta Embedded Signup Card */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <h2 className="text-lg font-semibold text-white">
                WhatsApp Business (Meta Embedded Signup)
              </h2>
              <p className="text-xs text-slate-400">
                Authorize your WhatsApp Business Account (WABA) directly via Meta OAuth without manual admin intervention.
              </p>
              <form onSubmit={handleConnectWhatsApp} className="space-y-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Meta Embedded Signup OAuth Code
                  </label>
                  <input
                    type="text"
                    required
                    value={oauthCode}
                    onChange={(e) => setOauthCode(e.target.value)}
                    className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium"
                >
                  Authorize & Connect WhatsApp Business
                </button>
              </form>

              <div className="pt-4 border-t border-slate-800 space-y-2">
                <h3 className="text-xs font-semibold uppercase text-slate-400">
                  Connected Tenant Integrations
                </h3>
                {integrations.map((intg) => (
                  <div
                    key={intg.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs"
                  >
                    <div>
                      <span className="font-semibold text-white uppercase">{intg.provider}</span>{" "}
                      <span className="text-slate-400">({intg.external_account_id})</span>
                    </div>
                    <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 font-medium">
                      {intg.status}
                    </span>
                  </div>
                ))}
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
