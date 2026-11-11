from app.core.security import sanitize_ai_prompt


def test_sanitize_credit_card():
    prompt = "Please charge customer card 4532-1234-5678-9012 for the rent payment."
    sanitized = sanitize_ai_prompt(prompt)
    assert "4532-1234-5678-9012" not in sanitized
    assert "[REDACTED_CARD]" in sanitized


def test_sanitize_cvv_and_password():
    prompt = "Credentials are password: SuperSecretP@ss123 and cvv: 894."
    sanitized = sanitize_ai_prompt(prompt)
    assert "SuperSecretP@ss123" not in sanitized
    assert "894" not in sanitized
    assert "[REDACTED_PASSWORD]" in sanitized
    assert "[REDACTED_CVV]" in sanitized


def test_sanitize_iban_and_id():
    prompt = "Transfer funds to IBAN PK36SCBL0000001123456701 for SSN 123-45-6789."
    sanitized = sanitize_ai_prompt(prompt)
    assert "PK36SCBL0000001123456701" not in sanitized
    assert "123-45-6789" not in sanitized
    assert "[REDACTED_IBAN]" in sanitized
    assert "[REDACTED_ID]" in sanitized


def test_sanitize_api_key():
    prompt = "Use authorization Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz."
    sanitized = sanitize_ai_prompt(prompt)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized
