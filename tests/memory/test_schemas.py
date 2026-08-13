"""Unit tests for tools.memoryctl.schemas (MEMORY_SCHEMA.md contract)."""

from __future__ import annotations

import pytest

from tools.memoryctl.schemas import (
    ParseError,
    load_document,
    split_frontmatter,
    validate_document,
)


def _doc(tmp_path, text: str, name: str = "page.md"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return load_document(p)


VALID_KNOWLEDGE = """---
schema_version: memory/v2alpha1
id: K-LOCKTIMER-SAFETY-STOP
kind: knowledge
title: Safety stop в LockTimer
status: active
authority: derived
owners:
  - project-owner
scope:
  - locktimer/core
applies_to:
  - app/locktimer/**
tags:
  - safety
source_refs:
  - path: DOCUMENTATION_MAP.md
    anchor: Safety и privacy
    relation: defines
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 0123456789abcdef0123456789abcdef01234567
review_on: source-change
---
# Body
"""


def test_parse_valid_knowledge(tmp_path):
    doc = _doc(tmp_path, VALID_KNOWLEDGE)
    assert doc.has_frontmatter
    assert doc.meta["id"] == "K-LOCKTIMER-SAFETY-STOP"
    assert doc.meta["owners"] == ["project-owner"]
    assert doc.meta["source_refs"][0]["relation"] == "defines"
    assert validate_document(doc) == []


def test_no_frontmatter(tmp_path):
    doc = _doc(tmp_path, "# just a markdown file\n")
    assert not doc.has_frontmatter
    assert validate_document(doc) == []


def test_unclosed_frontmatter_raises(tmp_path):
    text = "---\nschema_version: memory/v2alpha1\nid: K-X\nkind: knowledge\n"
    with pytest.raises(ParseError):
        split_frontmatter(text)


def test_tabs_are_rejected(tmp_path):
    text = "---\nschema_version: memory/v2alpha1\n\tid: K-X\nkind: knowledge\n---\n"
    with pytest.raises(ParseError):
        split_frontmatter(text)


def test_missing_required_field(tmp_path):
    text = "---\nschema_version: memory/v2alpha1\nid: K-X\nkind: knowledge\ntitle: T\n---\n"
    doc = _doc(tmp_path, text)
    errors = validate_document(doc)
    assert any("status" in e for e in errors)
    assert any("authority" in e for e in errors)
    assert any("owners" in e for e in errors)
    assert any("source_refs" in e for e in errors)


def test_invalid_status_for_kind(tmp_path):
    text = VALID_KNOWLEDGE.replace("status: active", "status: accepted")
    doc = _doc(tmp_path, text, "bad_status.md")
    errors = validate_document(doc)
    assert any("invalid status 'accepted' for kind 'knowledge'" in e for e in errors)


def test_invalid_authority(tmp_path):
    text = VALID_KNOWLEDGE.replace("authority: derived", "authority: divine")
    doc = _doc(tmp_path, text, "bad_auth.md")
    errors = validate_document(doc)
    assert any("invalid authority" in e for e in errors)


def test_id_pattern_mismatch(tmp_path):
    text = VALID_KNOWLEDGE.replace("id: K-LOCKTIMER-SAFETY-STOP", "id: locktimer-page")
    doc = _doc(tmp_path, text, "bad_id.md")
    errors = validate_document(doc)
    assert any("does not match pattern" in e for e in errors)


def test_duplicate_id(tmp_path):
    doc_a = _doc(tmp_path, VALID_KNOWLEDGE, "a.md")
    doc_b = _doc(tmp_path, VALID_KNOWLEDGE.replace("# Body", "# Body 2"), "b.md")
    errors = validate_document(doc_b, known_ids={doc_a.meta["id"]})
    assert any("duplicate id" in e for e in errors)


def test_short_verified_commit_rejected(tmp_path):
    text = VALID_KNOWLEDGE.replace("0123456789abcdef0123456789abcdef01234567", "shortsha")
    doc = _doc(tmp_path, text, "short_sha.md")
    errors = validate_document(doc)
    assert any("full 40-hex SHA" in e for e in errors)


def test_accepted_adr_requires_deciders_and_accepted_at(tmp_path):
    text = """---
schema_version: memory/v2alpha1
id: ADR-068
kind: adr
title: Adopt layered project memory v2
status: accepted
authority: technical
owners:
  - project-owner
scope:
  - engineering/memory
decision_type: technical
supersedes: []
superseded_by: null
source_refs:
  - path: docs/memory-rfc/MEMORY_ARCHITECTURE.md
    relation: origin
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 0123456789abcdef0123456789abcdef01234567
review_on: milestone:M3
---
# ADR-068
"""
    doc = _doc(tmp_path, text, "adr.md")
    errors = validate_document(doc)
    assert any("accepted_at" in e for e in errors)
    assert any("deciders" in e for e in errors)


def test_normative_only_for_accepted_adr_or_active_contract(tmp_path):
    text = VALID_KNOWLEDGE.replace("authority: derived", "authority: normative")
    doc = _doc(tmp_path, text, "normative_knowledge.md")
    errors = validate_document(doc)
    assert any("normative" in e for e in errors)


def test_derived_active_requires_source_refs(tmp_path):
    text = VALID_KNOWLEDGE.replace(
        "source_refs:\n  - path: DOCUMENTATION_MAP.md\n    anchor: Safety и privacy\n    relation: defines\n",
        "source_refs: []\n",
    )
    doc = _doc(tmp_path, text, "no_refs.md")
    errors = validate_document(doc)
    assert any("must have source_refs" in e for e in errors)


def test_supersedes_must_be_list(tmp_path):
    text = VALID_KNOWLEDGE.replace("review_on: source-change", "review_on: source-change\nsupersedes: K-OTHER\n")
    doc = _doc(tmp_path, text, "supersedes_str.md")
    errors = validate_document(doc)
    assert any("'supersedes' must be a list" in e for e in errors)


def test_unknown_kind(tmp_path):
    text = VALID_KNOWLEDGE.replace("kind: knowledge", "kind: hologram")
    doc = _doc(tmp_path, text, "unknown_kind.md")
    errors = validate_document(doc)
    assert any("unknown kind" in e for e in errors)


def test_unsupported_schema_version(tmp_path):
    text = VALID_KNOWLEDGE.replace("schema_version: memory/v2alpha1", "schema_version: memory/v2beta1")
    doc = _doc(tmp_path, text, "bad_schema.md")
    errors = validate_document(doc)
    assert any("unsupported schema_version" in e for e in errors)
