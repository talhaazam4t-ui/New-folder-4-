"""Bounded BaseAgent Contract (Section 10.1 & Non-Negotiable Rule #5).

Every agent in Talox Tech Stream MUST inherit from `BaseAgent` and operate within:
1. Explicit `allowed_tools` whitelist (raises `PermissionDeniedError` on unauthorized tool access).
2. Strict `max_steps` and `timeout_seconds` bounds (no unbounded loops).
3. Pre-execution `budget_manager` quota and circuit-breaker verification.
4. Prompt sanitization via `route_and_execute_ai_task`.
"""

import asyncio
import uuid
from typing import Any, Dict, Optional, Set

from app.automation.budget_manager import budget_manager
from app.core.exceptions import PermissionDeniedError, TaloxException
from app.core.logging import logger
from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.schemas.agent import AgentStageResult


class BaseAgent:
    """Abstract bounded AI agent with explicit tool permissions and step limits."""

    name: str = "base_agent"
    role: str = "General Assistant"
    category: str = "core"
    description: str = "Bounded base agent contract"
    version: str = "1.0.0"
    default_task_type: str = "simple_support"
    allowed_tools: Set[str] = {"read_context"}
    max_steps: int = 4
    timeout_seconds: int = 30

    def verify_tool_permission(self, tool_name: str) -> None:
        """Verify that this agent is explicitly permitted to invoke `tool_name`.

        Raises:
            PermissionDeniedError: If `tool_name` is not in `self.allowed_tools`.
        """
        if tool_name not in self.allowed_tools:
            logger.warning(
                "Blocked unauthorized agent tool invocation",
                agent_name=self.name,
                requested_tool=tool_name,
                allowed_tools=list(self.allowed_tools),
            )
            raise PermissionDeniedError(
                f"Agent '{self.name}' is not permitted to invoke tool '{tool_name}'. "
                f"Allowed tools: {sorted(self.allowed_tools)}"
            )

    def build_prompt(self, objective: str, context_data: Optional[Dict[str, Any]] = None) -> str:
        """Construct the bounded system + objective prompt for this agent."""
        ctx_str = f"\nContext from previous stages: {context_data}" if context_data else ""
        return (
            f"Role: {self.role} ({self.name})\n"
            f"Authorized Capabilities: {', '.join(sorted(self.allowed_tools))}\n"
            f"Objective: {objective}{ctx_str}\n\n"
            f"Provide a clear, concise, actionable executive response in plain text/Markdown bullet points. "
            f"Do NOT emit XML <tool_call> tags or raw JSON function calls."
        )

    async def execute_step(
        self,
        tenant_id: uuid.UUID,
        objective: str,
        context_data: Optional[Dict[str, Any]] = None,
        requested_tool: Optional[str] = None,
    ) -> AgentStageResult:
        """Execute a single bounded reasoning or action step with timeout and budget enforcement."""
        if requested_tool:
            self.verify_tool_permission(requested_tool)

        budget_manager.check_execution_eligibility(str(tenant_id), estimated_tokens=500)
        prompt = self.build_prompt(objective, context_data)
        system_instruction = (
            f"You are {self.role} ({self.name}) inside the Talox Tech Stream SaaS platform. "
            "Respond directly with clear, concise, actionable business analysis in plain text or Markdown bullet points. "
            "Never output <tool_call>, <think>, XML tags, or raw function-call syntax."
        )

        ai_result = await asyncio.wait_for(
            route_and_execute_ai_task(
                task_type=self.default_task_type,
                prompt=prompt,
                tenant_id=str(tenant_id),
                system_instruction=system_instruction,
            ),
            timeout=self.timeout_seconds,
        )

        if not ai_result.success:
            err_msg = ai_result.error_message or ai_result.content
            budget_manager.record_failure(str(tenant_id), err_msg)
            raise TaloxException(
                message=f"Agent '{self.name}' AI call failed: {err_msg}",
                code="AI_PROVIDER_ERROR",
                status_code=502,
            )

        return AgentStageResult(
            agent_name=self.name,
            role=self.role,
            model=ai_result.model,
            output=ai_result.content,
            tokens_used=ai_result.total_tokens,
            estimated_cost=ai_result.estimated_cost,
        )
