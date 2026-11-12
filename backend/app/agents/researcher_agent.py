"""Researcher Agent — Gathers tenant ledger, CRM, and market intelligence context.
"""

from app.agents.base_agent import BaseAgent


class ResearcherAgent(BaseAgent):
    name = "researcher_agent"
    role = "Context & Market Researcher"
    category = "orchestration"
    description = "Retrieves tenant financial metrics, audience insights, and domain context."
    default_task_type = "deep_research"
    allowed_tools = {"read_context", "query_business_summary", "query_marketing_insights"}
    max_steps = 4
    timeout_seconds = 30


researcher_agent = ResearcherAgent()
