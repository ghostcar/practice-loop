import json

from app.llm import policy


def test_personal_llm_is_denied_by_default(monkeypatch):
    monkeypatch.setattr(policy.settings, "personal_llm_sections_json", "[]")
    assert not policy.is_personal_allowed("tasks")


def test_personal_llm_policy_allows_only_configured_sections(monkeypatch):
    monkeypatch.setattr(
        policy.settings,
        "personal_llm_sections_json",
        json.dumps(["tasks", "training"]),
    )
    assert policy.is_personal_allowed("tasks")
    assert policy.is_personal_allowed("training")
    assert not policy.is_personal_allowed("media")
