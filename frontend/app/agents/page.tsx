"use client";

import React, { useEffect, useState } from "react";
import { AdminNavbar } from "../../components/admin/AdminNavbar";
import { AdminSidebar } from "../../components/admin/AdminSidebar";
import { Navbar } from "../../components/shared/Navbar";
import { Sidebar } from "../../components/shared/Sidebar";
import { apiRequest } from "../../lib/api";
import { clearActiveTenant, getActiveTenant, getAuthToken, isSuperAdminUser, setActiveTenant } from "../../lib/auth";

interface AgentItem {
  name: string;
  category: string;
  description: string;
  version: string;
  allowed_tools: string[];
  max_steps: number;
  enabled_for_tenant: boolean;
  execution_limit: number;
  budget_limit: number;
}

interface StageResult {
  agent_name: string;
  role: string;
  model: string;
  output: string;
  tokens_used: number;
  estimated_cost: number;
}

interface ApprovalItem {
  id: string;
  task_id: string | null;
  action_type: string;
  proposed_action: Record<string, unknown>;
  status: string;
  requested_by: string;
  expires_at: string;
}

interface ExecutionItem {
  id: string;
  task_id: string;
  status: string;
  tokens_used: number;
  estimated_cost: number;
  duration_ms: number | null;
  created_at: string;
}

export default function AgentsPage() {
  const [tenants, setTenants] = useState<Array<{ id: string; name: string; slug: string; industry?: string }>>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string>("");
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [executions, setExecutions] = useState<ExecutionItem[]>([]);
  const [selectedAgent, setSelectedAgent] = useState("master_orchestrator");
  const [objective, setObjective] = useState("");
  const [actionType, setActionType] = useState("");
  const [stages, setStages] = useState<StageResult[]>([]);
  const [finalOutput, setFinalOutput] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [isAdminView, setIsAdminView] = useState(false);

  const loadAgentWorkspace = async (tenantIdOverride?: string) => {
    const tId = tenantIdOverride || selectedTenantId || getActiveTenant()?.id;
    if (!tId) return;

    const reqHeaders = { "X-Tenant-ID": tId };
    const [agentsRes, approvalsRes, execsRes] = await Promise.all([
      apiRequest("/api/v1/agents", { headers: reqHeaders }),
      apiRequest("/api/v1/approvals?status=pending", { headers: reqHeaders }),
      apiRequest("/api/v1/agents/executions?limit=25", { headers: reqHeaders }),
    ]);

    if (Array.isArray(agentsRes)) setAgents(agentsRes);
    else if (agentsRes.data) setAgents(agentsRes.data);
    else if (agentsRes.error) setErrorMessage(agentsRes.error.message);

    if (Array.isArray(approvalsRes)) setApprovals(approvalsRes);
    else if (approvalsRes.data) setApprovals(approvalsRes.data);
    else if (approvalsRes.error) setErrorMessage(approvalsRes.error.message);

    if (Array.isArray(execsRes)) setExecutions(execsRes);
    else if (execsRes.data) setExecutions(execsRes.data);
  };

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    const adminMode = isSuperAdminUser();
    setIsAdminView(adminMode);

    (async () => {
      let currentTenant = getActiveTenant();
      if (!adminMode) {
        if (!currentTenant?.id) {
          const tenantsRes = await apiRequest("/api/v1/tenants");
          const list = Array.isArray(tenantsRes)
            ? tenantsRes
            : Array.isArray(tenantsRes?.data)
            ? tenantsRes.data
            : [];
          if (list.length > 0) {
            currentTenant = list[0];
            setActiveTenant(list[0], true);
          }
        }
        if (currentTenant?.id) {
          setSelectedTenantId(currentTenant.id);
          await loadAgentWorkspace(currentTenant.id);
        } else {
          window.location.href = "/onboarding";
        }
        return;
      }

      const tenantsRes = await apiRequest("/api/v1/admin/tenants");
      const list = Array.isArray(tenantsRes?.data) ? tenantsRes.data : [];
      setTenants(list);

      const isValidStoredTenant =
        Boolean(currentTenant?.id) &&
        (list.length === 0 || list.some((t: any) => t.id === currentTenant!.id));

      if (!isValidStoredTenant) {
        if (list.length > 0) {
          currentTenant = list[0];
          setActiveTenant(list[0], false);
        } else {
          clearActiveTenant();
          currentTenant = null;
        }
      }

      if (currentTenant?.id) {
        setSelectedTenantId(currentTenant.id);
        await loadAgentWorkspace(currentTenant.id);
      } else {
        setErrorMessage("No client workspaces registered yet. Create or onboard a tenant first.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSwitchTenant = async (tenantId: string) => {
    setSelectedTenantId(tenantId);
    setErrorMessage(null);
    setStatusMessage(null);
    const chosen = tenants.find((t) => t.id === tenantId);
    if (chosen) {
      setActiveTenant(chosen, false);
    }
    await loadAgentWorkspace(tenantId);
  };

  const handleToggleAgent = async (agent: AgentItem) => {
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest(`/api/v1/agents/${agent.name}/configure`, {
      method: "POST",
      headers: selectedTenantId ? { "X-Tenant-ID": selectedTenantId } : undefined,
      body: JSON.stringify({
        enabled: !agent.enabled_for_tenant,
        execution_limit: agent.execution_limit,
        budget_limit: agent.budget_limit,
      }),
    });
    if (!res.error && (res.name || res.data?.name || res.success)) {
      setStatusMessage(`Updated configuration for ${agent.name}`);
      loadAgentWorkspace();
    } else {
      setErrorMessage(res.error?.message || `Failed to update configuration for ${agent.name}.`);
    }
  };

  const handleOrchestrate = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunning(true);
    setStatusMessage(null);
    setErrorMessage(null);
    setStages([]);
    setFinalOutput(null);

    const res = await apiRequest("/api/v1/agents/orchestrate", {
      method: "POST",
      headers: selectedTenantId ? { "X-Tenant-ID": selectedTenantId } : undefined,
      body: JSON.stringify({
        objective,
        agent_name: selectedAgent,
        action_type: actionType || null,
      }),
    });

    setRunning(false);
    const payload = res.data || res;
    if (!res.error && payload && payload.status) {
      setStages(payload.stages || []);
      setFinalOutput(payload.final_output || null);
      if (payload.requires_approval) {
        setStatusMessage("Action paused for Human-in-the-Loop Approval.");
      } else {
        setStatusMessage(`Orchestration completed (${payload.total_tokens || 0} tokens).`);
      }
      loadAgentWorkspace();
    } else {
      setErrorMessage(res.error?.message || "Agent orchestration failed.");
    }
  };

  const handleDecision = async (approvalId: string, decision: "approve" | "reject") => {
    setStatusMessage(null);
    setErrorMessage(null);
    const res = await apiRequest(`/api/v1/approvals/${approvalId}/${decision}`, {
      method: "POST",
      headers: selectedTenantId ? { "X-Tenant-ID": selectedTenantId } : undefined,
      body: JSON.stringify({ reason: `Reviewed via Agent Governance Console (${decision})` }),
    });
    if (!res.error && (res.success || res.id || res.data?.id)) {
      setStatusMessage(`Approval request ${decision}d.`);
      loadAgentWorkspace();
    } else {
      setErrorMessage(res.error?.message || `Failed to ${decision} approval request.`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {isAdminView ? <AdminNavbar /> : <Navbar />}
      <div className="flex flex-1">
        {isAdminView ? (
          <AdminSidebar currentPath="/agents" activeTab="" />
        ) : (
          <Sidebar currentPath="/agents" />
        )}
        <main className="flex-1 min-w-0 p-4 sm:p-6 md:p-8 space-y-8 overflow-y-auto">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-white">AI Agent Orchestration & Governance</h1>
              <p className="text-slate-400 text-sm mt-1">
                Bounded multi-agent hierarchy (Planner → Researcher → Executor → Reviewer) with strict tool permissions and human approval gates.
              </p>
            </div>
            {tenants.length > 0 && (
              <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs">
                <span className="text-slate-400">Workspace:</span>
                <select
                  value={selectedTenantId}
                  onChange={(e) => handleSwitchTenant(e.target.value)}
                  className="bg-transparent font-semibold text-emerald-400 focus:outline-none"
                >
                  {tenants.map((t) => (
                    <option key={t.id} value={t.id} className="bg-slate-900 text-white">
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
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

          {/* Interactive Orchestrator Console + Pending Approvals */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-white mb-4">Run Multi-Agent Orchestrator</h2>
              <form onSubmit={handleOrchestrate} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Target Agent</label>
                    <select
                      value={selectedAgent}
                      onChange={(e) => setSelectedAgent(e.target.value)}
                      className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                    >
                      {agents.map((a) => (
                        <option key={a.name} value={a.name}>
                          {a.name} ({a.category})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Action Classification (Optional)</label>
                    <select
                      value={actionType}
                      onChange={(e) => setActionType(e.target.value)}
                      className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                    >
                      <option value="">Standard Bounded Task</option>
                      <option value="publish_marketing_campaign">Publish Campaign (Requires Approval)</option>
                      <option value="send_bulk_whatsapp">Bulk WhatsApp Broadcast (Requires Approval)</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Business or Operational Objective</label>
                  <textarea
                    required
                    rows={3}
                    value={objective}
                    onChange={(e) => setObjective(e.target.value)}
                    placeholder="e.g. Analyze this month's rent collection rate and draft polite follow-up reminders for overdue units."
                    className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-sm text-white"
                  />
                </div>
                <button
                  type="submit"
                  disabled={running}
                  className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium transition"
                >
                  {running ? "Orchestrating Bounded Pipeline..." : "Execute Agent Pipeline"}
                </button>
              </form>

              {stages.length > 0 && (
                <div className="mt-6 space-y-3 border-t border-slate-800 pt-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Pipeline Execution Trace
                  </h3>
                  {stages.map((st, idx) => (
                    <div key={idx} className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs space-y-1">
                      <div className="flex justify-between text-indigo-300 font-medium">
                        <span>
                          Stage {idx + 1}: {st.role} ({st.agent_name})
                        </span>
                        <span className="text-slate-400">
                          {st.model} • {st.tokens_used} tok
                        </span>
                      </div>
                      <p className="text-slate-300 whitespace-pre-wrap">{st.output}</p>
                    </div>
                  ))}
                </div>
              )}
              {finalOutput && stages.length === 0 && (
                <div className="mt-4 p-3 rounded-lg bg-amber-950/40 border border-amber-800 text-amber-200 text-xs">
                  {finalOutput}
                </div>
              )}
            </div>

            {/* Human-in-the-Loop Approval Queue */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-white mb-4">
                Pending Human Approvals ({approvals.length})
              </h2>
              {approvals.length === 0 ? (
                <p className="text-sm text-slate-500">
                  No sensitive actions awaiting human verification.
                </p>
              ) : (
                <div className="space-y-3">
                  {approvals.map((app) => (
                    <div
                      key={app.id}
                      className="p-4 rounded-lg bg-slate-950 border border-amber-800/60 space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-900/50 text-amber-300">
                          {app.action_type}
                        </span>
                        <span className="text-xs text-slate-400">
                          Requested by {app.requested_by}
                        </span>
                      </div>
                      <pre className="text-xs text-slate-300 bg-slate-900 p-2 rounded overflow-x-auto">
                        {JSON.stringify(app.proposed_action, null, 2)}
                      </pre>
                      <div className="flex gap-2 pt-1">
                        <button
                          onClick={() => handleDecision(app.id, "approve")}
                          className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium"
                        >
                          Approve & Execute
                        </button>
                        <button
                          onClick={() => handleDecision(app.id, "reject")}
                          className="px-3 py-1.5 rounded bg-rose-700 hover:bg-rose-600 text-white text-xs font-medium"
                        >
                          Reject & Cancel
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Registered Agents Matrix */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-5 border-b border-slate-800">
              <h2 className="text-lg font-semibold text-white">Bounded Agent Registry & Tool Permissions</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-950 text-slate-400 text-xs uppercase">
                  <tr>
                    <th className="py-3 px-4">Agent</th>
                    <th className="py-3 px-4">Category</th>
                    <th className="py-3 px-4">Explicit Allowed Tools</th>
                    <th className="py-3 px-4">Max Steps</th>
                    <th className="py-3 px-4">Budget Cap</th>
                    <th className="py-3 px-4">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {agents.map((ag) => (
                    <tr key={ag.name} className="hover:bg-slate-800/40">
                      <td className="py-3 px-4">
                        <div className="font-medium text-white">{ag.name}</div>
                        <div className="text-xs text-slate-400">{ag.description}</div>
                      </td>
                      <td className="py-3 px-4 text-xs uppercase text-indigo-300">{ag.category}</td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1">
                          {ag.allowed_tools.map((t) => (
                            <span
                              key={t}
                              className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-xs"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-slate-300">{ag.max_steps}</td>
                      <td className="py-3 px-4 text-slate-300">${ag.budget_limit.toFixed(2)}</td>
                      <td className="py-3 px-4">
                        <button
                          onClick={() => handleToggleAgent(ag)}
                          className={`px-2.5 py-1 rounded text-xs font-medium ${
                            ag.enabled_for_tenant
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-700"
                              : "bg-slate-800 text-slate-400 border border-slate-700"
                          }`}
                        >
                          {ag.enabled_for_tenant ? "Enabled" : "Disabled"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Execution Telemetry */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-5 border-b border-slate-800">
              <h2 className="text-lg font-semibold text-white">Recent Execution Telemetry</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-950 text-slate-400 text-xs uppercase">
                  <tr>
                    <th className="py-3 px-4">Execution ID</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Tokens</th>
                    <th className="py-3 px-4">Est. Cost (USD)</th>
                    <th className="py-3 px-4">Duration</th>
                    <th className="py-3 px-4">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {executions.map((ex) => (
                    <tr key={ex.id}>
                      <td className="py-3 px-4 font-mono text-xs text-slate-300">{ex.id.slice(0, 12)}...</td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-xs bg-emerald-950 text-emerald-300">
                          {ex.status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-300">{ex.tokens_used}</td>
                      <td className="py-3 px-4 text-slate-300">${ex.estimated_cost.toFixed(5)}</td>
                      <td className="py-3 px-4 text-slate-400">{ex.duration_ms ?? 0} ms</td>
                      <td className="py-3 px-4 text-xs text-slate-400">
                        {new Date(ex.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
