"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { Sidebar } from "@/components/shared/Sidebar";
import { StatCard } from "@/components/dashboard/StatCard";
import { apiRequest } from "@/lib/api";
import { getActiveTenant, getAuthToken } from "@/lib/auth";
import {
  DollarSign,
  TrendingUp,
  Receipt,
  AlertTriangle,
  Plus,
  Download,
  Filter,
  Building,
  History,
  BarChart3,
} from "lucide-react";

interface BusinessRecordItem {
  id: string;
  record_type: string;
  title: string;
  amount: number;
  currency: string;
  description?: string;
  source: string;
  recorded_at: string;
  metadata?: {
    original_amount?: number;
    revision_history?: any[];
  };
}

interface SummaryData {
  total_income: number;
  total_rent: number;
  total_payments_received: number;
  total_expenses: number;
  total_outstanding: number;
  gross_inflow: number;
  net_cashflow: number;
  record_count: number;
}

interface CustomMetricItem {
  id: string;
  metric_name: string;
  metric_value: number;
  period_start: string;
  period_end: string;
}

export default function BusinessPage() {
  const [records, setRecords] = useState<BusinessRecordItem[]>([]);
  const [summary, setSummary] = useState<SummaryData>({
    total_income: 0,
    total_rent: 0,
    total_payments_received: 0,
    total_expenses: 0,
    total_outstanding: 0,
    gross_inflow: 0,
    net_cashflow: 0,
    record_count: 0,
  });
  const [metrics, setMetrics] = useState<CustomMetricItem[]>([]);
  const [filterType, setFilterType] = useState<string>("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // New Record Form State
  const [recordType, setRecordType] = useState("income");
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [description, setDescription] = useState("");

  // Custom Metric Form State
  const [metricName, setMetricName] = useState("");
  const [metricValue, setMetricValue] = useState("");

  const fetchBusinessData = async (selectedType = filterType) => {
    const query = selectedType ? `?record_type=${selectedType}` : "";
    const [recordsRes, summaryRes, metricsRes] = await Promise.all([
      apiRequest<BusinessRecordItem[]>(`/api/v1/business/records${query}`),
      apiRequest<SummaryData>("/api/v1/business/summary"),
      apiRequest<CustomMetricItem[]>("/api/v1/business/metrics"),
    ]);

    if (Array.isArray(recordsRes)) setRecords(recordsRes);
    else if (recordsRes.data) setRecords(recordsRes.data);

    const sumRaw = (summaryRes.data || summaryRes) as SummaryData;
    if (sumRaw && sumRaw.net_cashflow !== undefined) {
      setSummary(sumRaw);
    }

    if (Array.isArray(metricsRes)) setMetrics(metricsRes);
    else if (metricsRes.data) setMetrics(metricsRes.data);
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
    fetchBusinessData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAddRecord = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMessage(null);
    const res = await apiRequest("/api/v1/business/records", {
      method: "POST",
      body: JSON.stringify({
        record_type: recordType,
        title,
        amount: parseFloat(amount),
        currency,
        description: description || null,
        source: "manual",
      }),
    });

    if (res.id || res.data?.id) {
      setTitle("");
      setAmount("");
      setDescription("");
      setStatusMessage("Financial record added and audited.");
      fetchBusinessData();
    } else {
      setStatusMessage(res.error?.message || "Failed to add financial record.");
    }
  };

  const handleAddMetric = async (e: React.FormEvent) => {
    e.preventDefault();
    const today = new Date().toISOString().split("T")[0];
    const res = await apiRequest("/api/v1/business/custom-metrics", {
      method: "POST",
      body: JSON.stringify({
        metric_name: metricName,
        metric_value: parseFloat(metricValue),
        period_start: today,
        period_end: today,
      }),
    });

    if (res.id || res.data?.id) {
      setMetricName("");
      setMetricValue("");
      setStatusMessage("Custom business metric recorded.");
      fetchBusinessData();
    }
  };

  const handleExportReport = async () => {
    const res = await apiRequest("/api/v1/business/reports");
    const csv = res.data?.csv_content;
    if (csv && typeof window !== "undefined") {
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `talox-financial-report-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />

      <div className="flex flex-1">
        <Sidebar currentPath="/business" />

        <main className="flex-1 min-w-0 p-4 sm:p-6 md:p-8 space-y-8 max-w-7xl mx-auto w-full">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-6">
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                Business & Financial Tracking
              </h1>
              <p className="mt-1 text-xs sm:text-sm text-slate-500">
                Immutable double-entry audit ledger for income, rent collection, expenses, and receivables.
              </p>
            </div>

            <button
              onClick={handleExportReport}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 transition"
            >
              <Download className="h-4 w-4" />
              <span>Export CSV Report</span>
            </button>
          </div>

          {statusMessage && (
            <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-xs font-medium text-emerald-800">
              {statusMessage}
            </div>
          )}

          {/* KPI Summary Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            <StatCard
              title="Gross Inflow"
              value={`$${summary.gross_inflow.toLocaleString()}`}
              icon={DollarSign}
              badge={{ text: "Inflow", variant: "success" }}
              subtext="Income + Rent + Received"
            />
            <StatCard
              title="Rent Collected"
              value={`$${summary.total_rent.toLocaleString()}`}
              icon={Building}
              badge={{ text: "Property", variant: "success" }}
              subtext="Verified rent receipts"
            />
            <StatCard
              title="Expenses"
              value={`$${summary.total_expenses.toLocaleString()}`}
              icon={Receipt}
              badge={{ text: "Outflow", variant: "neutral" }}
              subtext="Operating costs"
            />
            <StatCard
              title="Outstanding"
              value={`$${summary.total_outstanding.toLocaleString()}`}
              icon={AlertTriangle}
              badge={{ text: "Receivable", variant: "warning" }}
              subtext="Pending collection"
            />
            <StatCard
              title="Net Cashflow"
              value={`$${summary.net_cashflow.toLocaleString()}`}
              icon={TrendingUp}
              badge={{
                text: summary.net_cashflow >= 0 ? "Surplus" : "Deficit",
                variant: summary.net_cashflow >= 0 ? "success" : "danger",
              }}
              subtext={`${summary.record_count} audited entries`}
            />
          </div>

          {/* Forms Grid: Add Transaction & Custom Metrics */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Add Financial Record Form */}
            <form
              onSubmit={handleAddRecord}
              className="lg:col-span-2 rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4"
            >
              <div className="flex items-center justify-between">
                <h2 className="text-base font-bold text-slate-900">Record Financial Activity</h2>
                <span className="text-[11px] text-slate-400">Audited & Tenant-Isolated</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-700">Category</label>
                  <select
                    value={recordType}
                    onChange={(e) => setRecordType(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-900"
                  >
                    <option value="income">Income</option>
                    <option value="rent">Rent Collection</option>
                    <option value="payment_received">Payment Received</option>
                    <option value="expense">Expense</option>
                    <option value="outstanding">Outstanding Receivable</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700">Amount</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    required
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    placeholder="75000.00"
                    className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700">Currency</label>
                  <input
                    type="text"
                    maxLength={3}
                    required
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                    className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900 font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-700">Title / Reference</label>
                  <input
                    type="text"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. November Rent - Property A"
                    className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700">Description (Optional)</label>
                  <input
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Notes or invoice reference"
                    className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition"
              >
                <Plus className="h-4 w-4" />
                <span>Save Audited Record</span>
              </button>
            </form>

            {/* Custom Metrics Card */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-emerald-600" />
                <h2 className="text-base font-bold text-slate-900">Custom Business KPIs</h2>
              </div>

              <form onSubmit={handleAddMetric} className="space-y-3">
                <input
                  type="text"
                  required
                  value={metricName}
                  onChange={(e) => setMetricName(e.target.value)}
                  placeholder="Metric Name (e.g. Occupancy %)"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs"
                />
                <input
                  type="number"
                  step="any"
                  required
                  value={metricValue}
                  onChange={(e) => setMetricValue(e.target.value)}
                  placeholder="Numerical Value (e.g. 94.5)"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs"
                />
                <button
                  type="submit"
                  className="w-full rounded-lg bg-slate-900 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition"
                >
                  Track Custom Metric
                </button>
              </form>

              <div className="divide-y divide-slate-100 pt-2">
                {metrics.slice(0, 4).map((m) => (
                  <div key={m.id} className="py-2 flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-700">{m.metric_name}</span>
                    <span className="font-mono font-bold text-slate-900">{m.metric_value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Transaction Ledger Table */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h3 className="text-base font-bold text-slate-900">Audited Financial Ledger</h3>
                <p className="text-xs text-slate-500">
                  Every transaction preserves its original value, source, and author.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <Filter className="h-3.5 w-3.5 text-slate-400" />
                <select
                  value={filterType}
                  onChange={(e) => {
                    setFilterType(e.target.value);
                    fetchBusinessData(e.target.value);
                  }}
                  className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-700"
                >
                  <option value="">All Categories</option>
                  <option value="income">Income</option>
                  <option value="rent">Rent</option>
                  <option value="payment_received">Payment Received</option>
                  <option value="expense">Expense</option>
                  <option value="outstanding">Outstanding</option>
                </select>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-400 uppercase font-semibold">
                    <th className="py-3 px-4">Title</th>
                    <th className="py-3 px-4">Category</th>
                    <th className="py-3 px-4">Amount</th>
                    <th className="py-3 px-4">Source</th>
                    <th className="py-3 px-4">Audit History</th>
                    <th className="py-3 px-4">Recorded At</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {records.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-slate-400">
                        No financial records found for this filter.
                      </td>
                    </tr>
                  ) : (
                    records.map((r) => (
                      <tr key={r.id} className="hover:bg-slate-50 transition">
                        <td className="py-3 px-4 font-medium text-slate-900">{r.title}</td>
                        <td className="py-3 px-4">
                          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-bold uppercase text-slate-700">
                            {r.record_type}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono font-bold text-slate-900">
                          {r.amount.toLocaleString()} {r.currency}
                        </td>
                        <td className="py-3 px-4 uppercase text-[10px] font-semibold text-slate-500">
                          {r.source}
                        </td>
                        <td className="py-3 px-4">
                          <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
                            <History className="h-3 w-3" />
                            {r.metadata?.revision_history?.length || 0} revisions
                          </span>
                        </td>
                        <td className="py-3 px-4 text-slate-500">
                          {new Date(r.recorded_at).toLocaleDateString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
