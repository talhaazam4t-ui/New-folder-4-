"use client";

import React, { useEffect, useState } from "react";
import { FinancialAccount } from "./types";
import { X, DollarSign, Building2, Wallet } from "lucide-react";

interface LogTxModalProps {
  isOpen: boolean;
  onClose: () => void;
  accounts: FinancialAccount[];
  onSubmit: (data: any) => Promise<void>;
}

export function LogTransactionModal({ isOpen, onClose, accounts, onSubmit }: LogTxModalProps) {
  const [type, setType] = useState<"income" | "rent" | "expense">("income");
  const [category, setCategory] = useState("Client Retainer");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [accountId, setAccountId] = useState(accounts[0]?.id || "");
  const [status, setStatus] = useState<"paid" | "pending" | "overdue">("paid");
  const [counterparty, setCounterparty] = useState("");
  const [transactionDate, setTransactionDate] = useState(new Date().toISOString().split("T")[0]);
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && !accountId && accounts.length > 0) {
      setAccountId(accounts[0].id);
    }
  }, [isOpen, accounts, accountId]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || isNaN(Number(amount)) || !counterparty) return;

    setLoading(true);
    try {
      await onSubmit({
        type,
        category,
        amount: parseFloat(amount),
        currency,
        account_id: accountId || null,
        status,
        counterparty_name: counterparty,
        transaction_date: transactionDate || null,
        due_date: dueDate || null,
        notes: notes || null,
      });
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-lg rounded-2xl bg-[#131F2E] border border-slate-700/80 p-6 shadow-2xl text-slate-200">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <DollarSign className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Log Financial Record</h3>
              <p className="text-xs text-slate-400">Record income, expenses, or rent payments</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          {/* Type Selector */}
          <div>
            <label className="block font-medium text-slate-300 mb-1">Transaction Type</label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "Income", val: "income", color: "hover:border-emerald-500" },
                { label: "Property Rent", val: "rent", color: "hover:border-teal-500" },
                { label: "Expense", val: "expense", color: "hover:border-rose-500" },
              ].map((opt) => (
                <button
                  type="button"
                  key={opt.val}
                  onClick={() => {
                    setType(opt.val as any);
                    if (opt.val === "rent") setCategory("Property Rent");
                    else if (opt.val === "expense") setCategory("Software");
                    else setCategory("Client Retainer");
                  }}
                  className={`py-2 rounded-lg border font-semibold transition ${
                    type === opt.val
                      ? "bg-emerald-600 text-white border-emerald-500"
                      : "bg-slate-900 border-slate-700 text-slate-300"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Amount & Currency */}
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2">
              <label className="block font-medium text-slate-300 mb-1">Amount</label>
              <input
                type="number"
                step="0.01"
                required
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white font-mono font-bold focus:border-emerald-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-300 mb-1">Currency</label>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white font-mono focus:border-emerald-500 focus:outline-none"
              >
                <option value="USD">USD ($)</option>
                <option value="PKR">PKR (Rs)</option>
                <option value="EUR">EUR (€)</option>
                <option value="GBP">GBP (£)</option>
                <option value="AED">AED</option>
                <option value="SAR">SAR</option>
              </select>
            </div>
          </div>

          {/* Counterparty & Category */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Counterparty (Client / Vendor)</label>
              <input
                type="text"
                required
                placeholder="e.g. Apex Hospital, AWS, John Doe"
                value={counterparty}
                onChange={(e) => setCounterparty(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-300 mb-1">Category</label>
              <input
                type="text"
                required
                placeholder="e.g. Client Retainer, Software, Utilities"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Account / Vault & Status */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Deposit / Debit Vault</label>
              <select
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white focus:border-emerald-500 focus:outline-none"
              >
                <option value="">Unallocated</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.currency})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block font-medium text-slate-300 mb-1">Payment Status</label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as any)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white focus:border-emerald-500 focus:outline-none"
              >
                <option value="paid">Paid (Instant Reconciliation)</option>
                <option value="pending">Pending (Unpaid)</option>
                <option value="overdue">Overdue</option>
              </select>
            </div>
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Transaction Date</label>
              <input
                type="date"
                value={transactionDate}
                onChange={(e) => setTransactionDate(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-300 mb-1">Due Date (Optional)</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block font-medium text-slate-300 mb-1">Internal Notes</label>
            <input
              type="text"
              placeholder="e.g. Paid via IBFT ref #99281, Rent for November 2026"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white focus:border-emerald-500 focus:outline-none"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition disabled:opacity-50"
            >
              {loading ? "Reconciling..." : "Save Record"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface NewRentScheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: any) => Promise<void>;
}

export function NewRentScheduleModal({ isOpen, onClose, onSubmit }: NewRentScheduleModalProps) {
  const [propertyUnit, setPropertyUnit] = useState("");
  const [lesseeName, setLesseeName] = useState("");
  const [lesseeWhatsapp, setLesseeWhatsapp] = useState("");
  const [monthlyRent, setMonthlyRent] = useState("");
  const [currency, setCurrency] = useState("PKR");
  const [billingDay, setBillingDay] = useState(1);
  const [autoRemind, setAutoRemind] = useState(true);
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!propertyUnit || !lesseeName || !lesseeWhatsapp || !monthlyRent) return;

    setLoading(true);
    try {
      await onSubmit({
        property_unit: propertyUnit,
        lessee_name: lesseeName,
        lessee_whatsapp: lesseeWhatsapp,
        monthly_rent: parseFloat(monthlyRent),
        currency,
        billing_day: Number(billingDay),
        auto_remind_whatsapp: autoRemind,
        status: "active",
      });
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-md rounded-2xl bg-[#131F2E] border border-slate-700/80 p-6 shadow-2xl text-slate-200">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-teal-500/10 text-teal-400 border border-teal-500/20">
              <Building2 className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">New Property Lease Schedule</h3>
              <p className="text-xs text-slate-400">Configure recurring rent & WhatsApp alerts</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="block font-medium text-slate-300 mb-1">Property / Unit Name</label>
            <input
              type="text"
              required
              placeholder="e.g. Suite 401 - Tech Tower, Villa 12"
              value={propertyUnit}
              onChange={(e) => setPropertyUnit(e.target.value)}
              className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white focus:border-teal-500 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Lessee Full Name</label>
              <input
                type="text"
                required
                placeholder="e.g. Talha Azam"
                value={lesseeName}
                onChange={(e) => setLesseeName(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white focus:border-teal-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-300 mb-1">WhatsApp Number</label>
              <input
                type="text"
                required
                placeholder="e.g. 03238300330"
                value={lesseeWhatsapp}
                onChange={(e) => setLesseeWhatsapp(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white font-mono focus:border-teal-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2">
              <label className="block font-medium text-slate-300 mb-1">Monthly Rent</label>
              <input
                type="number"
                step="0.01"
                required
                placeholder="50000"
                value={monthlyRent}
                onChange={(e) => setMonthlyRent(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white font-mono font-bold focus:border-teal-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-300 mb-1">Currency</label>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white font-mono focus:border-teal-500 focus:outline-none"
              >
                <option value="PKR">PKR (Rs)</option>
                <option value="USD">USD ($)</option>
                <option value="AED">AED</option>
                <option value="SAR">SAR</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Billing Day of Month</label>
              <input
                type="number"
                min="1"
                max="31"
                value={billingDay}
                onChange={(e) => setBillingDay(parseInt(e.target.value) || 1)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white font-mono focus:border-teal-500 focus:outline-none"
              />
            </div>
            <div className="flex flex-col justify-end">
              <label className="flex items-center gap-2 cursor-pointer py-2">
                <input
                  type="checkbox"
                  checked={autoRemind}
                  onChange={(e) => setAutoRemind(e.target.checked)}
                  className="rounded bg-slate-900 border-slate-700 text-teal-600 focus:ring-0"
                />
                <span className="text-[11px] text-slate-300">Auto WhatsApp Reminder</span>
              </label>
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 text-white font-semibold transition disabled:opacity-50"
            >
              {loading ? "Creating..." : "Create Lease"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface NewAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: any) => Promise<void>;
}

export function NewAccountModal({ isOpen, onClose, onSubmit }: NewAccountModalProps) {
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [initialBalance, setInitialBalance] = useState("0");
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name) return;

    setLoading(true);
    try {
      await onSubmit({
        name,
        currency,
        current_balance: parseFloat(initialBalance) || 0,
      });
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-sm rounded-2xl bg-[#131F2E] border border-slate-700/80 p-6 shadow-2xl text-slate-200">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Wallet className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Add Financial Vault</h3>
              <p className="text-xs text-slate-400">Bank, Cash, NayaPay, Stripe</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="block font-medium text-slate-300 mb-1">Account / Vault Name</label>
            <input
              type="text"
              required
              placeholder="e.g. Meezan Bank, Petty Cash, NayaPay"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white focus:border-emerald-500 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Currency</label>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white font-mono focus:border-emerald-500 focus:outline-none"
              >
                <option value="USD">USD ($)</option>
                <option value="PKR">PKR (Rs)</option>
                <option value="EUR">EUR (€)</option>
                <option value="GBP">GBP (£)</option>
                <option value="AED">AED</option>
                <option value="SAR">SAR</option>
              </select>
            </div>
            <div>
              <label className="block font-medium text-slate-300 mb-1">Starting Balance</label>
              <input
                type="number"
                step="0.01"
                placeholder="0.00"
                value={initialBalance}
                onChange={(e) => setInitialBalance(e.target.value)}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-white font-mono focus:border-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition disabled:opacity-50"
            >
              {loading ? "Saving..." : "Create Vault"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
