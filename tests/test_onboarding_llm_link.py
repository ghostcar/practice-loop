"""Regression tests for onboarding links to user-owned LLM settings."""

from pathlib import Path


def test_onboarding_uses_user_llm_settings_route():
    """The onboarding CTA points to the platform-level settings route."""
    template = Path("app/templates/onboarding.html").read_text()

    assert 'href="/llm-configs/"' in template
    assert 'href="/llm/configs"' not in template


def test_application_sources_have_no_stale_llm_config_path():
    """No rendered application source should link to the retired path."""
    roots = (Path("app/templates"), Path("app/services"), Path("app/api"))
    stale_path = "/llm/configs"

    matches = [
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".html", ".py"} and stale_path in path.read_text()
    ]

    assert matches == []
