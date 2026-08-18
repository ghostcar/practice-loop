"""Lint and preview proposed adult activity manifests without database writes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "adult-activity/v1alpha1"
SOURCE_SCHEMA_VERSION = "adult-activity-source-inventory/v1alpha1"
EDITORIAL_SCHEMA_VERSION = "adult-activity-editorial-candidates/v1alpha1"
REVIEW_SCHEMA_VERSION = "adult-activity-editorial-review/v1alpha1"
INVENTORY_SCHEMA_VERSION = "adult-inventory-source/v1alpha1"
TAXONOMY_SCHEMA_VERSION = "adult-category-taxonomy/v1alpha1"
ADDITIONAL_TITLE_SCHEMA_VERSION = "adult-additional-title-source/v1alpha1"
ALLOWED_RISKS = {"low", "elevated"}
FOUNDATION_KINDS = {"preparation", "checkin", "aftercare"}
SOURCE_DISPOSITIONS = {"candidate", "manual_only", "needs_safe_rewrite", "research_only"}
REVIEW_OUTCOMES = {"promote_candidate", "manual_reference", "rewrite_required", "research_backlog"}


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


def lint_source_inventory(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != SOURCE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {SOURCE_SCHEMA_VERSION}")
    records = manifest.get("records")
    if not isinstance(records, list):
        return [*errors, "records must be an array"]
    expected = manifest.get("source_title_rows", 0) - manifest.get("ignored_template_rows", 0)
    if manifest.get("content_rows") != len(records) or len(records) != expected:
        errors.append(f"row count mismatch: expected={expected} records={len(records)}")
    ids: set[str] = set()
    lines: set[int] = set()
    for index, record in enumerate(records):
        prefix = f"records[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        source_id = record.get("source_id")
        source_line = record.get("source_line")
        if source_id in ids:
            errors.append(f"{prefix}.source_id is duplicated: {source_id}")
        ids.add(source_id)
        if source_line in lines:
            errors.append(f"{prefix}.source_line is duplicated: {source_line}")
        lines.add(source_line)
        if not isinstance(record.get("source_title"), str) or not record["source_title"].strip():
            errors.append(f"{prefix}.source_title must be non-empty")
        if record.get("disposition") not in SOURCE_DISPOSITIONS:
            errors.append(f"{prefix}.disposition is invalid")
        if record.get("retained") is not True:
            errors.append(f"{prefix}.retained must be true")
        if record.get("seed_ready") is not False:
            errors.append(f"{prefix}.seed_ready must remain false before editorial review")
        if not record.get("reason_codes"):
            errors.append(f"{prefix}.reason_codes must be non-empty")
    return errors


def preview_source_inventory(manifest: dict[str, Any]) -> str:
    records = manifest["records"]
    dispositions = Counter(record["disposition"] for record in records)
    areas = Counter(record["source_area"] for record in records)
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"policy={manifest.get('policy')}",
            f"records={len(records)}",
            "dispositions=" + ", ".join(f"{key}:{value}" for key, value in sorted(dispositions.items())),
            "areas=" + ", ".join(f"{key}:{value}" for key, value in sorted(areas.items())),
        ]
    )


def lint_editorial_candidates(manifest: dict[str, Any], known_source_ids: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != EDITORIAL_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EDITORIAL_SCHEMA_VERSION}")
    if manifest.get("import_allowed") is not False:
        errors.append("editorial candidates must set import_allowed=false")
    cards = manifest.get("cards")
    if not isinstance(cards, list) or not cards:
        return [*errors, "cards must be a non-empty array"]
    slugs: set[str] = set()
    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        slug = card.get("slug")
        if not isinstance(slug, str) or not slug:
            errors.append(f"{prefix}.slug must be non-empty")
        elif slug in slugs:
            errors.append(f"{prefix}.slug is duplicated: {slug}")
        slugs.add(slug)
        refs = card.get("source_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{prefix}.source_refs must be non-empty")
        elif known_source_ids is not None:
            unknown = sorted(set(refs) - known_source_ids)
            if unknown:
                errors.append(f"{prefix}.source_refs are unknown: {', '.join(unknown)}")
        for locale in ("ru", "en"):
            for field in ("title", "summary"):
                if not str(card.get(field, {}).get(locale, "")).strip():
                    errors.append(f"{prefix}.{field}.{locale} must be non-empty")
        if card.get("risk_level") not in ALLOWED_RISKS:
            errors.append(f"{prefix}.risk_level must be low or elevated")
        controls = card.get("required_controls")
        if not isinstance(controls, list) or not controls:
            errors.append(f"{prefix}.required_controls must be non-empty")
        if card.get("risk_level") == "elevated" and card.get("automation_allowed") is not False:
            errors.append(f"{prefix} elevated editorial candidate cannot enable automation")
        if card.get("category") == "sexual_connection":
            if card.get("automation_allowed") is not False:
                errors.append(f"{prefix} sexual_connection must remain manual-only")
            if not any("explicit" in control and "opt_in" in control for control in controls):
                errors.append(f"{prefix} sexual_connection requires an explicit opt-in control")
    return errors


def preview_editorial_candidates(manifest: dict[str, Any]) -> str:
    cards = manifest["cards"]
    categories = Counter(card["category"] for card in cards)
    risks = Counter(card["risk_level"] for card in cards)
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"status={manifest.get('manifest_status')}",
            f"import_allowed={manifest.get('import_allowed')}",
            f"cards={len(cards)}",
            "categories=" + ", ".join(f"{key}:{value}" for key, value in sorted(categories.items())),
            "risks=" + ", ".join(f"{key}:{value}" for key, value in sorted(risks.items())),
        ]
    )


def lint_editorial_review(manifest: dict[str, Any], known_source_ids: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != REVIEW_SCHEMA_VERSION:
        errors.append(f"schema_version must be {REVIEW_SCHEMA_VERSION}")
    if manifest.get("import_allowed") is not False:
        errors.append("editorial review must set import_allowed=false")
    records = manifest.get("records")
    if not isinstance(records, list):
        return [*errors, "records must be an array"]
    if len(records) != manifest.get("expected_records"):
        errors.append("records count must match expected_records")
    ids: set[str] = set()
    for index, record in enumerate(records):
        prefix = f"records[{index}]"
        source_id = record.get("source_id")
        if source_id in ids:
            errors.append(f"{prefix}.source_id is duplicated: {source_id}")
        ids.add(source_id)
        if known_source_ids is not None and source_id not in known_source_ids:
            errors.append(f"{prefix}.source_id is unknown: {source_id}")
        if record.get("review_outcome") not in REVIEW_OUTCOMES:
            errors.append(f"{prefix}.review_outcome is invalid")
        if record.get("retained") is not True:
            errors.append(f"{prefix}.retained must be true")
        if record.get("automation_allowed") is not False:
            errors.append(f"{prefix}.automation_allowed must be false in review")
        if not record.get("required_gates"):
            errors.append(f"{prefix}.required_gates must be non-empty")
        if not str(record.get("editorial_note", "")).strip():
            errors.append(f"{prefix}.editorial_note must be non-empty")
        if record.get("review_outcome") == "research_backlog":
            if record.get("user_discoverable_after_moderation") is not False:
                errors.append(f"{prefix} research backlog cannot be user-discoverable yet")
        elif record.get("user_discoverable_after_moderation") is not True:
            errors.append(f"{prefix} reviewed non-research record should remain discoverable after moderation")
        if record.get("review_outcome") in {"promote_candidate", "rewrite_required"} and not record.get(
            "derived_card_slug"
        ):
            errors.append(f"{prefix}.derived_card_slug is required for a derivative")
    return errors


def preview_editorial_review(manifest: dict[str, Any]) -> str:
    records = manifest["records"]
    outcomes = Counter(record["review_outcome"] for record in records)
    areas = Counter(record["source_area"] for record in records)
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"batch={manifest.get('review_batch')}",
            f"import_allowed={manifest.get('import_allowed')}",
            f"records={len(records)}",
            "outcomes=" + ", ".join(f"{key}:{value}" for key, value in sorted(outcomes.items())),
            "areas=" + ", ".join(f"{key}:{value}" for key, value in sorted(areas.items())),
        ]
    )


def lint_inventory_source(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {INVENTORY_SCHEMA_VERSION}")
    if manifest.get("import_allowed") is not False:
        errors.append("inventory source must set import_allowed=false")
    records = manifest.get("source_records")
    items = manifest.get("items")
    if not isinstance(records, list) or not isinstance(items, list):
        return [*errors, "source_records and items must be arrays"]
    if len(records) != manifest.get("source_record_count"):
        errors.append("source_record_count mismatch")
    if len(items) != manifest.get("normalized_item_count"):
        errors.append("normalized_item_count mismatch")
    source_ids = [record.get("source_id") for record in records]
    if len(source_ids) != len(set(source_ids)):
        errors.append("source IDs must be unique")
    if any(record.get("retained") is not True for record in records):
        errors.append("every source record must be retained")
    known_ids = set(source_ids)
    referenced_ids: set[str] = set()
    item_ids: set[str] = set()
    normalized_keys: set[str] = set()
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        item_id = item.get("item_id")
        key = item.get("normalized_key")
        if item_id in item_ids:
            errors.append(f"{prefix}.item_id is duplicated")
        item_ids.add(item_id)
        if key in normalized_keys:
            errors.append(f"{prefix}.normalized_key is duplicated")
        normalized_keys.add(key)
        refs = set(item.get("source_refs", []))
        if not refs:
            errors.append(f"{prefix}.source_refs must be non-empty")
        if refs - known_ids:
            errors.append(f"{prefix}.source_refs contains unknown IDs")
        referenced_ids.update(refs)
        if item.get("seed_ready") is not False:
            errors.append(f"{prefix}.seed_ready must remain false")
    if referenced_ids != known_ids:
        errors.append("every source record must be referenced by a normalized item")
    return errors


def preview_inventory_source(manifest: dict[str, Any]) -> str:
    families = Counter(item["family"] for item in manifest["items"])
    routing = Counter(item["risk_routing"] for item in manifest["items"])
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"import_allowed={manifest.get('import_allowed')}",
            f"source_records={len(manifest['source_records'])}",
            f"normalized_items={len(manifest['items'])}",
            "families=" + ", ".join(f"{key}:{value}" for key, value in sorted(families.items())),
            "risk_routing=" + ", ".join(f"{key}:{value}" for key, value in sorted(routing.items())),
        ]
    )


def lint_category_taxonomy(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != TAXONOMY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {TAXONOMY_SCHEMA_VERSION}")
    if manifest.get("import_allowed") is not False:
        errors.append("taxonomy proposal must set import_allowed=false")
    categories = manifest.get("categories")
    if not isinstance(categories, list) or len(categories) != 13:
        return [*errors, "taxonomy must contain exactly 13 source categories"]
    if [category.get("order") for category in categories] != list(range(1, 14)):
        errors.append("category order must be continuous from 1 to 13")
    slugs = [category.get("slug") for category in categories]
    if len(slugs) != len(set(slugs)):
        errors.append("category slugs must be unique")
    for index, category in enumerate(categories):
        if not category.get("title_ru") or not category.get("source_refs"):
            errors.append(f"categories[{index}] requires title_ru and source_refs")
    extensions = {extension.get("slug") for extension in manifest.get("platform_extensions", [])}
    if extensions != {"consent_communication", "connection_aftercare"}:
        errors.append("platform extensions must contain consent and aftercare")
    return errors


def preview_category_taxonomy(manifest: dict[str, Any]) -> str:
    kinds = Counter(category["content_kind"] for category in manifest["categories"])
    routing = Counter(category["default_routing"] for category in manifest["categories"])
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"import_allowed={manifest.get('import_allowed')}",
            f"categories={len(manifest['categories'])}",
            f"platform_extensions={len(manifest.get('platform_extensions', []))}",
            "content_kinds=" + ", ".join(f"{key}:{value}" for key, value in sorted(kinds.items())),
            "routing=" + ", ".join(f"{key}:{value}" for key, value in sorted(routing.items())),
        ]
    )


def lint_additional_titles(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != ADDITIONAL_TITLE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {ADDITIONAL_TITLE_SCHEMA_VERSION}")
    if manifest.get("import_allowed") is not False:
        errors.append("additional titles must set import_allowed=false")
    records = manifest.get("records", [])
    titles = manifest.get("titles", [])
    if len(records) != manifest.get("source_record_count"):
        errors.append("source_record_count mismatch")
    if len(titles) != manifest.get("unique_title_count"):
        errors.append("unique_title_count mismatch")
    record_ids = [record.get("source_id") for record in records]
    if len(record_ids) != len(set(record_ids)):
        errors.append("source IDs must be unique")
    known = set(record_ids)
    refs = {ref for title in titles for ref in title.get("source_refs", [])}
    if refs != known:
        errors.append("every source row must be referenced exactly by the title layer")
    if any(record.get("retained") is not True or record.get("seed_ready") is not False for record in records):
        errors.append("source records must be retained and not seed-ready")
    if any(title.get("seed_ready") is not False for title in titles):
        errors.append("normalized titles must not be seed-ready")
    return errors


def preview_additional_titles(manifest: dict[str, Any]) -> str:
    sources = Counter(record["source"] for record in manifest["records"])
    routing = Counter(title["review_routing"] for title in manifest["titles"])
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"import_allowed={manifest.get('import_allowed')}",
            f"source_records={len(manifest['records'])}",
            f"unique_titles={len(manifest['titles'])}",
            "sources=" + ", ".join(f"{key}:{value}" for key, value in sorted(sources.items())),
            "routing=" + ", ".join(f"{key}:{value}" for key, value in sorted(routing.items())),
        ]
    )


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
    schema_version = manifest.get("schema_version")
    is_source_inventory = schema_version == SOURCE_SCHEMA_VERSION
    is_editorial = schema_version == EDITORIAL_SCHEMA_VERSION
    is_review = schema_version == REVIEW_SCHEMA_VERSION
    is_inventory = schema_version == INVENTORY_SCHEMA_VERSION
    is_taxonomy = schema_version == TAXONOMY_SCHEMA_VERSION
    is_additional_titles = schema_version == ADDITIONAL_TITLE_SCHEMA_VERSION
    if is_source_inventory:
        errors = lint_source_inventory(manifest)
    elif is_editorial:
        errors = lint_editorial_candidates(manifest)
    elif is_review:
        errors = lint_editorial_review(manifest)
    elif is_inventory:
        errors = lint_inventory_source(manifest)
    elif is_taxonomy:
        errors = lint_category_taxonomy(manifest)
    elif is_additional_titles:
        errors = lint_additional_titles(manifest)
    else:
        errors = lint_manifest(manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("MANIFEST_OK")
    if args.preview:
        if is_source_inventory:
            print(preview_source_inventory(manifest))
        elif is_editorial:
            print(preview_editorial_candidates(manifest))
        elif is_review:
            print(preview_editorial_review(manifest))
        elif is_inventory:
            print(preview_inventory_source(manifest))
        elif is_taxonomy:
            print(preview_category_taxonomy(manifest))
        elif is_additional_titles:
            print(preview_additional_titles(manifest))
        else:
            print(preview(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
