"use client";

import React from "react";
import { FinancialAccount } from "./types";
import {
  Landmark,
  Banknote,
  Smartphone,
  CreditCard,
  Plus,
  Coins,
} from "lucide-react";

interface AccountsGridProps {
  accounts: FinancialAccount[];
  loading: boolean;
  onOpenNewModal: () => void;
}

export function AccountsGrid({ accounts, loading, onOpenNewModal }: AccountsGridProps) {
  const getAccountIcon = (name: string) => {
    const lower = name.toLowerCase();
    if (lower.includes("cash") || lower.includes("petty")) return Banknote;
    if (lower.includes("nayapay") || lower.includes("sadapay") || lower.includes("easypaisa") || lower.includes("jazzcash"))
      return Smartphone;
    if (lower.includes("stripe") || lower.includes("card")) return CreditCard;
    return Landmark;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-white">Accounts & Settlement Vaults</h3>
          <p className="text-xs text-slate-400">
            Multi-currency financial custody accounts automatically updated via transactions
          </p>
        </div>
        <button
          onClick={onOpenNewModal}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition"
        >
          <Plus className="h-3.5 w-3.5" />
          + Add Account
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 rounded-xl bg-[#131F2E] border border-slate-800/80 p-4 animate-pulse" />
          ))
        ) : accounts.length === 0 ? (
          <div className="col-span-full rounded-xl bg-[#131F2E] border border-slate-800/80 p-8 text-center text-xs text-slate-400">
            No financial accounts (Bank, Cash, NayaPay, Stripe) configured. Click &quot;+ Add Account&quot; to begin.
          </div>
        ) : (
          accounts.map((acc) => {
            const Icon = getAccountIcon(acc.name);
            return (
              <div
                key={acc.id}
                className="rounded-xl bg-[#131F2E] border border-slate-800/80 p-4 shadow-sm hover:border-slate-700 transition"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-white">{acc.name}</div>
                      <div className="text-[10px] text-slate-400 uppercase font-mono">{acc.currency}</div>
                    </div>
                  </div>
                  <span className="rounded bg-slate-800/90 text-slate-400 text-[10px] font-mono px-1.5 py-0.5 border border-slate-700">
                    Vault
                  </span>
                </div>

                <div className="text-lg font-mono font-bold text-white">
                  {acc.currency}{" "}
                  {acc.current_balance.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </div>
                <div className="text-[10px] text-slate-500 mt-1 flex items-center gap-1">
                  <Coins className="h-3 w-3 text-emerald-500" />
                  <span>Real-time reconciled balance</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
