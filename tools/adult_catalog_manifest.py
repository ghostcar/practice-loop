"""Lint and preview proposed adult activity manifests without database writes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "adult-activity/v1alpha1"
ALLOWED_RISKS = {"low", "elevated"}
FOUNDATION_KINDS = {"preparation", "checkin", "aftercare"}


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        manifest = json.load(source)
    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be an object")
    return manifest


def lint_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if manifest.get("import_allowed") is not False:
        errors.append("proposal manifest must set import_allowed=false")

    cards = manifest.get("cards")
    if not isinstance(cards, list) or not cards:
        return [*errors, "cards must be a non-empty array"]

    slugs: set[str] = set()
    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        if not isinstance(card, dict):
            errors.append(f"{prefix} must be an object")
            continue
        slug = card.get("slug")
        if not isinstance(slug, str) or not slug:
            errors.append(f"{prefix}.slug must be non-empty")
        elif slug in slugs:
            errors.append(f"{prefix}.slug is duplicated: {slug}")
        else:
            slugs.add(slug)

        for locale in ("ru", "en"):
            for field in ("title", "summary"):
                value = card.get(field, {}).get(locale)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{prefix}.{field}.{locale} must be non-empty")

        eligibility = card.get("eligibility", {})
        for flag in ("adult_only", "explicit_opt_in_required", "session_checkin_required"):
            if eligibility.get(flag) is not True:
                errors.append(f"{prefix}.eligibility.{flag} must be true")

        risk = card.get("risk", {})
        if risk.get("level") not in ALLOWED_RISKS:
            errors.append(f"{prefix}.risk.level must be low or elevated")
        if risk.get("level") == "elevated" and risk.get("per_session_confirmation") is not True:
            errors.append(f"{prefix} elevated risk requires per_session_confirmation=true")

        safety = card.get("safety", {})
        if not safety.get("stop_conditions"):
            errors.append(f"{prefix}.safety.stop_conditions must be non-empty")
        evidence = card.get("evidence_policy", {})
        if evidence.get("media_required") is not False:
            errors.append(f"{prefix}.evidence_policy.media_required must be false")
        if (
            card.get("content_kind") in FOUNDATION_KINDS
            and card.get("gamification", {}).get("penalty_enabled") is not False
        ):
            errors.append(f"{prefix} foundation cards cannot enable penalties")

        for name, parameter in card.get("parameters", {}).items():
            if not isinstance(parameter, dict):
                errors.append(f"{prefix}.parameters.{name} must be an object")
                continue
            for required in ("type", "unit", "min", "max"):
                if required not in parameter:
                    errors.append(f"{prefix}.parameters.{name}.{required} is required")
            if (
                isinstance(parameter.get("min"), (int, float))
                and isinstance(parameter.get("max"), (int, float))
                and parameter["min"] > parameter["max"]
            ):
                errors.append(f"{prefix}.parameters.{name} has min > max")
    return errors


def preview(manifest: dict[str, Any]) -> str:
    cards = manifest["cards"]
    categories = Counter(card["category"] for card in cards)
    risks = Counter(card["risk"]["level"] for card in cards)
    lines = [
        f"schema={manifest['schema_version']}",
        f"status={manifest.get('manifest_status')}",
        f"import_allowed={manifest.get('import_allowed')}",
        f"cards={len(cards)}",
        "categories=" + ", ".join(f"{key}:{value}" for key, value in sorted(categories.items())),
        "risks=" + ", ".join(f"{key}:{value}" for key, value in sorted(risks.items())),
    ]
    lines.extend(f"- {card['slug']} [{card['status']}] {card['title']['ru']}" for card in cards)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors = lint_manifest(manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("MANIFEST_OK")
    if args.preview:
        print(preview(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
