"""Tests for memoryctl code_units — structural parser (stdlib-only)."""

from __future__ import annotations

from tools.memoryctl import code_units as cu

PY_SAMPLE = '''\
"""Module docstring about session slots."""
from fastapi import APIRouter

router = APIRouter()


class LockTimerService:
    """Service that opens and closes slots."""

    __tablename__ = "lock_sessions"

    def __init__(self, db):
        self.db = db

    async def open_slot(self, occurrence_id: str):
        """Open a slot occurrence."""
        return occurrence_id


@router.post("/slot-occurrences/{occurrence_id}/open")
async def api_open_slot(occurrence_id: str):
    """API route to open a slot."""
    return occurrence_id


def test_open_slot():
    assert True


def helper_not_a_test():
    return 1
'''


def test_python_module_unit():
    units = cu.parse_python("app/locktimer/services/session.py", PY_SAMPLE)
    kinds = {u.unit_kind for u in units}
    assert "module" in kinds


def test_python_class_and_model():
    units = cu.parse_python("app/locktimer/services/session.py", PY_SAMPLE)
    by_sym = {u.symbol: u for u in units}
    assert by_sym["LockTimerService"].unit_kind == "model"
    assert by_sym["LockTimerService.__init__"].unit_kind == "method"
    assert by_sym["LockTimerService.open_slot"].unit_kind == "method"


def test_route_detection():
    units = cu.parse_python("app/api/locktimer_commands.py", PY_SAMPLE)
    routes = [u for u in units if u.unit_kind == "route"]
    assert len(routes) == 1
    r = routes[0]
    assert "POST /slot-occurrences/{occurrence_id}/open" in r.signature
    assert r.symbol == "api_open_slot"


def test_test_and_function_kinds():
    units = cu.parse_python("tests/test_x.py", PY_SAMPLE)
    by_sym = {u.symbol: u for u in units}
    assert by_sym["test_open_slot"].unit_kind == "test"
    assert by_sym["helper_not_a_test"].unit_kind == "function"


def test_scope_derivation():
    assert cu.derive_scope("app/locktimer/services/session.py") == "locktimer/core"
    assert cu.derive_scope("app/platform/social/models.py") == "social"
    assert cu.derive_scope("app/llm/pipeline.py") == "llm"
    assert cu.derive_scope("alembic/versions/025_x.py") == "data/migrations"
    assert cu.derive_scope("tests/test_locktimer_services.py") == "locktimer/core"


def test_content_hash_stable_and_span_sensitive():
    u1 = cu._unit("app/x.py", "fn", 1, 2, "function", "python", "def fn()", "body")
    u2 = cu._unit("app/x.py", "fn", 1, 3, "function", "python", "def fn()", "body")
    assert u1.content_hash != u2.content_hash
    u3 = cu._unit("app/x.py", "fn", 1, 2, "function", "python", "def fn()", "body")
    assert u1.content_hash == u3.content_hash
    assert u1.content_hash.startswith("sha256:")


def test_payload_roundtrip():
    u = cu._unit("app/x.py", "fn", 1, 2, "function", "python", "def fn()", "body")
    p = u.to_payload()
    assert p["path"] == "app/x.py"
    assert p["span"] == (1, 2)
    assert p["content_hash"] == u.content_hash


def test_alembic_revision():
    text = '''\
"""rev 025"""
revision: str = "025"
down_revision: str | None = "024"


def upgrade():
    op.create_table("lock_sessions")


def downgrade():
    op.drop_table("lock_sessions")
'''
    units = cu.parse_alembic("alembic/versions/025_lock.py", text)
    assert len(units) == 1
    assert units[0].unit_kind == "revision"
    assert units[0].symbol == "revision:025"
    assert "down_revision 024" in units[0].retrieval_text


def test_jinja_blocks():
    text = """\
{% block content %}
<form action="/x" method="post">
  <button>Go</button>
</form>
{% endblock %}
{% macro render_slot(o) %}{{ o }}{% endmacro %}
"""
    units = cu.parse_jinja("app/templates/locktimer/session_detail.html", text)
    syms = {u.symbol for u in units}
    assert "block:content" in syms
    assert "macro:render_slot" in syms
    assert any(u.unit_kind == "form" for u in units)


def test_js_handlers():
    text = """\
async function openSlot(id) { return fetch("/open"); }
const closeSlot = (id) => fetch("/close");
document.getElementById("x").addEventListener("click", () => {});
"""
    units = cu.parse_javascript("app/static/js/pages/dashboard.js", text)
    syms = {u.symbol for u in units}
    assert "openSlot" in syms
    assert "closeSlot" in syms
    assert any(u.symbol.startswith("handler:") for u in units)


def test_config_sections():
    text = """\
[tool.ruff]
line-length = 120

name = "practice-loop"
"""
    units = cu.parse_config("pyproject.toml", text)
    syms = {u.symbol for u in units}
    assert "section:tool.ruff" in syms


def test_extract_units_deterministic_order():
    root = cu.Path(__file__).resolve().parents[2]
    units = cu.extract_units(root)
    assert units == sorted(units, key=lambda u: (u.path, u.start_line, u.symbol))
    # real repo must yield a substantial number of structural units
    assert len(units) > 100
    kinds = {u.unit_kind for u in units}
    assert {"module", "function", "route", "model"} <= kinds
