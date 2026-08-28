"""Regression tests for onboarding links to user-owned LLM settings."""

from pathlib import Path


def test_onboarding_uses_user_llm_settings_route():
    """The onboarding CTA points to the platform-level settings route."""
    template = Path("app/templates/onboarding.html").read_text()

    assert 'href="/llm-configs/"' in template
    assert 'href="/llm/configs"' not in template
