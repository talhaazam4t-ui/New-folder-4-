"""Reviewer Agent — Audits agent outputs for compliance, PII safety, and financial accuracy.
"""

from app.agents.base_agent import BaseAgent


class ReviewerAgent(BaseAgent):
    name = "reviewer_agent"
    role = "Quality & Compliance Reviewer"
    category = "orchestration"
    description = "Verifies outputs against tenant guardrails, financial integrity rules, and brand policy."
    default_task_type = "reviewer_validation"
    allowed_tools = {"read_context", "validate_output", "flag_for_human_approval"}
    max_steps = 2
    timeout_seconds = 20


reviewer_agent = ReviewerAgent()
