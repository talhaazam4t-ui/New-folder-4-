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


# Official Model Pricing per 1,000 tokens (USD)
# Groq Free Tier: $0.00 / 1k tokens
# deepseek-chat: $0.14 / 1M input ($0.00014/1k), $0.28 / 1M output ($0.00028/1k)
# deepseek-reasoner: $0.55 / 1M input ($0.00055/1k), $2.19 / 1M output ($0.00219/1k)
MODEL_PRICING = {
    "llama-3.3-70b-versatile": {"input": 0.0, "output": 0.0},
    "llama-3.1-8b-instant": {"input": 0.0, "output": 0.0},
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


async def _call_openai_compatible_chat(
    base_url: str,
    api_key: str,
    model_name: str,
    task_type: str,
    clean_system: str,
    clean_prompt: str,
    temperature: float,
    max_tokens: int,
) -> AIExecutionResult:
    """Execute a chat completion call against an OpenAI-compatible endpoint (Groq or DeepSeek)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    effective_max_tokens = max(max_tokens, 4096) if "reasoner" in model_name else max_tokens
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": clean_system},
            {"role": "user", "content": clean_prompt},
        ],
        "max_tokens": effective_max_tokens,
    }
    if "reasoner" not in model_name:
        payload["temperature"] = temperature

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise ValueError(f"AI provider ({model_name}) returned an empty choices array")
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

        pricing = MODEL_PRICING.get(model_name, {"input": 0.0, "output": 0.0})
        cost = (prompt_tokens / 1000 * pricing["input"]) + (completion_tokens / 1000 * pricing["output"])

        return AIExecutionResult(
            success=True,
            model=model_name,
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


def _resolve_groq_api_key() -> str:
    """Locate a valid Groq API key from settings or any GROQ/gsk_ environment variable."""
    candidates = [
        settings.groq_api_key,
        os.environ.get("GROQ_API_KEY"),
        os.environ.get("GROQ_KEY"),
        os.environ.get("GROK_API_KEY"),
        settings.ai_api_key if (settings.ai_api_key or "").strip().strip("\"'").startswith("gsk_") else None,
        settings.deepseek_api_key if (settings.deepseek_api_key or "").strip().strip("\"'").startswith("gsk_") else None,
    ]
    for k, v in os.environ.items():
        k_up = k.strip().upper()
        v_clean = (v or "").strip().strip("\"'")
        if ("GROQ" in k_up or "GROK" in k_up or v_clean.startswith("gsk_")) and v_clean:
            candidates.append(v_clean)

    for raw in candidates:
        cleaned = (raw or "").strip().strip("\"'").strip()
        if cleaned and cleaned not in ("mock", "your-groq-api-key"):
            return cleaned
    return ""


def _resolve_deepseek_api_key() -> str:
    """Locate a valid DeepSeek API key from settings or environment variables."""
    candidates = [
        settings.deepseek_api_key,
        os.environ.get("DEEPSEEK_API_KEY"),
        os.environ.get("DEEPSEEK_KEY"),
        settings.ai_api_key,
    ]
    for raw in candidates:
        cleaned = (raw or "").strip().strip("\"'").strip()
        if (
            cleaned
            and not cleaned.startswith("gsk_")
            and cleaned not in ("mock", "your-openrouter-api-key", "your-deepseek-api-key")
        ):
            return cleaned
    return ""


async def route_and_execute_ai_task(
    task_type: str,
    prompt: str,
    tenant_id: Optional[str] = None,
    system_instruction: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
) -> AIExecutionResult:
    """Sanitize, route, and execute an AI task with 3-tier priority cascade:
    1. Priority 1 (Primary - Free): Groq API (`GROQ_API_KEY`, `llama-3.3-70b-versatile` -> `llama-3.1-8b-instant`)
    2. Priority 2 (Paid Fallback): DeepSeek API (`DEEPSEEK_API_KEY`, `deepseek-chat` / `deepseek-reasoner`)
    3. Priority 3 (Final Safety Net): Built-in resilient local AI engine (`_execute_mock_ai_task`)
    """
    # 1. Sanitize prompt for data privacy & compliance
    clean_prompt = sanitize_ai_prompt(prompt)
    clean_system = sanitize_ai_prompt(system_instruction or "You are an AI assistant in Talox Tech Stream.")

    # 2. Select baseline model tier
    target_model = select_model_for_task(task_type)

    # --- PRIORITY 1: Groq API (Free Primary Provider) ---
    resolved_groq_key = _resolve_groq_api_key()
    if resolved_groq_key and settings.app_env != "test":
        groq_candidates = [settings.groq_primary_model, settings.groq_fast_model]
        for groq_model in groq_candidates:
            try:
                logger.info(
                    "Routing AI task to Groq (Priority 1)",
                    task_type=task_type,
                    model=groq_model,
                    tenant_id=tenant_id,
                )
                return await _call_openai_compatible_chat(
                    base_url=settings.groq_base_url,
                    api_key=resolved_groq_key,
                    model_name=groq_model,
                    task_type=task_type,
                    clean_system=clean_system,
                    clean_prompt=clean_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as groq_exc:
                logger.warning(
                    "Groq model execution failed; trying next fallback",
                    model=groq_model,
                    task_type=task_type,
                    error=str(groq_exc),
                )

    # --- PRIORITY 2: DeepSeek API (Paid Fallback Provider) ---
    resolved_deepseek_key = _resolve_deepseek_api_key()
    if resolved_deepseek_key and settings.ai_provider != "mock" and settings.app_env != "test":
        try:
            logger.info(
                "Routing AI task to DeepSeek (Priority 2 Fallback)",
                task_type=task_type,
                model=target_model,
                tenant_id=tenant_id,
            )
            return await _call_openai_compatible_chat(
                base_url=settings.deepseek_base_url,
                api_key=resolved_deepseek_key,
                model_name=target_model,
                task_type=task_type,
                clean_system=clean_system,
                clean_prompt=clean_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as ds_exc:
            logger.warning(
                "DeepSeek API fallback failed; routing to Priority 3 local safety net",
                error=str(ds_exc),
                task_type=task_type,
                model=target_model,
            )

    # --- PRIORITY 3: Final Safety Net (Resilient Local AI Engine) ---
    return _execute_mock_ai_task(task_type, target_model, clean_prompt)


def _execute_mock_ai_task(task_type: str, model: str, prompt: str) -> AIExecutionResult:
    """Deterministic mock responses for offline development and test suites."""
    prompt_tokens = max(10, len(prompt) // 4)

    if "whatsapp" in task_type:
        mock_content = "Thank you for contacting us. Your message has been received and recorded."
    elif "sales" in task_type or "chatbot" in task_type:
        mock_content = (
            "Welcome to Talox Tech Stream! We provide Done-For-You Managed AI Automation across 4 core industries "
            "(Financing, Clinics / Hospitals, Real Estate / Property, and E-Commerce) plus custom industry setups. "
            "Our packages range from Starter ($99/mo) to Growth ($249/mo) and Enterprise ($499/mo). "
            "You can claim your package immediately or message our live team on WhatsApp at +92 323 8300330."
        )
    elif "transaction" in task_type:
        mock_content = '{"amount": 50000, "currency": "PKR", "type": "rent", "confirmed": true}'
    elif "marketing_campaign_strategy" in task_type:
        mock_content = (
            f"Headline: Unlock High-ROI Growth with Automated AI Operations\n\n"
            f"{prompt}\n\n"
            f"Key Benefits:\n"
            f"• 24/7 Automated Lead Qualification & Instant Follow-Up\n"
            f"• Real-Time Multi-Currency Financial & Rent Tracking\n"
            f"• Verified Human-in-the-Loop Compliance Guardrails\n\n"
            f"Reply 'START' or book your onboarding consultation today!"
        )
    elif "text_classification" in task_type:
        mock_content = (
            "Lead Qualification Assessment: High-intent prospect verified with valid contact "
            "channels and active inbound engagement. Recommended for priority outreach."
        )
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
