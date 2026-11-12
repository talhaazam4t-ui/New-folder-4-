"""Planner Agent — Decomposes complex tenant objectives into bounded execution steps.
"""

from app.agents.base_agent import BaseAgent


class PlannerAgent(BaseAgent):
    name = "planner_agent"
    role = "Strategic Task Planner"
    category = "orchestration"
    description = "Decomposes business, marketing, and operational objectives into bounded, auditable steps."
    default_task_type = "complex_planning"
    allowed_tools = {"read_context", "decompose_objective", "estimate_budget"}
    max_steps = 3
    timeout_seconds = 30


planner_agent = PlannerAgent()
