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
PARAMETER_SCHEMA_VERSION = "adult-parameter-vocabulary/v1alpha1"
BODY_ZONE_SCHEMA_VERSION = "adult-body-zone-vocabulary/v1alpha1"
SCENARIO_SCHEMA_VERSION = "adult-scenario-source/v1alpha1"
PROGRESSION_SCHEMA_VERSION = "adult-progression-source/v1alpha1"
TIMER_SCHEMA_VERSION = "adult-timer-source/v1alpha1"
EVIDENCE_SCHEMA_VERSION = "adult-evidence-source/v1alpha1"
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
    if not isinstance(manifest.get("import_allowed"), bool):
        errors.append("import_allowed must be a boolean (false=proposal, true=owner-authorized)")

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
        if record.get("seed_ready") is not True:
            errors.append(f"{prefix}.seed_ready must be true after owner promotion (ADR-111)")
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
    if not isinstance(manifest.get("import_allowed"), bool):
        errors.append("import_allowed must be a boolean (false=proposal, true=owner-authorized)")
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
        if card.get("automation_allowed") is not False:
            errors.append(f"{prefix} editorial candidates must keep automation_allowed=false until owner re-enables")
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
    if manifest.get("import_allowed") is not True:
        errors.append("editorial review must set import_allowed=true after owner promotion (ADR-111)")
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
        if record.get("owner_override") is not True:
            errors.append(f"{prefix}.owner_override must be true (ADR-111)")
        if record.get("user_discoverable_after_moderation") is not True:
            errors.append(f"{prefix} record must be user-discoverable after owner promotion")
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
    if manifest.get("import_allowed") is not True:
        errors.append("additional titles must set import_allowed=true after owner promotion (ADR-111)")
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
    if any(record.get("retained") is not True or record.get("seed_ready") is not True for record in records):
        errors.append("source records must be retained and seed-ready after owner promotion (ADR-111)")
    for title in titles:
        if title.get("noise") is True:
            if title.get("seed_ready") is not False:
                errors.append("noise titles must be seed_ready=false (owner filter)")
        elif title.get("seed_ready") is not True:
            errors.append("normalized titles must be seed-ready after owner promotion (ADR-111)")
    title_ids = {title.get("title_id") for title in titles}
    groups = manifest.get("semantic_groups", [])
    if not isinstance(groups, list):
        errors.append("semantic_groups must be an array")
        return errors
    group_ids: set[str] = set()
    members_seen: set[str] = set()
    merged_titles = 0
    for index, group in enumerate(groups):
        prefix = f"semantic_groups[{index}]"
        group_id = group.get("group_id")
        if not group_id or group_id in group_ids:
            errors.append(f"{prefix}.group_id must be non-empty and unique")
        group_ids.add(group_id)
        members = group.get("member_title_ids")
        if not isinstance(members, list) or len(members) < 2:
            errors.append(f"{prefix}.member_title_ids must list at least two titles")
            continue
        if len(set(members)) != len(members):
            errors.append(f"{prefix}.member_title_ids must not repeat")
        unknown = set(members) - title_ids
        if unknown:
            errors.append(f"{prefix} references unknown titles: {', '.join(sorted(unknown))}")
        overlap = members_seen & set(members)
        if overlap:
            errors.append(f"{prefix} overlaps another group: {', '.join(sorted(overlap))}")
        members_seen.update(members)
        if group.get("canonical_title_id") not in members:
            errors.append(f"{prefix}.canonical_title_id must be one of member_title_ids")
        merged_titles += len(members) - 1
    if len(titles) - merged_titles != manifest.get("semantic_title_count"):
        errors.append("semantic_title_count mismatch")
    return errors


def preview_additional_titles(manifest: dict[str, Any]) -> str:
    sources = Counter(record["source"] for record in manifest["records"])
    routing = Counter(title["review_routing"] for title in manifest["titles"])
    noise = sum(1 for title in manifest["titles"] if title.get("noise") is True)
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"import_allowed={manifest.get('import_allowed')}",
            f"source_records={len(manifest['records'])}",
            f"unique_titles={len(manifest['titles'])}",
            f"noise_titles={noise}",
            f"semantic_titles={manifest.get('semantic_title_count')}",
            f"semantic_groups={len(manifest.get('semantic_groups', []))}",
            "sources=" + ", ".join(f"{key}:{value}" for key, value in sorted(sources.items())),
            "routing=" + ", ".join(f"{key}:{value}" for key, value in sorted(routing.items())),
        ]
    )


def lint_parameter_vocabulary(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != PARAMETER_SCHEMA_VERSION or manifest.get("import_allowed") is not False:
        errors.append("invalid parameter vocabulary header")
    definitions = manifest.get("definitions", [])
    keys = [definition.get("key") for definition in definitions]
    if len(keys) != len(set(keys)) or not definitions:
        errors.append("parameter keys must be non-empty and unique")
    if manifest.get("legacy_values_imported") is not False:
        errors.append("legacy parameter values must not be imported")
    if any(definition.get("allow_custom_value") is not False for definition in definitions):
        errors.append("source vocabulary cannot allow custom values")
    return errors


def lint_body_zone_vocabulary(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != BODY_ZONE_SCHEMA_VERSION or manifest.get("import_allowed") is not False:
        errors.append("invalid body-zone vocabulary header")
    zones = manifest.get("zones", [])
    slugs = [zone.get("slug") for zone in zones]
    if len(slugs) != len(set(slugs)):
        errors.append("body-zone slugs must be unique")
    if sum(zone.get("existing") is True for zone in zones) != manifest.get("existing_count"):
        errors.append("existing body-zone count mismatch")
    if sum(zone.get("existing") is False for zone in zones) != manifest.get("extension_count"):
        errors.append("body-zone extension count mismatch")
    if not {"neck", "throat", "eyes", "nose"}.issubset(
        {zone["slug"] for zone in zones if zone.get("automation_routing") == "no_automation"}
    ):
        errors.append("vulnerable zones must disable automation")
    return errors


def _lint_reference_layer(
    manifest: dict[str, Any],
    schema_version: str,
    entity_key: str,
    entity_id_field: str,
    count_key: str,
) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != schema_version:
        errors.append(f"schema_version must be {schema_version}")
    if manifest.get("import_allowed") is not False:
        errors.append("source manifest must set import_allowed=false")
    records = manifest.get("source_records")
    entities = manifest.get(entity_key)
    if not isinstance(records, list) or not isinstance(entities, list):
        return [*errors, "source_records and entity layer must be arrays"]
    if len(records) != manifest.get("source_record_count"):
        errors.append("source_record_count mismatch")
    if len(entities) != manifest.get(count_key):
        errors.append(f"{count_key} mismatch")
    record_ids = [record.get("source_id") for record in records]
    if len(record_ids) != len(set(record_ids)):
        errors.append("source IDs must be unique")
    if any(record.get("retained") is not True for record in records):
        errors.append("every source record must be retained")
    known_ids = set(record_ids)
    entity_ids: set[str] = set()
    referenced_ids: set[str] = set()
    for index, entity in enumerate(entities):
        prefix = f"{entity_key}[{index}]"
        entity_id = entity.get(entity_id_field)
        if entity_id in entity_ids:
            errors.append(f"{prefix}.{entity_id_field} is duplicated")
        entity_ids.add(entity_id)
        refs = set(entity.get("source_refs", []))
        if not refs:
            errors.append(f"{prefix}.source_refs must be non-empty")
        if refs - known_ids:
            errors.append(f"{prefix}.source_refs contains unknown IDs")
        referenced_ids.update(refs)
        if entity.get("seed_ready") is not False:
            errors.append(f"{prefix}.seed_ready must remain false")
    if referenced_ids != known_ids:
        errors.append("every source record must be referenced by the normalized layer")
    return errors


def lint_scenario_source(manifest: dict[str, Any]) -> list[str]:
    errors = _lint_reference_layer(manifest, SCENARIO_SCHEMA_VERSION, "scenarios", "scenario_id", "scenario_count")
    allowed_routing = {"candidate", "manual_only", "needs_safe_rewrite", "research_only"}
    for index, scenario in enumerate(manifest.get("scenarios", [])):
        prefix = f"scenarios[{index}]"
        if not scenario.get("phases"):
            errors.append(f"{prefix}.phases must be non-empty")
        if scenario.get("review_routing") not in allowed_routing:
            errors.append(f"{prefix}.review_routing is invalid")
        if scenario.get("steps_imported") is not False:
            errors.append(f"{prefix}.steps_imported must be false (no source steps copied)")
    return errors


def preview_scenario_source(manifest: dict[str, Any]) -> str:
    routing = Counter(scenario["review_routing"] for scenario in manifest["scenarios"])
    kinds = Counter(scenario["kind"] for scenario in manifest["scenarios"])
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"import_allowed={manifest.get('import_allowed')}",
            f"source_records={len(manifest['source_records'])}",
            f"scenarios={len(manifest['scenarios'])}",
            "routing=" + ", ".join(f"{key}:{value}" for key, value in sorted(routing.items())),
            "kinds=" + ", ".join(f"{key}:{value}" for key, value in sorted(kinds.items())),
        ]
    )


def lint_progression_source(manifest: dict[str, Any]) -> list[str]:
    errors = _lint_reference_layer(
        manifest, PROGRESSION_SCHEMA_VERSION, "hierarchies", "hierarchy_id", "hierarchy_count"
    )
    for index, hierarchy in enumerate(manifest.get("hierarchies", [])):
        prefix = f"hierarchies[{index}]"
        stages = hierarchy.get("stages")
        if not isinstance(stages, list) or not stages:
            errors.append(f"{prefix}.stages must be non-empty")
        elif any(
            not isinstance(stage, dict) or not stage.get("stage") or stage.get("levels", 0) < 1 for stage in stages
        ):
            errors.append(f"{prefix}.stages require stage name and levels >= 1")
        if hierarchy.get("escalation_automation") is not False:
            errors.append(f"{prefix}.escalation_automation must be false")
    return errors


def preview_progression_source(manifest: dict[str, Any]) -> str:
    kinds = Counter(hierarchy["kind"] for hierarchy in manifest["hierarchies"])
    total_levels = sum(stage["levels"] for hierarchy in manifest["hierarchies"] for stage in hierarchy["stages"])
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"import_allowed={manifest.get('import_allowed')}",
            f"source_records={len(manifest['source_records'])}",
            f"hierarchies={len(manifest['hierarchies'])}",
            f"total_levels={total_levels}",
            "kinds=" + ", ".join(f"{key}:{value}" for key, value in sorted(kinds.items())),
        ]
    )


def lint_timer_source(manifest: dict[str, Any]) -> list[str]:
    errors = _lint_reference_layer(manifest, TIMER_SCHEMA_VERSION, "timers", "timer_id", "timer_count")
    for index, timer in enumerate(manifest.get("timers", [])):
        prefix = f"timers[{index}]"
        if not timer.get("name"):
            errors.append(f"{prefix}.name must be non-empty")
        if timer.get("emergency_stop_always_available") is not True:
            errors.append(f"{prefix}.emergency_stop_always_available must be true")
    return errors


def preview_timer_source(manifest: dict[str, Any]) -> str:
    kinds = Counter(timer["kind"] for timer in manifest["timers"])
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"import_allowed={manifest.get('import_allowed')}",
            f"source_records={len(manifest['source_records'])}",
            f"timers={len(manifest['timers'])}",
            "kinds=" + ", ".join(f"{key}:{value}" for key, value in sorted(kinds.items())),
        ]
    )


def lint_evidence_source(manifest: dict[str, Any]) -> list[str]:
    errors = _lint_reference_layer(
        manifest, EVIDENCE_SCHEMA_VERSION, "evidence_types", "evidence_id", "evidence_type_count"
    )
    for index, evidence in enumerate(manifest.get("evidence_types", [])):
        prefix = f"evidence_types[{index}]"
        if not evidence.get("name"):
            errors.append(f"{prefix}.name must be non-empty")
        if evidence.get("media_required") is not False:
            errors.append(f"{prefix}.media_required must be false")
    return errors


def preview_evidence_source(manifest: dict[str, Any]) -> str:
    kinds = Counter(evidence["kind"] for evidence in manifest["evidence_types"])
    return "\n".join(
        [
            f"schema={manifest['schema_version']}",
            f"import_allowed={manifest.get('import_allowed')}",
            f"source_records={len(manifest['source_records'])}",
            f"evidence_types={len(manifest['evidence_types'])}",
            "kinds=" + ", ".join(f"{key}:{value}" for key, value in sorted(kinds.items())),
        ]
    )


def preview_vocabulary(manifest: dict[str, Any]) -> str:
    if manifest["schema_version"] == PARAMETER_SCHEMA_VERSION:
        routing = Counter(item["safety_routing"] for item in manifest["definitions"])
        return f"schema={PARAMETER_SCHEMA_VERSION}\ndefinitions={len(manifest['definitions'])}\nrouting=" + ", ".join(
            f"{key}:{value}" for key, value in sorted(routing.items())
        )
    routing = Counter(item["automation_routing"] for item in manifest["zones"])
    return (
        f"schema={BODY_ZONE_SCHEMA_VERSION}\nzones={len(manifest['zones'])}"
        f"\nexisting={manifest['existing_count']}\nextensions={manifest['extension_count']}\nrouting="
        + ", ".join(f"{key}:{value}" for key, value in sorted(routing.items()))
    )


EXTENSION_SCHEMA_VERSION = "adult-activity-extensions/v1alpha1"


def lint_extensions(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != EXTENSION_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EXTENSION_SCHEMA_VERSION}")
    if manifest.get("import_allowed") is not True:
        errors.append("extensions must set import_allowed=true (ADR-119)")
    cards = manifest.get("cards")
    if not isinstance(cards, list) or not cards:
        return [*errors, "cards must be a non-empty array"]
    slugs: set[str] = set()
    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        slug = card.get("slug")
        if not isinstance(slug, str) or not slug or slug in slugs:
            errors.append(f"{prefix}.slug must be non-empty and unique")
        slugs.add(slug)
        for locale in ("ru", "en"):
            for field in ("title", "summary"):
                if not str(card.get(field, {}).get(locale, "")).strip():
                    errors.append(f"{prefix}.{field}.{locale} must be non-empty")
        if card.get("risk_level") not in ALLOWED_RISKS:
            errors.append(f"{prefix}.risk_level must be low or elevated")
        if not card.get("required_controls"):
            errors.append(f"{prefix}.required_controls must be non-empty")
        if not card.get("rules"):
            errors.append(f"{prefix}.rules must be non-empty")
    return errors


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
    is_parameters = schema_version == PARAMETER_SCHEMA_VERSION
    is_body_zones = schema_version == BODY_ZONE_SCHEMA_VERSION
    is_scenario = schema_version == SCENARIO_SCHEMA_VERSION
    is_progression = schema_version == PROGRESSION_SCHEMA_VERSION
    is_timer = schema_version == TIMER_SCHEMA_VERSION
    is_evidence = schema_version == EVIDENCE_SCHEMA_VERSION
    is_extensions = schema_version == EXTENSION_SCHEMA_VERSION
    if is_extensions:
        errors = lint_extensions(manifest)
    elif is_source_inventory:
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
    elif is_parameters:
        errors = lint_parameter_vocabulary(manifest)
    elif is_body_zones:
        errors = lint_body_zone_vocabulary(manifest)
    elif is_scenario:
        errors = lint_scenario_source(manifest)
    elif is_progression:
        errors = lint_progression_source(manifest)
    elif is_timer:
        errors = lint_timer_source(manifest)
    elif is_evidence:
        errors = lint_evidence_source(manifest)
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
        elif is_parameters or is_body_zones:
            print(preview_vocabulary(manifest))
        elif is_scenario:
            print(preview_scenario_source(manifest))
        elif is_progression:
            print(preview_progression_source(manifest))
        elif is_timer:
            print(preview_timer_source(manifest))
        elif is_evidence:
            print(preview_evidence_source(manifest))
        else:
            print(preview(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
