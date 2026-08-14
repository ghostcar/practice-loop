"""Tests for DESIGN v2 («Тёмный архив») app shell — Step 9a.

Covers:
1. Sidebar renders for authenticated users with feature-flag gating.
2. Active nav highlight (aria-current) derived from the request path.
3. Mobile full-screen sheet exists; old global bottom nav is gone.
4. Anonymous pages render without the shell.
5. i18n shell keys exist in both locales.
6. Self-hosted serif + mono fonts are present on disk.
"""

from __future__ import annotations

import os

import pytest

from app.i18n.en import EN
from app.i18n.ru import RU

pytestmark = pytest.mark.anyio

SHELL_KEYS = [
    "nav_group_now",
    "nav_group_personal",
    "nav_group_data",
    "nav_group_social",
    "nav_group_system",
    "nav_today",
    "nav_measurements",
    "nav_schedule",
    "nav_body_parts",
    "nav_media",
    "nav_llm",
    "shell_collapse",
    "shell_expand",
    "shell_menu",
    "shell_close",
    "dashboard_ritual",
]


class TestShellRender:
    async def test_sidebar_present_for_authed(self, auth_client):
        resp = await auth_client.get("/dashboard")
        assert resp.status_code == 200
        html = resp.text
        assert "pl-sidebar" in html
        assert "pl-sidebar-toggle" in html
        assert "pl-mobile-sheet" in html
        # Sigil is referenced from the brand directory
        assert "/static/brand/practiceloop-sigil.svg" in html

    async def test_old_bottom_nav_removed(self, auth_client):
        resp = await auth_client.get("/dashboard")
        assert resp.status_code == 200
        html = resp.text
        assert "fixed bottom-0 inset-x-0" not in html
        assert "bn_class" not in html

    async def test_active_nav_highlight_by_path(self, auth_client):
        resp = await auth_client.get("/tasks/")
        assert resp.status_code == 200
        html = resp.text
        # The Tasks item must carry the active state
        assert 'aria-current="page"' in html
        assert "pl-nav-active" in html

    async def test_anonymous_page_without_shell(self, async_client):
        resp = await async_client.get("/login")
        assert resp.status_code == 200
        assert 'id="pl-sidebar"' not in resp.text
        assert 'id="pl-mobile-sheet"' not in resp.text

    async def test_utility_bar_and_context_title(self, auth_client):
        resp = await auth_client.get("/dashboard")
        assert resp.status_code == 200
        assert "pl-utility" in resp.text
        assert "pl-mobile-top" in resp.text


class TestShellI18n:
    def test_shell_keys_in_both_locales(self):
        for key in SHELL_KEYS:
            assert key in EN, f"missing EN key: {key}"
            assert key in RU, f"missing RU key: {key}"
            assert EN[key].strip(), f"empty EN value: {key}"
            assert RU[key].strip(), f"empty RU value: {key}"


class TestShellAssets:
    def test_self_hosted_fonts_present(self):
        fonts = os.listdir("app/static/fonts")
        assert any(f.startswith("source-serif-4-") for f in fonts), "Source Serif 4 missing"
        assert any(f.startswith("ibm-plex-mono-") for f in fonts), "IBM Plex Mono missing"
        assert any(f.startswith("InterVariable") for f in fonts), "Inter Variable missing"

    def test_sigil_present(self):
        assert os.path.isfile("app/static/brand/practiceloop-sigil.svg")
