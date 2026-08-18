"""Dry-run importer for the P1 18+ catalog (ADR-105).

Projects the owner-reviewed foundation manifest (7 cards) and the editorial
candidates manifest (34 cards) into ``entities`` rows with a typed
``safety_contract`` JSONB and ``content_status``, then either prints a read-only
plan (default) or applies it behind an explicit import gate.

Owner decisions (2026-08-18):
- import **everything** (foundation + all 34 candidates), preserving each
  card's own ``automation_allowed``/``risk_level``;
- ``content_status`` stamped on every imported entity is ``approved``.

Gate (ADR-105): a production write is refused unless **every** source manifest
sets ``import_allowed=true`` AND the caller passes ``--apply --yes`` with an
explicit ``--database-url``.  All manifests currently ship ``import_allowed=false``,
so this tool is read-only until the owner flips the gate for the separate
production-import step.

Usage:
    # read-only plan (no DB)
    python -m tools.adult_catalog_import
    python -m tools.adult_catalog_import --manifest-dir data/seed

    # gated apply (refused while import_allowed=false)
    python -m tools.adult_catalog_import --apply --yes \
        --database-url postgresql+asyncpg://user:pass@host:5432/db
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST_DIR = Path("data/seed")
FOUNDATION_FILENAME = "adult_activity_foundation.v1.json"
CANDIDATES_FILENAME = "adult_activity_editorial_candidates.v1.json"
SOURCE_INVENTORY_FILENAME = "adult_activity_source_inventory.v1.json"

SAFETY_CONTRACT_VERSION = "adult-safety-contract/v1"
IMPORT_CONTENT_STATUS = "approved"  # owner decision: stamp every imported entity


def _load(path: Path) -> dict[str, Any]:
    from tools.adult_catalog_manifest import load_manifest

    return load_manifest(path)


def build_foundation_contract(card: dict[str, Any]) -> dict[str, Any]:
    """Project a foundation card into a typed safety contract (lossless)."""
    return {
        "schema_version": SAFETY_CONTRACT_VERSION,
        "kind": "foundation",
        "content_kind": card.get("content_kind"),
        "participants": card.get("participants"),
        "eligibility": card.get("eligibility"),
        "risk": card.get("risk"),
        "parameters": card.get("parameters"),
        "requirements": card.get("requirements"),
        "safety": card.get("safety"),
        "evidence_policy": card.get("evidence_policy"),
        "gamification": card.get("gamification"),
        "source": card.get("source"),
    }


def build_candidate_contract(card: dict[str, Any]) -> dict[str, Any]:
    """Project an editorial candidate into a typed safety contract.

    Candidates carry fewer structured fields than foundation cards; the absent
    safety sections are filled with the catalog-wide safe defaults (adult-only,
    explicit opt-in, per-session check-in, media never required, no penalties).
    """
    return {
        "schema_version": SAFETY_CONTRACT_VERSION,
        "kind": "editorial_candidate",
        "content_kind": card.get("content_kind"),
        "eligibility": {
            "adult_only": True,
            "explicit_opt_in_required": True,
            "session_checkin_required": True,
        },
        "risk": {"level": card.get("risk_level"), "automation_allowed": False},
        "parameters": card.get("proposed_parameters"),
        "required_controls": card.get("required_controls"),
        "evidence_policy": {"media_required": False},
        "gamification": {"penalty_enabled": False},
        "source": {"kind": "editorial_candidate", "source_refs": card.get("source_refs")},
    }


def _entity_fields(
    *,
    slug: str,
    title: dict[str, str],
    category: str,
    tags: list[str] | None,
    role_tags: list[str] | None,
    risk_level: str,
    params_schema: dict[str, Any] | None,
    safety_contract: dict[str, Any],
    automation_allowed: bool,
) -> dict[str, Any]:
    """Normalize a card into Entity constructor kwargs."""
    return {
        "type": "one_time",
        "real_name": title["ru"],
        "short_title": title["en"],
        "slug": slug,
        "category": category,
        "tags": tags,
        "role_tags": role_tags,
        "risk_level": risk_level,
        "penalty_enabled": False,
        "params_schema": params_schema,
        "safety_contract": safety_contract,
        "automation_allowed": automation_allowed,
        "adult_only": True,
        "content_status": IMPORT_CONTENT_STATUS,
        "content_version": 1,
        "is_public": True,
        "owner_id": None,  # system catalog
        "author_id": None,
    }


def _foundation_entity(card: dict[str, Any]) -> dict[str, Any]:
    contract = build_foundation_contract(card)
    return _entity_fields(
        slug=card["slug"],
        title=card["title"],
        category=card["category"],
        tags=card.get("tags"),
        role_tags=card.get("role_tags"),
        risk_level=card["risk"]["level"],
        params_schema=card.get("parameters"),
        safety_contract=contract,
        automation_allowed=bool(card["risk"].get("automation_allowed", False)),
    )


def _candidate_entity(card: dict[str, Any]) -> dict[str, Any]:
    contract = build_candidate_contract(card)
    return _entity_fields(
        slug=card["slug"],
        title=card["title"],
        category=card["category"],
        tags=None,
        role_tags=None,
        risk_level=card["risk_level"],
        params_schema=card.get("proposed_parameters"),
        safety_contract=contract,
        automation_allowed=bool(card.get("automation_allowed", False)),
    )


def build_plan(
    foundation: dict[str, Any],
    candidates: dict[str, Any],
) -> dict[str, Any]:
    """Build the full import plan: gate status + normalized entity rows."""
    entities: list[dict[str, Any]] = [
        _foundation_entity(card) for card in foundation.get("cards", [])
    ] + [_candidate_entity(card) for card in candidates.get("cards", [])]

    return {
        "gate": {
            "foundation_import_allowed": foundation.get("import_allowed"),
            "candidates_import_allowed": candidates.get("import_allowed"),
        },
        "entities": entities,
    }


def validate_plan(plan: dict[str, Any]) -> list[str]:
    """Invariants that must hold before the plan can be applied."""
    errors: list[str] = []
    entities = plan["entities"]
    slugs = [entity["slug"] for entity in entities]
    if len(slugs) != len(set(slugs)):
        errors.append("duplicate slugs in import plan")

    for index, entity in enumerate(entities):
        prefix = f"entities[{index}]"
        if entity["adult_only"] is not True:
            errors.append(f"{prefix}.adult_only must be true")
        if entity["content_status"] != IMPORT_CONTENT_STATUS:
            errors.append(f"{prefix}.content_status must be {IMPORT_CONTENT_STATUS!r}")
        if entity["risk_level"] not in {"low", "elevated"}:
            errors.append(f"{prefix}.risk_level must be low or elevated")
        contract = entity["safety_contract"]
        if contract.get("schema_version") != SAFETY_CONTRACT_VERSION:
            errors.append(f"{prefix}.safety_contract has wrong schema_version")
        evidence = contract.get("evidence_policy") or {}
        if evidence.get("media_required") is not False:
            errors.append(f"{prefix} must not require media evidence")
        gamification = contract.get("gamification") or {}
        if gamification.get("penalty_enabled") is not False:
            errors.append(f"{prefix} must not enable penalties")
        risk = contract.get("risk") or {}
        if risk.get("level") != entity["risk_level"]:
            errors.append(f"{prefix} risk level mismatch between column and contract")
        if bool(risk.get("automation_allowed")) != bool(entity["automation_allowed"]):
            errors.append(f"{prefix} automation_allowed mismatch between column and contract")
        if entity["risk_level"] == "elevated" and entity["automation_allowed"]:
            errors.append(f"{prefix} elevated cards must keep automation off")
    return errors


def _plan_summary(plan: dict[str, Any]) -> str:
    entities = plan["entities"]
    by_risk: dict[str, int] = {}
    by_auto: dict[str, int] = {"auto": 0, "manual": 0}
    for entity in entities:
        by_risk[entity["risk_level"]] = by_risk.get(entity["risk_level"], 0) + 1
        key = "auto" if entity["automation_allowed"] else "manual"
        by_auto[key] += 1
    return (
        f"entities={len(entities)} "
        f"risks={by_risk} "
        f"automation={by_auto}"
    )


def render_plan(plan: dict[str, Any]) -> str:
    """Human-readable dry-run report (read-only)."""
    gate = plan["gate"]
    lines = [
        "P1 18+ catalog import — dry-run",
        f"gate.foundation_import_allowed={gate['foundation_import_allowed']}",
        f"gate.candidates_import_allowed={gate['candidates_import_allowed']}",
        _plan_summary(plan),
        f"content_status={IMPORT_CONTENT_STATUS}",
        "",
    ]
    lines.extend(
        f"- {entity['slug']} [{entity['risk_level']}] "
        f"auto={entity['automation_allowed']} {entity['real_name']}"
        for entity in plan["entities"]
    )
    return "\n".join(lines)


async def apply_plan(database_url: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Write the plan to ``entities``. Idempotent by slug; skips existing rows.

    Lazy imports keep the read-only path free of DB driver requirements.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    # Import all model modules so the mapper registry resolves Entity's
    # relationships and FK target tables (User / ActivityCategory /
    # UserEntityOptIn / ActivityCatalogItem).
    import app.models.catalog  # noqa: F401
    import app.models.category  # noqa: F401
    import app.models.opt_in  # noqa: F401
    import app.models.user  # noqa: F401
    from app.models.entity import Entity

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    imported = skipped = 0
    async with factory() as db:
        for entity_fields in plan["entities"]:
            existing = await db.execute(
                select(Entity.id).where(Entity.slug == entity_fields["slug"]).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue
            db.add(Entity(**entity_fields))
            imported += 1
        await db.commit()
    await engine.dispose()
    return {"status": "ok", "imported": imported, "skipped": skipped}


def _gate_error(plan: dict[str, Any]) -> str | None:
    gate = plan["gate"]
    blockers = [
        name
        for name, allowed in gate.items()
        if allowed is not True
    ]
    if blockers:
        return (
            "import gate closed: the following manifests do not set "
            f"import_allowed=true — {', '.join(blockers)}. "
            "Flip the gate explicitly before a production import (ADR-105)."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run importer for the P1 18+ catalog")
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    parser.add_argument("--apply", action="store_true", help="write to entities (gated)")
    parser.add_argument("--yes", action="store_true", help="confirm a gated production write")
    parser.add_argument("--database-url", default=None, help="PostgreSQL connection string")
    args = parser.parse_args(argv)

    foundation = _load(args.manifest_dir / FOUNDATION_FILENAME)
    candidates = _load(args.manifest_dir / CANDIDATES_FILENAME)
    source_inventory = _load(args.manifest_dir / SOURCE_INVENTORY_FILENAME)

    # Lint first — refuse to plan from invalid manifests.
    from tools.adult_catalog_manifest import (
        lint_editorial_candidates,
        lint_manifest,
        lint_source_inventory,
    )

    source_ids = {record["source_id"] for record in source_inventory.get("records", [])}
    errors = (
        lint_manifest(foundation)
        + lint_editorial_candidates(candidates, source_ids)
        + lint_source_inventory(source_inventory)
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    plan = build_plan(foundation, candidates)
    plan_errors = validate_plan(plan)
    if plan_errors:
        for error in plan_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if not args.apply:
        print(render_plan(plan))
        print("\nRead-only dry-run complete. Pass --apply --yes --database-url ... to import.")
        return 0

    gate_error = _gate_error(plan)
    if gate_error:
        print(f"ERROR: {gate_error}", file=sys.stderr)
        return 1
    if not args.yes:
        print("ERROR: --apply requires --yes to confirm a production write.", file=sys.stderr)
        return 1
    if not args.database_url:
        print("ERROR: --apply requires --database-url.", file=sys.stderr)
        return 1

    result = asyncio.run(apply_plan(args.database_url, plan))
    print(
        f"imported={result['imported']} skipped={result['skipped']} "
        f"(slug idempotent, content_status={IMPORT_CONTENT_STATUS})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
