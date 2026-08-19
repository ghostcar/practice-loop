import json
from pathlib import Path

from tools.adult_catalog_manifest import (
    lint_additional_titles,
    lint_body_zone_vocabulary,
    lint_category_taxonomy,
    lint_editorial_candidates,
    lint_editorial_review,
    lint_evidence_source,
    lint_extensions,
    lint_inventory_source,
    lint_manifest,
    lint_parameter_vocabulary,
    lint_progression_source,
    lint_scenario_source,
    lint_source_inventory,
    lint_timer_source,
    load_manifest,
    preview,
    preview_additional_titles,
    preview_category_taxonomy,
    preview_editorial_candidates,
    preview_editorial_review,
    preview_evidence_source,
    preview_inventory_source,
    preview_progression_source,
    preview_scenario_source,
    preview_source_inventory,
    preview_timer_source,
)

MANIFEST_PATH = Path("data/seed/adult_activity_foundation.v1.json")
SOURCE_INVENTORY_PATH = Path("data/seed/adult_activity_source_inventory.v1.json")
EDITORIAL_PATH = Path("data/seed/adult_activity_editorial_candidates.v1.json")
FULL_CATALOG_PATH = Path("data/seed/adult_activity_full_catalog.v1.json")
FLUID_TOILET_REVIEW_PATH = Path("data/seed/adult_activity_fluid_toilet_review.v1.json")
BREATH_REVIEW_PATH = Path("data/seed/adult_activity_breath_review.v1.json")
SEXUAL_TECHNIQUE_REVIEW_PATH = Path("data/seed/adult_activity_sexual_technique_review.v1.json")
WEARING_CHASTITY_REVIEW_PATH = Path("data/seed/adult_activity_wearing_chastity_review.v1.json")
RESTRAINT_REVIEW_PATH = Path("data/seed/adult_activity_restraint_bondage_review.v1.json")
SENSORY_REVIEW_PATH = Path("data/seed/adult_activity_sensory_review.v1.json")
IMPACT_REVIEW_PATH = Path("data/seed/adult_activity_impact_review.v1.json")
STANDALONE_REVIEW_PATH = Path("data/seed/adult_activity_standalone_review.v1.json")
INVENTORY_SOURCE_PATH = Path("data/seed/adult_inventory_source.v1.json")
TAXONOMY_PATH = Path("data/seed/adult_category_taxonomy_source.v1.json")
ADDITIONAL_TITLES_PATH = Path("data/seed/adult_additional_activity_titles.v1.json")
EXTENSIONS_PATH = Path("data/seed/adult_activity_extensions.v1.json")
PARAMETER_VOCABULARY_PATH = Path("data/seed/adult_parameter_vocabulary.v1.json")
BODY_ZONE_VOCABULARY_PATH = Path("data/seed/adult_body_zone_vocabulary.v1.json")
SCENARIO_SOURCE_PATH = Path("data/seed/adult_scenario_source.v1.json")
PROGRESSION_SOURCE_PATH = Path("data/seed/adult_progression_source.v1.json")
TIMER_SOURCE_PATH = Path("data/seed/adult_timer_source.v1.json")
EVIDENCE_SOURCE_PATH = Path("data/seed/adult_evidence_source.v1.json")


def test_foundation_manifest_is_valid() -> None:
    manifest = load_manifest(MANIFEST_PATH)

    assert lint_manifest(manifest) == []
    assert manifest["import_allowed"] is True
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

    assert "import_allowed=True" in result
    assert "cards=7" in result


def test_source_inventory_retains_every_content_title() -> None:
    manifest = load_manifest(SOURCE_INVENTORY_PATH)

    assert lint_source_inventory(manifest) == []
    assert manifest["source_title_rows"] == 164
    assert manifest["ignored_template_rows"] == 1
    assert len(manifest["records"]) == 163
    assert all(record["retained"] for record in manifest["records"])
    assert all(record["seed_ready"] for record in manifest["records"])


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
    assert candidates["import_allowed"] is True
    assert len(candidates["cards"]) == 34
    assert all(not card["automation_allowed"] for card in candidates["cards"])


def test_editorial_preview_reports_candidate_mix() -> None:
    candidates = load_manifest(EDITORIAL_PATH)

    result = preview_editorial_candidates(candidates)

    assert "cards=34" in result
    assert "elevated:17" in result


def test_extensions_are_valid_and_cover_four_categories() -> None:
    extensions = load_manifest(EXTENSIONS_PATH)

    assert lint_extensions(extensions) == []
    assert extensions["import_allowed"] is True
    assert len(extensions["cards"]) >= 30
    categories = {card["category"] for card in extensions["cards"]}
    assert categories == {
        "humiliation_objectification",
        "service_protocol",
        "psychological_control",
        "clothing_fetish",
    }
    assert all(card["rules"] for card in extensions["cards"])


def test_full_catalog_covers_every_source_record() -> None:
    source = load_manifest(SOURCE_INVENTORY_PATH)
    additional = load_manifest(ADDITIONAL_TITLES_PATH)
    full_catalog = load_manifest(FULL_CATALOG_PATH)
    source_ids = {record["source_id"] for record in source["records"]}
    title_ids = {title["title_id"] for title in additional["titles"]}
    known_ids = source_ids | title_ids

    assert lint_editorial_candidates(full_catalog, known_ids) == []
    assert full_catalog["import_allowed"] is True
    covered = {ref for card in full_catalog["cards"] for ref in card["source_refs"]}
    assert source_ids <= covered  # ADR-111: every prepared record is promoted
    assert all(card["automation_allowed"] is False for card in full_catalog["cards"])
    # ADR-119 extension: four extra categories have cards too.
    extension_categories = {
        "humiliation_objectification",
        "service_protocol",
        "psychological_control",
        "clothing_fetish",
    }
    extension_cards = [c for c in full_catalog["cards"] if c["category"] in extension_categories]
    assert len(extension_cards) >= 30
    assert full_catalog["extension_cards"] == len(extension_cards)


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


def test_wearing_chastity_review_has_exact_source_coverage() -> None:
    source = load_manifest(SOURCE_INVENTORY_PATH)
    review = load_manifest(WEARING_CHASTITY_REVIEW_PATH)
    expected_ids = {record["source_id"] for record in source["records"] if record["source_area"] == "wearing_chastity"}

    assert lint_editorial_review(review, expected_ids) == []
    assert {record["source_id"] for record in review["records"]} == expected_ids
    assert len(review["records"]) == 20
    assert all(record["retained"] for record in review["records"])
    assert all(not record["automation_allowed"] for record in review["records"])


def test_promoted_wearing_sources_have_editorial_derivatives() -> None:
    review = load_manifest(WEARING_CHASTITY_REVIEW_PATH)
    candidates = load_manifest(EDITORIAL_PATH)
    candidate_slugs = {card["slug"] for card in candidates["cards"]}
    candidate_refs = {source_ref for card in candidates["cards"] for source_ref in card["source_refs"]}
    promoted = [record for record in review["records"] if record["review_outcome"] == "promote_candidate"]

    assert len(promoted) == 5
    assert all(record["source_id"] in candidate_refs for record in promoted)
    assert all(record["derived_card_slug"] in candidate_slugs for record in promoted)


def test_wearing_chastity_review_preview_reports_outcomes() -> None:
    review = load_manifest(WEARING_CHASTITY_REVIEW_PATH)

    result = preview_editorial_review(review)

    assert "records=20" in result
    assert "promote_candidate:5" in result
    assert "manual_reference:4" in result
    assert "rewrite_required:9" in result
    assert "research_backlog:2" in result


def test_restraint_review_has_exact_source_and_derivative_coverage() -> None:
    source = load_manifest(SOURCE_INVENTORY_PATH)
    review = load_manifest(RESTRAINT_REVIEW_PATH)
    candidates = load_manifest(EDITORIAL_PATH)
    expected_ids = {record["source_id"] for record in source["records"] if record["source_area"] == "restraint_bondage"}
    candidate_slugs = {card["slug"] for card in candidates["cards"]}
    candidate_refs = {source_ref for card in candidates["cards"] for source_ref in card["source_refs"]}
    promoted = [record for record in review["records"] if record["review_outcome"] == "promote_candidate"]

    assert lint_editorial_review(review, expected_ids) == []
    assert {record["source_id"] for record in review["records"]} == expected_ids
    assert len(review["records"]) == 20
    assert len(promoted) == 4
    assert all(record["source_id"] in candidate_refs for record in promoted)
    assert all(record["derived_card_slug"] in candidate_slugs for record in promoted)
    assert all("quick_release_required" in record["required_gates"] for record in review["records"])
    assert all(record["retained"] and not record["automation_allowed"] for record in review["records"])


def test_restraint_review_preview_reports_outcomes() -> None:
    result = preview_editorial_review(load_manifest(RESTRAINT_REVIEW_PATH))

    assert "records=20" in result
    assert "promote_candidate:4" in result
    assert "manual_reference:5" in result
    assert "rewrite_required:9" in result
    assert "research_backlog:2" in result


def test_remaining_review_batches_have_exact_source_coverage() -> None:
    source = load_manifest(SOURCE_INVENTORY_PATH)
    for path, area, expected_count in (
        (SENSORY_REVIEW_PATH, "sensory_play", 20),
        (IMPACT_REVIEW_PATH, "impact_play", 20),
        (STANDALONE_REVIEW_PATH, "other", 1),
    ):
        review = load_manifest(path)
        expected_ids = {record["source_id"] for record in source["records"] if record["source_area"] == area}
        assert lint_editorial_review(review, expected_ids) == []
        assert {record["source_id"] for record in review["records"]} == expected_ids
        assert len(review["records"]) == expected_count


def test_all_source_records_are_covered_once_by_review_batches() -> None:
    source = load_manifest(SOURCE_INVENTORY_PATH)
    review_paths = sorted(Path("data/seed").glob("adult_activity_*_review.v1.json"))
    reviewed_ids = [record["source_id"] for path in review_paths for record in load_manifest(path)["records"]]
    source_ids = {record["source_id"] for record in source["records"]}

    assert len(reviewed_ids) == 163
    assert len(set(reviewed_ids)) == 163
    assert set(reviewed_ids) == source_ids


def test_promoted_sensory_and_impact_sources_have_derivatives() -> None:
    candidates = load_manifest(EDITORIAL_PATH)
    candidate_slugs = {card["slug"] for card in candidates["cards"]}
    candidate_refs = {source_ref for card in candidates["cards"] for source_ref in card["source_refs"]}

    for path, expected_promoted in ((SENSORY_REVIEW_PATH, 5), (IMPACT_REVIEW_PATH, 6)):
        promoted = [
            record for record in load_manifest(path)["records"] if record["review_outcome"] == "promote_candidate"
        ]
        assert len(promoted) == expected_promoted
        assert all(record["source_id"] in candidate_refs for record in promoted)
        assert all(record["derived_card_slug"] in candidate_slugs for record in promoted)


def test_inventory_source_is_complete_and_non_importable() -> None:
    manifest = load_manifest(INVENTORY_SOURCE_PATH)

    assert lint_inventory_source(manifest) == []
    assert manifest["import_allowed"] is False
    assert len(manifest["source_records"]) == 186
    assert len(manifest["items"]) == 135
    assert all(item["seed_ready"] is False for item in manifest["items"])
    assert all("price" not in record and "quantity" not in record for record in manifest["source_records"])


def test_inventory_preview_reports_families_and_routing() -> None:
    result = preview_inventory_source(load_manifest(INVENTORY_SOURCE_PATH))

    assert "source_records=186" in result
    assert "normalized_items=135" in result
    assert "clothing_fetish:30" in result
    assert "future_research:18" in result


def test_category_taxonomy_has_source_and_platform_layers() -> None:
    manifest = load_manifest(TAXONOMY_PATH)

    assert lint_category_taxonomy(manifest) == []
    assert len(manifest["categories"]) == 13
    assert [category["order"] for category in manifest["categories"]] == list(range(1, 14))
    assert {extension["slug"] for extension in manifest["platform_extensions"]} == {
        "consent_communication",
        "connection_aftercare",
    }


def test_category_taxonomy_preview_reports_routing() -> None:
    result = preview_category_taxonomy(load_manifest(TAXONOMY_PATH))

    assert "categories=13" in result
    assert "platform_extensions=2" in result
    assert "research_only:1" in result


def test_additional_title_inventory_retains_all_rows() -> None:
    manifest = load_manifest(ADDITIONAL_TITLES_PATH)

    assert lint_additional_titles(manifest) == []
    assert len(manifest["records"]) == 289
    assert len(manifest["titles"]) == 286
    assert all(record["retained"] and record["seed_ready"] for record in manifest["records"])


def test_additional_title_semantic_dedupe_is_valid() -> None:
    manifest = load_manifest(ADDITIONAL_TITLES_PATH)
    title_ids = {title["title_id"] for title in manifest["titles"]}

    assert manifest["semantic_title_count"] == 277
    assert len(manifest["semantic_groups"]) == 9
    for group in manifest["semantic_groups"]:
        assert group["canonical_title_id"] in group["member_title_ids"]
        assert len(group["member_title_ids"]) >= 2
        assert set(group["member_title_ids"]) <= title_ids
    all_members = [title_id for group in manifest["semantic_groups"] for title_id in group["member_title_ids"]]
    assert len(all_members) == len(set(all_members))
    merged_titles = sum(len(group["member_title_ids"]) - 1 for group in manifest["semantic_groups"])
    assert len(manifest["titles"]) - merged_titles == manifest["semantic_title_count"]


def test_additional_title_preview_reports_sources() -> None:
    result = preview_additional_titles(load_manifest(ADDITIONAL_TITLES_PATH))

    assert "source_records=289" in result
    assert "unique_titles=286" in result
    assert "semantic_titles=277" in result
    assert "semantic_groups=9" in result
    assert "examples/Книга1.xlsx:" in result


def test_parameter_and_body_zone_vocabularies_are_safe_overlays() -> None:
    parameters = load_manifest(PARAMETER_VOCABULARY_PATH)
    body_zones = load_manifest(BODY_ZONE_VOCABULARY_PATH)

    assert lint_parameter_vocabulary(parameters) == []
    assert lint_body_zone_vocabulary(body_zones) == []
    assert len(parameters["definitions"]) == 27
    assert parameters["legacy_values_imported"] is False
    assert body_zones["existing_count"] == 39
    assert body_zones["extension_count"] == 9


def test_scenario_source_keeps_names_and_phases_without_steps() -> None:
    manifest = load_manifest(SCENARIO_SOURCE_PATH)

    assert lint_scenario_source(manifest) == []
    assert manifest["import_allowed"] is False
    assert len(manifest["source_records"]) == 13
    assert len(manifest["scenarios"]) == 13
    assert all(scenario["steps_imported"] is False for scenario in manifest["scenarios"])
    assert all(not scenario["seed_ready"] for scenario in manifest["scenarios"])
    assert all(scenario["review_routing"] in {"candidate", "manual_only", "needs_safe_rewrite", "research_only"}
               for scenario in manifest["scenarios"])


def test_scenario_source_preview_reports_routing() -> None:
    result = preview_scenario_source(load_manifest(SCENARIO_SOURCE_PATH))

    assert "scenarios=13" in result
    assert "research_only:11" in result
    assert "manual_only:2" in result


def test_progression_source_is_structure_only() -> None:
    manifest = load_manifest(PROGRESSION_SOURCE_PATH)

    assert lint_progression_source(manifest) == []
    assert manifest["import_allowed"] is False
    assert len(manifest["source_records"]) == 8
    assert len(manifest["hierarchies"]) == 6
    assert all(hierarchy["escalation_automation"] is False for hierarchy in manifest["hierarchies"])
    assert all(not hierarchy["seed_ready"] for hierarchy in manifest["hierarchies"])
    assert all(stage["levels"] >= 1 for hierarchy in manifest["hierarchies"] for stage in hierarchy["stages"])


def test_progression_source_preview_reports_levels() -> None:
    result = preview_progression_source(load_manifest(PROGRESSION_SOURCE_PATH))

    assert "hierarchies=6" in result
    assert "total_levels=63" in result


def test_timer_source_keeps_emergency_stop_invariant() -> None:
    manifest = load_manifest(TIMER_SOURCE_PATH)

    assert lint_timer_source(manifest) == []
    assert manifest["import_allowed"] is False
    assert len(manifest["source_records"]) == 9
    assert len(manifest["timers"]) == 9
    assert all(timer["emergency_stop_always_available"] for timer in manifest["timers"])
    assert all(not timer["seed_ready"] for timer in manifest["timers"])


def test_timer_source_preview_reports_kinds() -> None:
    result = preview_timer_source(load_manifest(TIMER_SOURCE_PATH))

    assert "timers=9" in result
    assert "interval_device:4" in result


def test_evidence_source_never_requires_media() -> None:
    manifest = load_manifest(EVIDENCE_SOURCE_PATH)

    assert lint_evidence_source(manifest) == []
    assert manifest["import_allowed"] is False
    assert len(manifest["source_records"]) == 8
    assert len(manifest["evidence_types"]) == 7
    assert all(evidence["media_required"] is False for evidence in manifest["evidence_types"])
    assert all(not evidence["seed_ready"] for evidence in manifest["evidence_types"])


def test_evidence_source_preview_reports_kinds() -> None:
    result = preview_evidence_source(load_manifest(EVIDENCE_SOURCE_PATH))

    assert "evidence_types=7" in result
    assert "checkpoint:1" in result


def test_reference_layers_cover_all_source_records() -> None:
    for path, entity_key in (
        (SCENARIO_SOURCE_PATH, "scenarios"),
        (PROGRESSION_SOURCE_PATH, "hierarchies"),
        (TIMER_SOURCE_PATH, "timers"),
        (EVIDENCE_SOURCE_PATH, "evidence_types"),
    ):
        manifest = load_manifest(path)
        record_ids = {record["source_id"] for record in manifest["source_records"]}
        referenced = {ref for entity in manifest[entity_key] for ref in entity["source_refs"]}
        assert referenced == record_ids
        assert len(record_ids) == len(manifest["source_records"])
