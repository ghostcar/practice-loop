"""Tests for Step 9e — Social tone + customization/discretion (DESIGN_V2 §13/§16).

Covers:
1. Settings page renders and persists all preference groups (appearance,
   dashboard blocks, discretion).
2. Dashboard renders blocks in the stored order and hides disabled ones.
3. Discretion always → neutral nav labels, masked entity names, neutral
   favicon, html[data-discretion]; schedule window logic; quick toggle.
4. Accent sets and theme 'system' choice.
5. Media Vault blur class under discretion.
6. Social templates carry no legacy classes (cold blue-gray tone).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.activity_log import ActivityLog
from app.models.media import MediaAsset

pytestmark = pytest.mark.anyio


async def _save_prefs(client, db=None, **overrides):
    """POST the full settings form with defaults + overrides."""
    data = {
        "theme_choice": overrides.get("theme_choice", "dark"),
        "accent": overrides.get("accent", "ember"),
        "density": overrides.get("density", "comfortable"),
        "block_order": overrides.get("block_order", "header,stats,charts,summaries,xp,quick,today,timer"),
        "block_hidden": overrides.get("block_hidden", ""),
        "discretion_mode": overrides.get("discretion_mode", "off"),
        "discretion_start": overrides.get("discretion_start", "22:00"),
        "discretion_end": overrides.get("discretion_end", "07:00"),
        "blur": str(overrides.get("blur", 0)),
    }
    r = await client.post("/settings", data=data)
    assert r.status_code == 303
    if db is not None:
        # the test get_db override does not commit — flush so the row is visible
        await db.flush()
    return r


class TestSettingsPage:
    async def test_settings_page_renders_sections(self, auth_client):
        # Default tab (appearance)
        r = await auth_client.get("/settings")
        assert r.status_code == 200
        html = r.text
        assert "settings_title" in html or "Settings" in html
        assert 'name="theme_choice"' in html
        assert 'name="accent"' in html

        # Dashboard tab
        r2 = await auth_client.get("/settings?tab=dashboard")
        assert 'name="block_order"' in r2.text

        # Privacy tab
        r3 = await auth_client.get("/settings?tab=privacy")
        assert 'name="discretion_mode"' in r3.text

        # Security tab
        r4 = await auth_client.get("/settings?tab=security")
        assert 'action="/settings/password"' in r4.text

    async def test_save_settings_persists(self, db_session, auth_client, test_user):
        await _save_prefs(
            auth_client,
            db_session,
            theme_choice="system",
            accent="sage",
            density="compact",
            block_order="stats,header,today",
            block_hidden="quick,xp",
            discretion_mode="schedule",
            discretion_start="21:30",
            discretion_end="08:15",
            blur=2,
        )
        await db_session.refresh(test_user)
        prefs = test_user.prefs
        assert prefs["accent"] == "sage"
        assert prefs["density"] == "compact"
        assert prefs["theme_choice"] == "system"
        # sanitize appends any blocks missing from the stored order (keeps them visible)
        assert prefs["dash_blocks"]["order"][:3] == ["stats", "header", "today"]
        assert prefs["dash_blocks"]["hidden"] == ["quick", "xp"]
        assert prefs["discretion"]["mode"] == "schedule"
        assert prefs["discretion"]["start"] == "21:30"
        assert prefs["discretion"]["end"] == "08:15"
        assert prefs["blur"] == 2
        # legacy column stays in sync
        assert test_user.theme == "system"

    async def test_invalid_values_fall_back_to_defaults(self, db_session, auth_client, test_user):
        await _save_prefs(
            auth_client,
            db_session,
            accent="neon",
            density="huge",
            theme_choice="matrix",
            discretion_mode="sometimes",
            discretion_start="notatime",
            blur=9,
        )
        await db_session.refresh(test_user)
        prefs = test_user.prefs
        assert prefs["accent"] == "ember"
        assert prefs["density"] == "comfortable"
        assert prefs["theme_choice"] == "dark"
        assert prefs["discretion"]["mode"] == "off"
        assert prefs["discretion"]["start"] == "22:00"
        assert prefs["blur"] == 0


class TestDashboardBlocks:
    async def test_blocks_render_in_stored_order_and_hide(self, db_session, auth_client):
        # order: today before stats; hide charts, summaries, quick, xp
        await _save_prefs(
            auth_client,
            db_session,
            block_order="header,today,stats",
            block_hidden="charts,summaries,xp,quick",
        )
        r = await auth_client.get("/dashboard")
        assert r.status_code == 200
        html = r.text
        # hidden blocks absent (structural ids, not i18n text which is in page-i18n)
        assert 'id="dash-block-charts"' not in html
        assert 'id="dash-block-quick"' not in html
        assert 'id="dash-block-xp"' not in html
        assert 'id="dash-block-summaries"' not in html
        # order: today block renders before stats block
        assert html.index('id="dash-block-today"') < html.index('id="dash-block-stats"')
        assert html.index('id="dash-block-header"') < html.index('id="dash-block-today"')


class TestDiscretion:
    async def test_always_masks_nav_and_names(self, db_session, auth_client, test_user):
        import re

        def _html_tag(html: str) -> str:
            m = re.search(r"<html[^>]*>", html)
            return m.group(0) if m else ""

        now = datetime.now(UTC)
        db_session.add(
            ActivityLog(
                user_id=test_user.id,
                status="planned",
                scheduled_at=now,
                selected_entity_name="Secret Task",
            )
        )
        await db_session.flush()
        await _save_prefs(auth_client, db_session, discretion_mode="always")

        r = await auth_client.get("/dashboard")
        assert r.status_code == 200
        html = r.text
        assert 'data-discretion="on"' in _html_tag(html)
        assert "favicon-neutral.svg" in html
        # neutral nav label for tasks (sidebar item)
        assert re.search(r'pl-nav-label">[^<]*Items</span>', html) is not None
        # entity name masked
        assert "Secret Task" not in html
        assert "Item #1" in html

    async def test_schedule_window_active_and_inactive(self, db_session, auth_client):
        import re

        await _save_prefs(
            auth_client,
            db_session,
            discretion_mode="schedule",
            discretion_start="00:00",
            discretion_end="23:59",
        )
        r = await auth_client.get("/dashboard")
        tag = re.search(r"<html[^>]*>", r.text).group(0)
        assert 'data-discretion="on"' in tag

        await _save_prefs(
            auth_client,
            db_session,
            discretion_mode="schedule",
            discretion_start="12:00",
            discretion_end="12:00",
        )
        r = await auth_client.get("/dashboard")
        tag = re.search(r"<html[^>]*>", r.text).group(0)
        assert 'data-discretion="on"' not in tag

    async def test_quick_toggle_off_always(self, db_session, auth_client, test_user):
        r = await auth_client.post("/settings/discretion/toggle")
        assert r.status_code == 200
        assert r.json()["mode"] == "always"
        await db_session.flush()
        await db_session.refresh(test_user)
        assert test_user.prefs["discretion"]["mode"] == "always"

        r = await auth_client.post("/settings/discretion/toggle")
        assert r.json()["mode"] == "off"
        await db_session.flush()
        await db_session.refresh(test_user)
        assert test_user.prefs["discretion"]["mode"] == "off"


class TestAccentAndThemeSystem:
    async def test_accent_and_system_choice_render(self, db_session, auth_client, test_user):
        await _save_prefs(auth_client, db_session, accent="sage", theme_choice="system")
        await db_session.refresh(test_user)
        assert test_user.theme == "system"
        assert test_user.prefs["theme_choice"] == "system"

        r = await auth_client.get("/dashboard")
        assert r.status_code == 200
        assert 'data-accent="sage"' in r.text
        assert 'data-theme-choice="system"' in r.text
        # SSR fallback resolution for system → dark
        assert 'data-theme="dark"' in r.text

    async def test_accent_css_sets_present(self):
        with open("app/templates/base.html") as f:
            html = f.read()
        assert 'data-accent="sage"' in html
        assert 'data-accent="slate"' in html
        # contrast-verified values baked in
        assert "--accent:#5b7452" in html  # sage dark
        assert "--accent:#56758a" in html  # slate dark


class TestMediaBlur:
    async def test_media_vault_blur_class(self, db_session, auth_client, test_user):
        db_session.add(
            MediaAsset(
                owner_id=test_user.id,
                owner_type="general",
                state="staged",
                file_path="/uploads/media/test.jpg",
                mime_type="image/jpeg",
            )
        )
        await db_session.flush()
        await _save_prefs(auth_client, db_session, discretion_mode="always", blur=2)

        r = await auth_client.get("/media")
        assert r.status_code == 200
        assert "pl-blur-2" in r.text


class TestSocialTone:
    def test_social_templates_have_no_legacy_classes(self):
        import glob

        for path in sorted(glob.glob("app/templates/social/*.html")):
            with open(path) as f:
                html = f.read()
            for legacy in ("bg-white", "text-gray-", "border-gray-", "indigo-"):
                assert legacy not in html, f"{path} still contains {legacy!r}"
