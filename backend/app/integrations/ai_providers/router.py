"""Centralized AI Provider Integration & Smart Model Router.

Uses OpenRouter API as the unified AI gateway.
Implements smart task-based model routing:
- Fast / Cost-Effective Tier: "google/gemini-flash-1.5" or "openai/gpt-4o-mini" for simple tasks
  (e.g., whatsapp_reply, simple_support, extraction, classification).
- Reasoning / Deep Analysis Tier: "anthropic/claude-3.5-sonnet" for complex reasoning
  (e.g., planning, code_generation, financial_audit, campaign_strategy, deep_research).

Integrates:
1. Prompt sanitization (PII and financial credential redaction).
2. Cost & token estimation.
3. Offline / mock fallback when running without live API keys.
"""

from typing import Any, Dict, Optional

import httpx
from app.config import settings
from app.core.logging import logger
from app.core.security import sanitize_ai_prompt
from pydantic import BaseModel


class AIExecutionResult(BaseModel):
    """Standardized response schema for AI task execution."""
    success: bool
    model: str
    task_type: str
    content: str
    tokens_prompt: int = 0
    tokens_completion: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    is_mock: bool = False
    raw_response: Optional[Dict[str, Any]] = None


# Pricing estimates per 1,000 tokens (USD)
MODEL_PRICING = {
    "google/gemini-flash-1.5": {"input": 0.000075, "output": 0.0003},
    "openai/gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "anthropic/claude-3.5-sonnet": {"input": 0.003, "output": 0.015},
    "mock": {"input": 0.0, "output": 0.0},
}

# Task category to model mapping
FAST_TIER_TASKS = {
    "whatsapp_reply",
    "simple_support",
    "text_classification",
    "transaction_extraction",
    "quick_summary",
    "sentiment_analysis",
}

REASONING_TIER_TASKS = {
    "complex_planning",
    "financial_audit",
    "marketing_campaign_strategy",
    "code_generation",
    "deep_research",
    "reviewer_validation",
}


def select_model_for_task(task_type: str) -> str:
    """Smart model selection based on task complexity."""
    if task_type in FAST_TIER_TASKS:
        return settings.ai_default_fast_model
    elif task_type in REASONING_TIER_TASKS:
        return settings.ai_default_reasoning_model
    # Default to fast model for cost-optimization unless explicitly complex
    return settings.ai_default_fast_model


async def route_and_execute_ai_task(
    task_type: str,
    prompt: str,
    tenant_id: Optional[str] = None,
    system_instruction: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
) -> AIExecutionResult:
    """Sanitize, route, and execute an AI task via OpenRouter (or mock fallback)."""
    # 1. Sanitize prompt for data privacy & compliance
    clean_prompt = sanitize_ai_prompt(prompt)
    clean_system = sanitize_ai_prompt(system_instruction or "You are an AI assistant in Talox Tech Stream.")

    # 2. Select target model
    target_model = select_model_for_task(task_type)

    logger.info(
        "Routing AI task",
        task_type=task_type,
        model=target_model,
        tenant_id=tenant_id,
        is_live_key_present=bool(settings.ai_api_key and settings.ai_api_key != "your-openrouter-api-key")
    )

    # 3. Fallback to mock adapter if no live API key is set or mock mode is requested
    if (
        settings.ai_provider == "mock"
        or not settings.ai_api_key
        or settings.ai_api_key == "your-openrouter-api-key"
    ):
        return _execute_mock_ai_task(task_type, target_model, clean_prompt)

    # 4. Live OpenRouter Execution via HTTP/2
    headers = {
        "Authorization": f"Bearer {settings.ai_api_key}",
        "HTTP-Referer": settings.backend_url,
        "X-Title": settings.app_name,
        "Content-Type": "application/json",
    }

    payload = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": clean_system},
            {"role": "user", "content": clean_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", len(clean_prompt) // 4)
            completion_tokens = usage.get("completion_tokens", len(content) // 4)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            # Cost estimation
            pricing = MODEL_PRICING.get(target_model, MODEL_PRICING["google/gemini-flash-1.5"])
            cost = (prompt_tokens / 1000 * pricing["input"]) + (completion_tokens / 1000 * pricing["output"])

            return AIExecutionResult(
                success=True,
                model=target_model,
                task_type=task_type,
                content=content,
                tokens_prompt=prompt_tokens,
                tokens_completion=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost=round(cost, 6),
                is_mock=False,
                raw_response=data,
            )

    except Exception as exc:
        logger.error(
            "OpenRouter call failed, falling back to safe offline response",
            error=str(exc),
            task_type=task_type,
            model=target_model,
        )
        # Graceful fallback to mock response with error indicator
        mock_result = _execute_mock_ai_task(task_type, target_model, clean_prompt)
        mock_result.content = f"[AI Service Alert: {str(exc)}] {mock_result.content}"
        return mock_result


def _execute_mock_ai_task(task_type: str, model: str, prompt: str) -> AIExecutionResult:
    """Deterministic mock responses for offline development and test suites."""
    prompt_tokens = max(10, len(prompt) // 4)

    if "whatsapp" in task_type:
        mock_content = "Thank you for contacting us. Your message has been received and recorded."
    elif "transaction" in task_type:
        mock_content = '{"amount": 50000, "currency": "PKR", "type": "rent", "confirmed": true}'
    elif "planning" in task_type or "audit" in task_type:
        mock_content = f"Comprehensive Plan for {task_type}: 1. Review requirements. 2. Verify budget. 3. Execute approved steps."
    else:
        mock_content = f"Mock AI completion for task '{task_type}' using model '{model}'."

    completion_tokens = max(15, len(mock_content) // 4)
    total_tokens = prompt_tokens + completion_tokens

    pricing = MODEL_PRICING.get(model, {"input": 0.0001, "output": 0.0002})
    cost = (prompt_tokens / 1000 * pricing["input"]) + (completion_tokens / 1000 * pricing["output"])

    return AIExecutionResult(
        success=True,
        model=model,
        task_type=task_type,
        content=mock_content,
        tokens_prompt=prompt_tokens,
        tokens_completion=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost=round(cost, 6),
        is_mock=True,
    )
