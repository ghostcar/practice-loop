"""Regression tests for onboarding links and CSP-safe interaction."""

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


def test_onboarding_uses_csp_safe_event_handlers():
    """Onboarding interactions must not rely on CSP-blocked inline handlers."""
    template = Path("app/templates/onboarding.html").read_text()

    assert "onclick=" not in template
    assert "onchange=" not in template
    assert "data-go-step=" in template
    assert "data-ai-mode=" in template
    assert "addEventListener('click'" in template
    assert "addEventListener('change'" in template


def test_onboarding_uses_localized_option_keys():
    """Mode and module labels are resolved through the active locale."""
    template = Path("app/templates/onboarding.html").read_text()
    service = Path("app/services/onboarding_service.py").read_text()

    assert "t.get(opt.label_key" in template
    assert "t.get(mod.label_key" in template
    assert '"onboard_ai_none_label"' in Path("app/i18n/en.py").read_text()
    assert '"onboard_ai_none_label"' in Path("app/i18n/ru.py").read_text()
    assert "_MODULE_LABEL_KEYS" in service
