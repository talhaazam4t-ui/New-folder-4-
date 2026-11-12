"""Specialized Business Agent — Financial Ledger & Rent Reconciliation Assistant.
"""

from app.agents.base_agent import BaseAgent


class FinanceTrackerAgent(BaseAgent):
    name = "finance_tracker_agent"
    role = "Financial Ledger & Rent Analyst"
    category = "business"
    description = (
        "Extracts unconfirmed rent/income/expense items from messages and generates financial summaries. "
        "Prohibited from altering or deleting confirmed financial transactions."
    )
    default_task_type = "financial_audit"
    allowed_tools = {"read_context", "query_business_summary", "extract_transaction_draft"}
    max_steps = 3
    timeout_seconds = 30


finance_tracker_agent = FinanceTrackerAgent()
