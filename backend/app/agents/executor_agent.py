"""Executor Agent — Executes bounded tasks using explicitly permitted domain tools.
"""

from app.agents.base_agent import BaseAgent


class ExecutorAgent(BaseAgent):
    name = "executor_agent"
    role = "Bounded Task Executor"
    category = "orchestration"
    description = "Executes approved workflow steps, drafts communications, and prepares structured outputs."
    default_task_type = "simple_support"
    allowed_tools = {
        "read_context",
        "draft_whatsapp_reply",
        "create_business_draft",
        "create_campaign_draft",
        "qualify_lead",
    }
    max_steps = 5
    timeout_seconds = 30


executor_agent = ExecutorAgent()
