import pytest
from app.integrations.ai_providers.router import (
    route_and_execute_ai_task,
    select_model_for_task,
)


def test_model_selection_tiers():
    # Fast / Cost-Effective Tier
    assert select_model_for_task("whatsapp_reply") == "google/gemini-flash-1.5"
    assert select_model_for_task("simple_support") == "google/gemini-flash-1.5"
    assert select_model_for_task("transaction_extraction") == "google/gemini-flash-1.5"

    # Reasoning / Deep Analysis Tier
    assert select_model_for_task("complex_planning") == "anthropic/claude-3.5-sonnet"
    assert select_model_for_task("financial_audit") == "anthropic/claude-3.5-sonnet"
    assert select_model_for_task("code_generation") == "anthropic/claude-3.5-sonnet"


@pytest.mark.asyncio
async def test_route_and_execute_mock_mode():
    result = await route_and_execute_ai_task(
        task_type="whatsapp_reply",
        prompt="Hi, I want to inquire about renting apartment 4B. My card is 4532-1111-2222-3333.",
        tenant_id="tenant-test-123",
    )
    assert result.success is True
    assert result.is_mock is True
    assert result.model == "google/gemini-flash-1.5"
    assert result.total_tokens > 0
    assert result.estimated_cost >= 0.0
    assert "received" in result.content.lower()


@pytest.mark.asyncio
async def test_route_and_execute_reasoning_task():
    result = await route_and_execute_ai_task(
        task_type="complex_planning",
        prompt="Generate Q4 growth strategy for tenant.",
        tenant_id="tenant-test-456",
    )
    assert result.success is True
    assert result.model == "anthropic/claude-3.5-sonnet"
    assert "plan" in result.content.lower()
