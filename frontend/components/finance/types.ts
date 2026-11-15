export interface FinancialAccount {
  id: string;
  tenant_id: string;
  name: string;
  currency: string;
  current_balance: number;
  created_at: string;
  updated_at: string;
}

export interface FinancialTransaction {
  id: string;
  tenant_id: string;
  account_id?: string | null;
  type: "income" | "expense" | "rent";
  category: string;
  amount: number;
  currency: string;
  status: "paid" | "pending" | "overdue";
  transaction_date: string;
  due_date?: string | null;
  counterparty_name: string;
  notes?: string | null;
  receipt_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RentSchedule {
  id: string;
  tenant_id: string;
  property_unit: string;
  lessee_name: string;
  lessee_whatsapp: string;
  monthly_rent: number;
  currency: string;
  billing_day: number;
  auto_remind_whatsapp: boolean;
  status: "active" | "vacant";
  created_at: string;
  updated_at: string;
}

export interface MonthlyChartPoint {
  month: string;
  income: number;
  expense: number;
  net: number;
}

export interface FinancialSummary {
  total_cash_balance: number;
  monthly_revenue: number;
  monthly_expenses: number;
  net_cash_flow: number;
  accounts_receivable: number;
  monthly_burn_rate: number;
  pending_rent_count: number;
  overdue_rent_count: number;
  currency: string;
  currency_balances: Record<string, number>;
  monthly_chart: MonthlyChartPoint[];
}
