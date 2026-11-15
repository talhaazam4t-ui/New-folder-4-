"use client";

import React, { useState } from "react";
import { FinancialAccount, FinancialTransaction } from "./types";
import {
  Search,
  Filter,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ArrowDownLeft,
  ArrowUpRight,
  Home,
  Plus,
  Download,
} from "lucide-react";

interface LedgerProps {
  transactions: FinancialTransaction[];
  accounts: FinancialAccount[];
  loading: boolean;
  onOpenLogModal: () => void;
  onMarkAsPaid: (txId: string) => Promise<void>;
  onExportCSV: () => void;
}

export function TransactionLedger({
  transactions,
  accounts,
  loading,
  onOpenLogModal,
  onMarkAsPaid,
  onExportCSV,
}: LedgerProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const getAccountName = (accId?: string | null) => {
    if (!accId) return "Unallocated";
    const acc = accounts.find((a) => a.id === accId);
    return acc ? acc.name : "Vault";
  };

  const filtered = transactions.filter((tx) => {
    const matchesSearch =
      tx.counterparty_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      tx.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (tx.notes && tx.notes.toLowerCase().includes(searchTerm.toLowerCase()));

    const matchesType = typeFilter === "all" || tx.type === typeFilter;
    const matchesStatus = statusFilter === "all" || tx.status === statusFilter;

    return matchesSearch && matchesType && matchesStatus;
  });

  const handleMarkPaid = async (txId: string) => {
    setUpdatingId(txId);
    try {
      await onMarkAsPaid(txId);
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="rounded-xl bg-[#131F2E] border border-slate-800/80 shadow-lg overflow-hidden">
      {/* Table Header Controls */}
      <div className="p-5 border-b border-slate-800/80 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold text-white">Financial & Rent Ledger</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Audit-reconciled operational records with instant status reconciliation
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Search Bar */}
          <div className="relative min-w-[200px]">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search client/vendor..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
            />
          </div>

          {/* Type Filter */}
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
          >
            <option value="all">All Types</option>
            <option value="income">Income</option>
            <option value="rent">Property Rent</option>
            <option value="expense">Expenses</option>
          </select>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
          >
            <option value="all">All Statuses</option>
            <option value="paid">Paid</option>
            <option value="pending">Pending</option>
            <option value="overdue">Overdue</option>
          </select>

          {/* Export CSV */}
          <button
            onClick={onExportCSV}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-300 border border-slate-700 transition"
            title="Download CSV Statement"
          >
            <Download className="h-3.5 w-3.5 text-slate-400" />
            CSV
          </button>

          {/* Log Transaction Button */}
          <button
            onClick={onOpenLogModal}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-semibold text-white shadow transition"
          >
            <Plus className="h-3.5 w-3.5" />
            + Log Transaction
          </button>
        </div>
      </div>

      {/* Ledger Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/60 text-slate-400 uppercase tracking-wider font-semibold">
              <th className="py-3 px-4">Date</th>
              <th className="py-3 px-4">Type</th>
              <th className="py-3 px-4">Counterparty / Description</th>
              <th className="py-3 px-4">Category</th>
              <th className="py-3 px-4">Account / Vault</th>
              <th className="py-3 px-4">Amount</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 text-slate-300">
            {loading ? (
              <tr>
                <td colSpan={8} className="py-10 text-center text-slate-500">
                  <div className="flex items-center justify-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
                    Loading financial ledger records...
                  </div>
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-10 text-center text-slate-500">
                  No transaction records match the applied criteria.
                </td>
              </tr>
            ) : (
              filtered.map((tx) => {
                const isPaid = tx.status === "paid";
                const isPending = tx.status === "pending";
                const isOverdue = tx.status === "overdue";

                return (
                  <tr key={tx.id} className="hover:bg-slate-850/40 transition">
                    <td className="py-3.5 px-4 font-mono text-slate-400 whitespace-nowrap">
                      {tx.transaction_date}
                    </td>

                    <td className="py-3.5 px-4 whitespace-nowrap">
                      {tx.type === "income" && (
                        <span className="inline-flex items-center gap-1 font-medium text-emerald-400">
                          <ArrowDownLeft className="h-3 w-3" /> Income
                        </span>
                      )}
                      {tx.type === "rent" && (
                        <span className="inline-flex items-center gap-1 font-medium text-teal-400">
                          <Home className="h-3 w-3" /> Property Rent
                        </span>
                      )}
                      {tx.type === "expense" && (
                        <span className="inline-flex items-center gap-1 font-medium text-rose-400">
                          <ArrowUpRight className="h-3 w-3" /> Expense
                        </span>
                      )}
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="font-medium text-white">{tx.counterparty_name}</div>
                      {tx.notes && (
                        <div className="text-[11px] text-slate-400 truncate max-w-xs" title={tx.notes}>
                          {tx.notes}
                        </div>
                      )}
                    </td>

                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <span className="rounded bg-slate-800/80 px-2 py-0.5 text-[11px] text-slate-300 border border-slate-700/60">
                        {tx.category}
                      </span>
                    </td>

                    <td className="py-3.5 px-4 text-slate-400 whitespace-nowrap">
                      {getAccountName(tx.account_id)}
                    </td>

                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <span
                        className={`font-mono font-bold ${
                          tx.type === "expense" ? "text-rose-400" : "text-emerald-400"
                        }`}
                      >
                        {tx.type === "expense" ? "-" : "+"}
                        {tx.currency}{" "}
                        {tx.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </span>
                      {tx.due_date && isPending && (
                        <div className="text-[10px] text-amber-400/80">Due: {tx.due_date}</div>
                      )}
                    </td>

                    <td className="py-3.5 px-4 whitespace-nowrap">
                      {isPaid && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400 border border-emerald-500/20">
                          <CheckCircle2 className="h-3 w-3" /> Paid
                        </span>
                      )}
                      {isPending && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-amber-400 border border-amber-500/20">
                          <Clock className="h-3 w-3" /> Pending
                        </span>
                      )}
                      {isOverdue && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-rose-400 border border-rose-500/20">
                          <AlertTriangle className="h-3 w-3" /> Overdue
                        </span>
                      )}
                    </td>

                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      {!isPaid && (
                        <button
                          onClick={() => handleMarkPaid(tx.id)}
                          disabled={updatingId === tx.id}
                          className="inline-flex items-center gap-1 rounded bg-emerald-600/90 hover:bg-emerald-600 px-2.5 py-1 text-[11px] font-medium text-white transition disabled:opacity-50"
                        >
                          <CheckCircle2 className="h-3 w-3" />
                          {updatingId === tx.id ? "Saving..." : "Mark Paid"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="p-3 border-t border-slate-800 bg-slate-900/40 text-[11px] text-slate-500 flex justify-between items-center">
        <span>Showing {filtered.length} of {transactions.length} total ledger records</span>
        <span className="font-mono">Auto-reconciliation active</span>
      </div>
    </div>
  );
}
