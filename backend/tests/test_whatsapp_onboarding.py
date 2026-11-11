import pytest
from app.integrations.whatsapp.onboarding import whatsapp_onboarding_adapter


@pytest.mark.asyncio
async def test_meta_embedded_signup_mock_flow():
    result = await whatsapp_onboarding_adapter.exchange_code_and_register_waba(
        tenant_id="tenant-whatsapp-001",
        oauth_code="AQDxyz12345mockcode",
    )
    assert result.success is True
    assert result.is_mock is True
    assert result.status == "connected"
    assert "waba_mock_" in result.waba_id
    assert "phone_mock_" in result.phone_number_id
    assert result.display_phone_number == "+92 300 1234567"
