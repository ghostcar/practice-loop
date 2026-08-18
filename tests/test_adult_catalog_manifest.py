import json
from pathlib import Path

from tools.adult_catalog_manifest import (
    lint_editorial_candidates,
    lint_editorial_review,
    lint_manifest,
    lint_source_inventory,
    load_manifest,
    preview,
    preview_editorial_candidates,
    preview_editorial_review,
    preview_source_inventory,
)

MANIFEST_PATH = Path("data/seed/adult_activity_foundation.v1.json")
SOURCE_INVENTORY_PATH = Path("data/seed/adult_activity_source_inventory.v1.json")
EDITORIAL_PATH = Path("data/seed/adult_activity_editorial_candidates.v1.json")
FLUID_TOILET_REVIEW_PATH = Path("data/seed/adult_activity_fluid_toilet_review.v1.json")
BREATH_REVIEW_PATH = Path("data/seed/adult_activity_breath_review.v1.json")
SEXUAL_TECHNIQUE_REVIEW_PATH = Path("data/seed/adult_activity_sexual_technique_review.v1.json")


def test_foundation_manifest_is_valid() -> None:
    manifest = load_manifest(MANIFEST_PATH)

    assert lint_manifest(manifest) == []
    assert manifest["import_allowed"] is False
    assert len(manifest["cards"]) == 7


def test_lint_rejects_required_media_and_penalty() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    card = manifest["cards"][0]
    card["evidence_policy"]["media_required"] = True
    card["gamification"]["penalty_enabled"] = True

    errors = lint_manifest(manifest)

    assert any("media_required" in error for error in errors)
    assert any("cannot enable penalties" in error for error in errors)


def test_preview_is_read_only_summary() -> None:
    manifest = load_manifest(MANIFEST_PATH)

    result = preview(manifest)

    assert "import_allowed=False" in result
    assert "cards=7" in result


def test_source_inventory_retains_every_content_title() -> None:
    manifest = load_manifest(SOURCE_INVENTORY_PATH)

    assert lint_source_inventory(manifest) == []
    assert manifest["source_title_rows"] == 164
    assert manifest["ignored_template_rows"] == 1
    assert len(manifest["records"]) == 163
    assert all(record["retained"] for record in manifest["records"])
    assert all(not record["seed_ready"] for record in manifest["records"])


def test_source_inventory_preview_reports_dispositions() -> None:
    manifest = load_manifest(SOURCE_INVENTORY_PATH)

    result = preview_source_inventory(manifest)

    assert "records=163" in result
    assert "research_only:" in result
    assert "manual_only:" in result


def test_editorial_candidates_reference_retained_source_records() -> None:
    source = load_manifest(SOURCE_INVENTORY_PATH)
    candidates = load_manifest(EDITORIAL_PATH)
    source_ids = {record["source_id"] for record in source["records"]}

    assert lint_editorial_candidates(candidates, source_ids) == []
    assert candidates["import_allowed"] is False
    assert len(candidates["cards"]) == 34


def test_editorial_preview_reports_candidate_mix() -> None:
    candidates = load_manifest(EDITORIAL_PATH)

    result = preview_editorial_candidates(candidates)

    assert "cards=34" in result
    assert "elevated:17" in result


def test_fluid_toilet_review_retains_and_covers_all_source_records() -> None:
    source = load_manifest(SOURCE_INVENTORY_PATH)
    review = load_manifest(FLUID_TOILET_REVIEW_PATH)
    expected_ids = {
        record["source_id"]
        for record in source["records"]
        if record["source_area"] in {"fluid_enema_control", "toilet_control"}
    }

    assert lint_editorial_review(review, expected_ids) == []
    assert {record["source_id"] for record in review["records"]} == expected_ids
    assert len(review["records"]) == 42
    assert all(record["retained"] for record in review["records"])


def test_fluid_toilet_review_preview_reports_outcomes() -> None:
    review = load_manifest(FLUID_TOILET_REVIEW_PATH)

    result = preview_editorial_review(review)

    assert "records=42" in result
    assert "promote_candidate:12" in result
    assert "research_backlog:6" in result


def test_breath_review_retains_all_sources_without_automation() -> None:
    source = load_manifest(SOURCE_INVENTORY_PATH)
    review = load_manifest(BREATH_REVIEW_PATH)
    expected_ids = {
        record["source_id"] for record in source["records"] if record["source_area"] == "breath_restriction"
    }

    assert lint_editorial_review(review, expected_ids) == []
    assert {record["source_id"] for record in review["records"]} == expected_ids
    assert len(review["records"]) == 20
    assert all(record["retained"] for record in review["records"])
    assert all(not record["automation_allowed"] for record in review["records"])
    assert all("no_executable_breath_instructions" in record["required_gates"] for record in review["records"])


def test_breath_review_preview_reports_research_queue() -> None:
    review = load_manifest(BREATH_REVIEW_PATH)

    result = preview_editorial_review(review)

    assert "records=20" in result
    assert "research_backlog:18" in result
    assert "rewrite_required:1" in result


def test_sexual_technique_review_has_exact_source_coverage() -> None:
    source = load_manifest(SOURCE_INVENTORY_PATH)
    review = load_manifest(SEXUAL_TECHNIQUE_REVIEW_PATH)
    expected_ids = {record["source_id"] for record in source["records"] if record["source_area"] == "sexual_technique"}

    assert lint_editorial_review(review, expected_ids) == []
    assert {record["source_id"] for record in review["records"]} == expected_ids
    assert len(review["records"]) == 20
    assert all(record["retained"] for record in review["records"])
    assert all(not record["automation_allowed"] for record in review["records"])


def test_promoted_sexual_sources_have_editorial_derivatives() -> None:
    review = load_manifest(SEXUAL_TECHNIQUE_REVIEW_PATH)
    candidates = load_manifest(EDITORIAL_PATH)
    candidate_slugs = {card["slug"] for card in candidates["cards"]}
    candidate_refs = {source_ref for card in candidates["cards"] for source_ref in card["source_refs"]}
    promoted = [record for record in review["records"] if record["review_outcome"] == "promote_candidate"]

    assert len(promoted) == 9
    assert all(record["source_id"] in candidate_refs for record in promoted)
    assert all(record["derived_card_slug"] in candidate_slugs for record in promoted)


def test_sexual_technique_review_preview_reports_outcomes() -> None:
    review = load_manifest(SEXUAL_TECHNIQUE_REVIEW_PATH)

    result = preview_editorial_review(review)

    assert "records=20" in result
    assert "promote_candidate:9" in result
    assert "rewrite_required:5" in result
    assert "research_backlog:1" in result
