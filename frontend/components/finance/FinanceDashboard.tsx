"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { Sidebar } from "@/components/shared/Sidebar";
import { FinancialKPIRow } from "./FinancialKPIRow";
import { CashFlowChart } from "./CashFlowChart";
import { TransactionLedger } from "./TransactionLedger";
import { RentSchedulesTable } from "./RentSchedulesTable";
import { AccountsGrid } from "./AccountsGrid";
import { LogTransactionModal, NewRentScheduleModal, NewAccountModal } from "./Modals";
import { FinancialAccount, FinancialSummary, FinancialTransaction, RentSchedule } from "./types";
import { apiRequest } from "@/lib/api";
import { getActiveTenant } from "@/lib/auth";
import {
  TrendingUp,
  Receipt,
  Building2,
  Wallet,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  SlidersHorizontal,
} from "lucide-react";

export function FinanceDashboard() {
  const [tenant, setTenant] = useState<any>(null);
  const [moduleStatus, setModuleStatus] = useState<"ACTIVE" | "DISABLED" | "LOADING">("LOADING");
  const [summary, setSummary] = useState<FinancialSummary | null>(null);
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [transactions, setTransactions] = useState<FinancialTransaction[]>([]);
  const [rentSchedules, setRentSchedules] = useState<RentSchedule[]>([]);

  const [loading, setLoading] = useState(true);
  const [reminderLoading, setReminderLoading] = useState(false);
  const [toastMessage, setToastMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  // Active Tab: 'ledger' | 'schedules' | 'accounts'
  const [activeTab, setActiveTab] = useState<"ledger" | "schedules" | "accounts">("ledger");

  // Modals
  const [isLogTxOpen, setIsLogTxOpen] = useState(false);
  const [isRentModalOpen, setIsRentModalOpen] = useState(false);
  const [isAccountModalOpen, setIsAccountModalOpen] = useState(false);

  const showToast = (text: string, type: "success" | "error" = "success") => {
    setToastMessage({ text, type });
    setTimeout(() => setToastMessage(null), 4000);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const activeT = getActiveTenant();
      setTenant(activeT);

      // Check module status
      const statusRes = await apiRequest<{ active: boolean; status: "ACTIVE" | "DISABLED" }>("/api/v1/finance/status");
      const isActive = statusRes.data?.active ?? true;
      setModuleStatus(isActive ? "ACTIVE" : "DISABLED");

      // Load parallel endpoints
      const [sumRes, accRes, txRes, rentRes] = await Promise.all([
        apiRequest<FinancialSummary>("/api/v1/finance/summary"),
        apiRequest<FinancialAccount[]>("/api/v1/finance/accounts"),
        apiRequest<FinancialTransaction[]>("/api/v1/finance/transactions?limit=200"),
        apiRequest<RentSchedule[]>("/api/v1/finance/rent-schedules"),
      ]);

      if (sumRes.data) setSummary(sumRes.data);
      else if ((sumRes as any).total_cash_balance !== undefined) setSummary(sumRes as any);

      if (Array.isArray(accRes)) setAccounts(accRes);
      else if (accRes.data) setAccounts(accRes.data);

      if (Array.isArray(txRes)) setTransactions(txRes);
      else if (txRes.data) setTransactions(txRes.data);

      if (Array.isArray(rentRes)) setRentSchedules(rentRes);
      else if (rentRes.data) setRentSchedules(rentRes.data);
    } catch (err: any) {
      console.error("Failed to load finance data:", err);
      showToast("Error loading financial data", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle Mark As Paid
  const handleMarkAsPaid = async (txId: string) => {
    try {
      const res = await apiRequest(`/api/v1/finance/transactions/${txId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "paid" }),
      });

      if (res.success || res.data) {
        showToast("Transaction marked as Paid & ledger reconciled");
        loadData();
      } else {
        showToast(res.error?.message || "Failed to update transaction", "error");
      }
    } catch (err: any) {
      showToast(err.message || "Failed to mark as paid", "error");
    }
  };

  // Handle Log Transaction
  const handleLogTransaction = async (data: any) => {
    try {
      const res = await apiRequest("/api/v1/finance/transactions", {
        method: "POST",
        body: JSON.stringify(data),
      });

      if (res.success || res.data) {
        showToast("Transaction logged and account balance reconciled");
        loadData();
      } else {
        showToast(res.error?.message || "Failed to log transaction", "error");
      }
    } catch (err: any) {
      showToast(err.message || "Failed to log transaction", "error");
    }
  };

  // Handle New Rent Schedule
  const handleCreateRentSchedule = async (data: any) => {
    try {
      const res = await apiRequest("/api/v1/finance/rent-schedules", {
        method: "POST",
        body: JSON.stringify(data),
      });

      if (res.success || res.data) {
        showToast("New property lease schedule registered");
        loadData();
      } else {
        showToast(res.error?.message || "Failed to create lease schedule", "error");
      }
    } catch (err: any) {
      showToast(err.message || "Failed to create lease schedule", "error");
    }
  };

  // Handle New Account
  const handleCreateAccount = async (data: any) => {
    try {
      const res = await apiRequest("/api/v1/finance/accounts", {
        method: "POST",
        body: JSON.stringify(data),
      });

      if (res.success || res.data) {
        showToast("Financial account & vault established");
        loadData();
      } else {
        showToast(res.error?.message || "Failed to create account", "error");
      }
    } catch (err: any) {
      showToast(err.message || "Failed to create account", "error");
    }
  };

  // Handle WhatsApp Reminders
  const handleTriggerReminders = async () => {
    setReminderLoading(true);
    try {
      const res = await apiRequest<{ total_scanned: number; reminders_dispatched: number }>(
        "/api/v1/finance/whatsapp/reminders",
        { method: "POST" }
      );
      const dispatched = res.data?.reminders_dispatched ?? 0;
      showToast(`Scanned leases: dispatched ${dispatched} automated WhatsApp reminder(s)`);
      loadData();
    } catch (err: any) {
      showToast(err.message || "Failed to dispatch reminders", "error");
    } finally {
      setReminderLoading(false);
    }
  };

  // Handle Export CSV
  const handleExportCSV = () => {
    const tenantId = tenant?.id || "active";
    window.open(`/api/v1/finance/export/csv`, "_blank");
    showToast("Downloading financial CSV reconciliation statement");
  };

  return (
    <div className="min-h-screen bg-[#0B131E] text-slate-100 flex flex-col font-sans">
      <Navbar />

      <div className="flex flex-1">
        <Sidebar currentPath="/business" />

        <main className="flex-1 p-6 md:p-8 space-y-6 max-w-7xl mx-auto w-full">
          {/* Header & Status Banner */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800/80">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold tracking-tight text-white">
                  Business Financial & Rent Tracking
                </h1>
                <span className="rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-0.5 text-xs font-semibold">
                  Multi-Tenant Ledger
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Unified real-time cash flow, rent schedules, vault accounts, and automated WhatsApp reminders
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={loadData}
                disabled={loading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-850 hover:bg-slate-800 text-xs font-medium text-slate-300 border border-slate-700/80 transition"
                title="Refresh Financial Records"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin text-emerald-400" : ""}`} />
                Refresh
              </button>
            </div>
          </div>

          {/* Toast Notification */}
          {toastMessage && (
            <div
              className={`fixed bottom-6 right-6 z-50 rounded-xl px-4 py-3 shadow-2xl flex items-center gap-2.5 border text-xs font-medium transition-all ${
                toastMessage.type === "success"
                  ? "bg-slate-900 border-emerald-500/40 text-emerald-300"
                  : "bg-slate-900 border-rose-500/40 text-rose-300"
              }`}
            >
              {toastMessage.type === "success" ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              ) : (
                <AlertCircle className="h-4 w-4 text-rose-400" />
              )}
              <span>{toastMessage.text}</span>
            </div>
          )}

          {/* Module Gating Warning if Disabled by Admin */}
          {moduleStatus === "DISABLED" && (
            <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-4 flex items-start gap-3 text-xs text-amber-200">
              <AlertCircle className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold text-amber-300">
                  Business Financial Tracking Module is Currently Paused
                </p>
                <p className="text-amber-200/80 mt-0.5">
                  The Super Administrator has toggled this module to DISABLED for your account. Please contact
                  Platform Operations to re-activate full ledger capabilities.
                </p>
              </div>
            </div>
          )}

          {/* 1. KPI Summary Row */}
          <FinancialKPIRow summary={summary} loading={loading} />

          {/* 2. Interactive Cash Flow Chart */}
          <CashFlowChart
            data={summary?.monthly_chart || []}
            currency={summary?.currency || "USD"}
            loading={loading}
          />

          {/* 3. Navigation Tabs */}
          <div className="flex border-b border-slate-800 gap-6 text-xs font-semibold">
            <button
              onClick={() => setActiveTab("ledger")}
              className={`pb-3 flex items-center gap-2 border-b-2 transition ${
                activeTab === "ledger"
                  ? "border-emerald-500 text-emerald-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Receipt className="h-4 w-4" />
              Transactions & Rent Ledger ({transactions.length})
            </button>

            <button
              onClick={() => setActiveTab("schedules")}
              className={`pb-3 flex items-center gap-2 border-b-2 transition ${
                activeTab === "schedules"
                  ? "border-teal-500 text-teal-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Building2 className="h-4 w-4" />
              Property Rent Schedules ({rentSchedules.length})
            </button>

            <button
              onClick={() => setActiveTab("accounts")}
              className={`pb-3 flex items-center gap-2 border-b-2 transition ${
                activeTab === "accounts"
                  ? "border-emerald-500 text-emerald-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Wallet className="h-4 w-4" />
              Vault Accounts ({accounts.length})
            </button>
          </div>

          {/* Tab 1: Transaction & Rent Ledger */}
          {activeTab === "ledger" && (
            <TransactionLedger
              transactions={transactions}
              accounts={accounts}
              loading={loading}
              onOpenLogModal={() => setIsLogTxOpen(true)}
              onMarkAsPaid={handleMarkAsPaid}
              onExportCSV={handleExportCSV}
            />
          )}

          {/* Tab 2: Property Rent Schedules */}
          {activeTab === "schedules" && (
            <RentSchedulesTable
              schedules={rentSchedules}
              loading={loading}
              onOpenNewModal={() => setIsRentModalOpen(true)}
              onTriggerReminders={handleTriggerReminders}
              reminderLoading={reminderLoading}
            />
          )}

          {/* Tab 3: Vault Accounts */}
          {activeTab === "accounts" && (
            <AccountsGrid
              accounts={accounts}
              loading={loading}
              onOpenNewModal={() => setIsAccountModalOpen(true)}
            />
          )}
        </main>
      </div>

      {/* Modals */}
      <LogTransactionModal
        isOpen={isLogTxOpen}
        onClose={() => setIsLogTxOpen(false)}
        accounts={accounts}
        onSubmit={handleLogTransaction}
      />

      <NewRentScheduleModal
        isOpen={isRentModalOpen}
        onClose={() => setIsRentModalOpen(false)}
        onSubmit={handleCreateRentSchedule}
      />

      <NewAccountModal
        isOpen={isAccountModalOpen}
        onClose={() => setIsAccountModalOpen(false)}
        onSubmit={handleCreateAccount}
      />
    </div>
  );
}
