import json

from app.llm import portal


def test_portal_provider_json_is_parsed_without_changing_model_metadata(monkeypatch):
    monkeypatch.setattr(
        portal.settings,
        "portal_llm_providers_json",
        json.dumps(
            [
                {
                    "name": "Portal",
                    "base_url": "https://portal.example/v1/",
                    "api_key": "secret",
                    "models": [{"name": "text", "vision": False}, {"name": "vision", "vision": True}],
                }
            ]
        ),
    )

    providers = portal.get_portal_providers()
    assert len(providers) == 1
    assert providers[0].base_url == "https://portal.example/v1"
    assert [model.name for model in providers[0].models] == ["text", "vision"]
    assert providers[0].models[1].supports_vision is True
    assert providers[0].api_key == "secret"


def test_invalid_portal_json_is_ignored(monkeypatch):
    monkeypatch.setattr(portal.settings, "portal_llm_providers_json", "not-json")
    assert portal.get_portal_providers() == ()
