"""Tests for REM §7.5 raw LLM response retention policy.

Verifies the helper `_resolve_raw_response` enforces:
- store_raw_response=True (default) → raw is kept with a TTL
- store_raw_response=False → raw is dropped (None) but usage remains
- empty raw → returns (None, None)
- TTL is set in the future and within sane range (e.g. ~30 days)
"""

from datetime import UTC, datetime, timedelta

from app.llm.pipeline import RAW_RESPONSE_TTL_DAYS, _resolve_raw_response
from app.models.llm_config import LLMProviderConfig


def _make_cfg(store_raw: bool = True) -> LLMProviderConfig:
    """Bare-bones config object — avoid DB/encryption concerns."""
    cfg = LLMProviderConfig(
        provider_name="test",
        api_base_url="https://x.invalid",
        model_name="m",
        store_raw_response=store_raw,
    )
    return cfg


def test_store_enabled_keeps_raw_with_ttl():
    cfg = _make_cfg(store_raw=True)
    raw = '{"entity_id":"e","entity_name":"n"}'
    stored, expires = _resolve_raw_response(cfg, raw)

    assert stored == raw
    assert expires is not None
    # TTL window: now < expires < now + TTL + small slack
    now = datetime.now(UTC)
    delta = expires - now
    assert timedelta(days=RAW_RESPONSE_TTL_DAYS - 1) <= delta <= timedelta(days=RAW_RESPONSE_TTL_DAYS + 1)


def test_store_disabled_drops_raw():
    cfg = _make_cfg(store_raw=False)
    raw = '{"entity_id":"e","entity_name":"n"}'
    stored, expires = _resolve_raw_response(cfg, raw)

    assert stored is None
    assert expires is None


def test_disabled_default_when_attr_missing():
    """Older configs loaded without store_raw_response shouldn't keep raw by mistake."""
    cfg = _make_cfg()
    # Force-remove the attribute to simulate pre-migration state.
    delattr(cfg, "store_raw_response")
    raw = "raw-payload"
    stored, expires = _resolve_raw_response(cfg, raw)
    # Spec default: when the field is absent we protect privacy — do NOT store.
    assert stored is None
    assert expires is None


def test_empty_raw_returns_none_pair():
    cfg = _make_cfg(store_raw=True)
    stored, expires = _resolve_raw_response(cfg, "")
    assert stored is None
    assert expires is None

    stored, expires = _resolve_raw_response(cfg, None)  # type: ignore[arg-type]
    assert stored is None
    assert expires is None


def test_ttl_constant_is_within_rem_window():
    """Sanity: keep TTL in line with REM §7.5 (debug for a while, then forget)."""
    assert 7 <= RAW_RESPONSE_TTL_DAYS <= 90
