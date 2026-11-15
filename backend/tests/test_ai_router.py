import pytest
from app.integrations.ai_providers.router import (
    route_and_execute_ai_task,
    select_model_for_task,
)


def test_model_selection_tiers():
    # Fast / Cost-Effective Tier (DeepSeek-V3)
    assert select_model_for_task("whatsapp_reply") == "deepseek-chat"
    assert select_model_for_task("simple_support") == "deepseek-chat"
    assert select_model_for_task("transaction_extraction") == "deepseek-chat"

    # Reasoning / Deep Analysis Tier (DeepSeek-R1)
    assert select_model_for_task("complex_planning") == "deepseek-reasoner"
    assert select_model_for_task("financial_audit") == "deepseek-reasoner"
    assert select_model_for_task("code_generation") == "deepseek-reasoner"


@pytest.mark.asyncio
async def test_route_and_execute_mock_mode():
    result = await route_and_execute_ai_task(
        task_type="whatsapp_reply",
        prompt="Hi, I want to inquire about renting apartment 4B. My card is 4532-1111-2222-3333.",
        tenant_id="tenant-test-123",
    )
    assert result.success is True
    assert result.is_mock is True
    assert result.model == "deepseek-chat"
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
    assert result.model == "deepseek-reasoner"
    assert "plan" in result.content.lower()
