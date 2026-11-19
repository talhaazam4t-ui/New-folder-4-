"""Centralized AI Provider Integration & Smart Model Router (DeepSeek API Only).

Exclusively uses DeepSeek API (https://api.deepseek.com) as the unified AI provider.
Implements smart task-based model routing:
- Fast / Cost-Effective Tier: "deepseek-chat" (DeepSeek-V3) for structured tasks,
  function calling, JSON mode, and high-frequency workloads (e.g. whatsapp_reply,
  simple_support, transaction_extraction, classification, quick_summary).
- Reasoning / Deep Analysis Tier: "deepseek-reasoner" (DeepSeek-R1) for complex reasoning
  (e.g., complex_planning, financial_audit, marketing_campaign_strategy, code_generation,
  deep_research, reviewer_validation).

Integrates:
1. Prompt sanitization (PII and financial credential redaction).
2. Exact token counting & cost estimation based on DeepSeek official pricing.
3. Offline / mock fallback when running without live API keys.
"""

import os
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
    reasoning_content: Optional[str] = None
    tokens_prompt: int = 0
    tokens_completion: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    is_mock: bool = False
    error_message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


# Official DeepSeek Pricing per 1,000 tokens (USD)
# deepseek-chat: $0.14 / 1M input ($0.00014/1k), $0.28 / 1M output ($0.00028/1k)
# deepseek-reasoner: $0.55 / 1M input ($0.00055/1k), $2.19 / 1M output ($0.00219/1k)
MODEL_PRICING = {
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
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
    """Smart model selection based on task complexity using DeepSeek model tiers."""
    if task_type in FAST_TIER_TASKS:
        return settings.ai_default_fast_model
    elif task_type in REASONING_TIER_TASKS:
        return settings.ai_default_reasoning_model
    # Default to fast model (deepseek-chat) for cost-optimization unless explicitly complex
    return settings.ai_default_fast_model


async def route_and_execute_ai_task(
    task_type: str,
    prompt: str,
    tenant_id: Optional[str] = None,
    system_instruction: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
) -> AIExecutionResult:
    """Sanitize, route, and execute an AI task via DeepSeek API (or mock fallback)."""
    # 1. Sanitize prompt for data privacy & compliance
    clean_prompt = sanitize_ai_prompt(prompt)
    clean_system = sanitize_ai_prompt(system_instruction or "You are an AI assistant in Talox Tech Stream.")

    # 2. Select target model
    target_model = select_model_for_task(task_type)
    resolved_api_key = (
        settings.deepseek_api_key
        or os.environ.get("DEEPSEEK_API_KEY")
        or settings.ai_api_key
        or ""
    ).strip()

    is_live_key_present = bool(
        resolved_api_key
        and resolved_api_key not in ("mock", "your-openrouter-api-key", "your-deepseek-api-key")
    )

    logger.info(
        "Routing AI task to DeepSeek",
        task_type=task_type,
        model=target_model,
        tenant_id=tenant_id,
        is_live_key_present=is_live_key_present,
    )

    # 3. Fallback to mock adapter if no live API key is set or mock mode is requested
    if settings.ai_provider == "mock" or not is_live_key_present:
        return _execute_mock_ai_task(task_type, target_model, clean_prompt)

    # 4. Live DeepSeek Execution via HTTP
    headers = {
        "Authorization": f"Bearer {resolved_api_key}",
        "Content-Type": "application/json",
    }

    # deepseek-reasoner counts chain-of-thought reasoning tokens toward max_tokens
    effective_max_tokens = max(max_tokens, 4096) if "reasoner" in target_model else max_tokens

    payload: Dict[str, Any] = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": clean_system},
            {"role": "user", "content": clean_prompt},
        ],
        "max_tokens": effective_max_tokens,
    }

    # deepseek-chat supports temperature customization
    if target_model == "deepseek-chat":
        payload["temperature"] = temperature

    try:
        base_url = settings.deepseek_base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices") or []
            if not choices:
                raise ValueError("DeepSeek API returned an empty choices array")
            choice = choices[0]
            message_obj = choice.get("message") or {}
            content = (message_obj.get("content") or "").strip()
            reasoning_content = message_obj.get("reasoning_content")
            if not content and reasoning_content:
                content = reasoning_content

            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", len(clean_prompt) // 4)
            completion_tokens = usage.get("completion_tokens", len(content) // 4)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            # Accurate cost estimation from DeepSeek official rates
            pricing = MODEL_PRICING.get(target_model, MODEL_PRICING["deepseek-chat"])
            cost = (prompt_tokens / 1000 * pricing["input"]) + (completion_tokens / 1000 * pricing["output"])

            return AIExecutionResult(
                success=True,
                model=target_model,
                task_type=task_type,
                content=content,
                reasoning_content=reasoning_content,
                tokens_prompt=prompt_tokens,
                tokens_completion=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost=round(cost, 6),
                is_mock=False,
                raw_response=data,
            )

    except Exception as exc:
        logger.error(
            "DeepSeek API call failed",
            error=str(exc),
            task_type=task_type,
            model=target_model,
        )
        return AIExecutionResult(
            success=False,
            model=target_model,
            task_type=task_type,
            content=f"[AI Service Error: {str(exc)}]",
            is_mock=False,
            error_message=str(exc),
        )


def _execute_mock_ai_task(task_type: str, model: str, prompt: str) -> AIExecutionResult:
    """Deterministic mock responses for offline development and test suites."""
    prompt_tokens = max(10, len(prompt) // 4)

    if "whatsapp" in task_type:
        mock_content = "Thank you for contacting us. Your message has been received and recorded."
    elif "sales" in task_type or "chatbot" in task_type:
        mock_content = (
            "Welcome to Talox Tech Stream! We provide Done-For-You Managed AI Automation across 27 industries "
            "(including Clinics & Hospitals, Dental Clinics, Financing, Real Estate, and E-Commerce). "
            "Our packages range from Starter ($99/mo) to Growth ($249/mo) and Enterprise ($499/mo). "
            "You can claim your package immediately or message our live team on WhatsApp at +92 339 8701000."
        )
    elif "transaction" in task_type:
        mock_content = '{"amount": 50000, "currency": "PKR", "type": "rent", "confirmed": true}'
    elif "planning" in task_type or "audit" in task_type:
        mock_content = f"Comprehensive Plan for {task_type}: 1. Review requirements. 2. Verify budget. 3. Execute approved steps."
    else:
        mock_content = f"Mock AI completion for task '{task_type}' using model '{model}'."

    completion_tokens = max(15, len(mock_content) // 4)
    total_tokens = prompt_tokens + completion_tokens

    pricing = MODEL_PRICING.get(model, MODEL_PRICING["deepseek-chat"])
    cost = (prompt_tokens / 1000 * pricing["input"]) + (completion_tokens / 1000 * pricing["output"])

    return AIExecutionResult(
        success=True,
        model=model,
        task_type=task_type,
        content=mock_content,
        reasoning_content="Mock reasoning chain verified." if model == "deepseek-reasoner" else None,
        tokens_prompt=prompt_tokens,
        tokens_completion=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost=round(cost, 6),
        is_mock=True,
    )
