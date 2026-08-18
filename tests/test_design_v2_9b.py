"""Tests for Step 9b — Active Timer + Tasks rebuild (DESIGN_V2 §8/§10).

Covers:
1. Active timer hero: serif countdown, honest mode label, device chip,
   started→end range with cap, safety stop prominent.
2. Draft sessions render settings without the countdown hero.
3. Tasks page: density toggle (compact/comfortable) renders.
4. New i18n keys exist in both locales.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.i18n.en import EN
from app.i18n.ru import RU

pytestmark = pytest.mark.anyio

I18N_KEYS_9B = [
    "locktimer_mode_duration",
    "locktimer_mode_infinite",
    "locktimer_cap",
    "tasks_density_label",
    "tasks_density_compact",
    "tasks_density_comfortable",
    "tasks_row_due",
]


def _render_session(**overrides):
    """Render session_detail.html directly with a fabricated session dict."""
    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(),
    )
    env.globals["t"] = EN
    env.globals["localtime"] = lambda v, fmt="%Y-%m-%d %H:%M": v.strftime(fmt) if v else ""

    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    session = {
        "id": str(uuid.uuid4()),
        "state": "active",
        "state_label": "Active",
        "duration_type": "duration_from_start",
        "timezone": "Europe/Moscow",
        "started_at": now,
        "effective_end_at": now + timedelta(hours=6),
        "max_end_at": now + timedelta(hours=6),
        "effective_end_ts": (now + timedelta(hours=6)).timestamp(),
        "remaining_seconds": 21600,
        "merge_gap_seconds": 300,
        "row_version": 3,
        "device_id": str(uuid.uuid4()),
    }
    session.update(overrides)

    ctx = {
        "t": EN,
        "csrf_token": "test",
        "session": session,
        "bound_device": {"name": "Steel Cage", "inventory_status": "in_use"},
        "devices": [],
        "slot_rules": [],
        "task_rules": [],
        "slot_occurrences": [],
        "task_occurrences": [],
        "proposals": [],
    }
    return env.get_template("locktimer/session_detail.html").render(**ctx)


class TestActiveTimerHero:
    def test_active_hero_renders_serif_countdown(self):
        html = _render_session()
        assert 'id="countdown-display"' in html
        assert "pl-display" in html
        assert "tabular-nums" in html

    def test_active_hero_honest_mode_label(self):
        html = _render_session(duration_type="infinite")
        assert "Infinite — until safety stop" in html
        html2 = _render_session(duration_type="duration_from_start")
        assert "Duration from start" in html2

    def test_active_hero_device_and_range(self):
        html = _render_session()
        assert "Steel Cage" in html
        assert "Locked On Since" in html  # t.locktimer_started
        assert "Unlock At" in html  # t.locktimer_ends

    def test_active_hero_shows_cap_when_different(self):
        now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
        html = _render_session(
            effective_end_at=now + timedelta(hours=4),
            max_end_at=now + timedelta(hours=8),
            effective_end_ts=(now + timedelta(hours=4)).timestamp(),
        )
        assert "cap" in html

    def test_active_hero_safety_stop_prominent(self):
        html = _render_session()
        # Safety stop form posts to the safety-stop endpoint
        assert "/safety-stop" in html
        assert "Safety Stop" in html

    def test_draft_has_no_countdown_hero(self):
        html = _render_session(state="draft", started_at=None, effective_end_at=None, remaining_seconds=None)
        assert 'id="countdown-display"' not in html
        # Draft keeps the settings form
        assert "Settings" in html


class TestTasksDensity:
    async def test_tasks_page_renders_density_toggle(self, auth_client):
        resp = await auth_client.get("/tasks/")
        assert resp.status_code == 200
        html = resp.text
        assert 'id="density-compact"' in html
        assert 'id="density-comfortable"' in html
        assert 'id="log-list"' in html


class TestI18n9b:
    def test_keys_in_both_locales(self):
        for key in I18N_KEYS_9B:
            assert key in EN, f"missing EN key: {key}"
            assert key in RU, f"missing RU key: {key}"
            assert EN[key].strip(), f"empty EN value: {key}"
            assert RU[key].strip(), f"empty RU value: {key}"
