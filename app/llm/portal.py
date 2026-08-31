"""Environment-backed portal LLM provider configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class PortalModel:
    name: str
    supports_vision: bool = False


@dataclass(frozen=True)
class PortalProvider:
    name: str
    base_url: str
    api_key: str | None
    models: tuple[PortalModel, ...]
    supports_text: bool = True


def get_portal_providers() -> tuple[PortalProvider, ...]:
    """Parse and validate the env-backed portal provider pool.

    Invalid entries are ignored rather than breaking application startup; the
    admin can correct the secret configuration and restart the deployment.
    """
    try:
        raw = json.loads(settings.portal_llm_providers_json or "[]")
    except (TypeError, ValueError):
        return ()
    if not isinstance(raw, list):
        return ()

    providers: list[PortalProvider] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        base_url = str(item.get("base_url") or "").strip().rstrip("/")
        if not name or not base_url:
            continue
        models: list[PortalModel] = []
        for model in item.get("models", []):
            if isinstance(model, str) and model.strip():
                models.append(PortalModel(model.strip()))
            elif isinstance(model, dict) and str(model.get("name") or "").strip():
                models.append(
                    PortalModel(
                        name=str(model["name"]).strip(),
                        supports_vision=bool(model.get("vision", False)),
                    )
                )
        providers.append(
            PortalProvider(
                name=name,
                base_url=base_url,
                api_key=str(item.get("api_key") or "") or None,
                models=tuple(models),
                supports_text=bool(item.get("supports_text", True)),
            )
        )
    return tuple(providers)
