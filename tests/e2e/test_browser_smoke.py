"""Browser E2E smoke test (audit P1-4).

Covers the core personal loop end-to-end in a real browser:
  1. register/login
  2. dashboard renders (stats + locktimer card when timer enabled)
  3. timer page renders

Runs only when Playwright + a browser binary are installed
(`pip install ".[e2e]" && playwright install chromium`). Skips otherwise so
the default unit-test env is unaffected.

Target URL from env:
  E2E_BASE_URL   (default http://localhost:8000)
  E2E_EMAIL      (default smoke-<uuid>@example.com — registers a fresh user)
  E2E_HEADLESS   (default 1)
"""

from __future__ import annotations

import os
import uuid

import pytest

playwright = pytest.importorskip("playwright.sync_api", reason="playwright not installed (dev extra 'e2e')")

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000").rstrip("/")
HEADLESS = os.environ.get("E2E_HEADLESS", "1") == "1"


def _fresh_email() -> str:
    return os.environ.get("E2E_EMAIL") or f"smoke-{uuid.uuid4().hex[:12]}@example.com"


def _register_and_login(page, email: str, password: str) -> None:
    """Register a fresh user and land on /dashboard, passing the consent gate.

    Current flow: register auto-logs-in and redirects to /onboarding (wizard for
    new users); onboarding can be skipped and leads to /consent/setup (module
    permissions) before /dashboard is available.
    """
    page.goto(f"{BASE_URL}/register")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url(
        lambda u: any(x in u for x in ("/dashboard", "/login", "/consent", "/onboarding")),
        timeout=20_000,
    )

    if "/onboarding" in page.url:
        # New-user wizard — skip it (module consents are granted on /consent/setup).
        # The skip button lives in the last wizard step and is display:hidden
        # until then, so submit the skip form directly (same as the button does
        # via the form= attribute; the hidden csrf_token input is included).
        page.locator("#skip-form").evaluate("(f) => f.submit()")
        page.wait_for_url(lambda u: "/dashboard" in u or "/consent" in u, timeout=20_000)

    if "/login" in page.url:
        # Registration redirected to login — sign in.
        page.fill('input[name="email"]', email)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_url(lambda u: "/dashboard" in u or "/consent" in u, timeout=20_000)

    if "/consent/setup" in page.url:
        # Consent gate: grant all required module permissions, then continue.
        # Scope locators to the consent form — the shell has locale-switcher
        # forms whose submit buttons precede it in DOM order.
        form = page.locator('form[action="/consent/setup"]')
        boxes = form.locator('input[name="consent_types"]')
        for i in range(boxes.count()):
            boxes.nth(i).check()
        form.locator('button[type="submit"]').click()
        page.wait_for_url(lambda u: "/dashboard" in u, timeout=20_000)

    assert "/dashboard" in page.url, f"expected dashboard, got {page.url}"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(headless=HEADLESS)
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    # Function-scoped on purpose: each test gets a fresh context (no session
    # cookies leaking between tests). Registration is CSRF-rejected for an
    # already-authenticated session (the register form carries no csrf_token
    # and CSRF is enforced only when access_token is present), so a shared
    # module-scoped page would make every test after the first fail.
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    pg = ctx.new_page()
    pg.set_default_timeout(15_000)
    console_errors: list[str] = []
    pg.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    pg._console_errors = console_errors  # type: ignore[attr-defined]
    yield pg
    ctx.close()


def test_full_personal_loop(page) -> None:
    email = _fresh_email()
    password = "Smoke-Pass-2026!"

    # ── Register + login (+ consent gate for fresh users) ───────────────
    _register_and_login(page, email, password)
    page.screenshot(path="/tmp/smoke_dashboard.png")

    # Desktop shell must render (DESIGN v2 sidebar) and the icon sprite must
    # load (no broken <use>).
    nav = page.locator("#pl-sidebar")
    assert nav.is_visible(), "desktop sidebar missing"

    # Dashboard page script must actually run (regression: head-included
    # dashboard.js used to no-op before DOM parse — no Chart instances).
    page.wait_for_timeout(2_000)
    chart_ok = page.evaluate("() => !!(window.Chart && Chart.getChart && Chart.getChart('activity-chart'))")
    assert chart_ok, "activity-chart has no Chart instance — dashboard.js dead"
    # Telegram linking card present and clickable (restored block).
    tg_btn = page.locator("#tg-link-btn")
    assert tg_btn.count() == 1, "tg-link-btn missing on dashboard"

    # ── Tasks page ──────────────────────────────────────────────────────
    page.goto(f"{BASE_URL}/tasks/")
    page.wait_for_load_state("networkidle")
    assert page.title()

    # ── Timer page (when enabled) ───────────────────────────────────────
    timer_link = page.locator("a[href='/locktimer']").first
    if timer_link.is_visible(timeout=3_000):
        timer_link.click()
        page.wait_for_url(lambda u: "/locktimer" in u, timeout=20_000)
        page.screenshot(path="/tmp/smoke_timer.png")
        # Timer page renders some heading.
        assert page.locator("h1").count() > 0 or page.locator("main").count() > 0

    # ── No console errors (except favicon 404s which are benign) ────────
    page.goto(f"{BASE_URL}/dashboard")
    page.wait_for_load_state("networkidle")
    real_errors = [e for e in page._console_errors if "favicon" not in e.lower()]  # type: ignore[attr-defined]
    assert not real_errors, f"console errors: {real_errors[:5]}"


def test_protocol_builder_duration_picker(page) -> None:
    """R10.5 regression: JS-added step rows must render the duration picker.

    The server-side macro renders fields, but rows created by the "Add step"
    button are generated in protocol_builder.js — those must include the five
    duration inputs + preset chips (regression: empty Duration section).
    """
    email = _fresh_email()
    password = "Smoke-Pass-2026!"

    _register_and_login(page, email, password)

    page.goto(f"{BASE_URL}/protocols/new")
    page.wait_for_load_state("networkidle")
    page.click("#add-step")
    page.wait_for_selector(".step-row .duration-picker", timeout=10_000)

    row = page.locator(".step-row").first
    # Five duration inputs with the step_0_* naming.
    for unit in ("months", "days", "hours", "minutes", "seconds"):
        assert row.locator(f'input[name="step_0_{unit}"]').count() == 1, f"missing step_0_{unit}"
    # Preset chips present and clickable: 15м -> 15 minutes, 0 h/months.
    row.locator('.dp-preset[data-seconds="900"]').click()
    minutes = row.locator('input[name="step_0_minutes"]').input_value()
    hours = row.locator('input[name="step_0_hours"]').input_value()
    assert minutes == "15", f"expected 15 minutes after 15м preset, got {minutes}"
    assert hours == "0", f"expected 0 hours, got {hours}"

    # No console errors (favicon 404s benign).
    real_errors = [e for e in page._console_errors if "favicon" not in e.lower()]  # type: ignore[attr-defined]
    assert not real_errors, f"console errors: {real_errors[:5]}"
