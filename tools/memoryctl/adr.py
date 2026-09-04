"""ADR compiler — split legacy ``memory/DECISIONS.md`` into ``docs/adr/`` (MEMORY_IMPLEMENTATION_PLAN.md M2).

Deterministic transform from a single raw source:

- parse the registry table (ADR-001..ADR-NNN) and the detailed sections (``### ADR-NNN — …``);
- emit one ``docs/adr/ADR-NNN.md`` per legacy ADR, preserving the stable ``id``;
- emit a generated ``docs/adr/README.md`` index;
- ``check`` performs the bidirectional gate: every legacy ADR has a file, every
  file maps back to a legacy row, and no ADR id is dropped or invented.

This is a *draft split* of already owner-accepted decisions (not new decisions):
``status`` is carried over from the legacy registry, ``source_refs`` points back
to ``memory/DECISIONS.md``. A human still reviews the compiled bodies.

Commands:
    python -m tools.memoryctl adr compile   # write docs/adr/ADR-*.md + README.md
    python -m tools.memoryctl adr check     # bidirectional verification, no writes
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

VERIFIED_AT = "2026-08-13T00:00:00Z"
LEGACY_SOURCE = "memory/DECISIONS.md"

# Canonical legacy status is russian; english statuses (ADR-172..178 era) and a few
# synonyms are accepted case-insensitively so mixed-format registries still compile.
_STATUS_MAP = {
    "принято": "accepted",
    "принят": "accepted",
    "реализовано": "accepted",
    "отложено": "proposed",
    "отклонено": "rejected",
    "accepted": "accepted",
    "proposed": "proposed",
    "rejected": "rejected",
    "superseded": "superseded",
}

# Provisional decision_type classification for the table-only ADRs (draft).
# Everything not listed here is ``technical``. A human refines these on review.
_DECISION_TYPE_OVERRIDES: dict[int, str] = {
    1: "safety",  # hybrid generation / compliance
    5: "product",  # penalties as product behaviour
    6: "product",  # XP / combos / challenges
    8: "product",  # opt-in
    9: "product",  # task publication
    10: "product",  # achievements board
    13: "product",  # subscriptions
    17: "product",  # content language
    18: "product",  # training
    22: "product",  # body measurements
    23: "product",  # inventory
    29: "safety",  # penalties kept as-is
    32: "product",  # training as separate page
    33: "product",  # secondary modules in main nav
    52: "safety",  # feature flags default off
    62: "product",  # terminology (PD-017)
    63: "product",  # mobile client (PD-018)
    64: "product",  # scaling commitment (PD-019)
}


@dataclass
class LegacyAdr:
    num: int
    date: str
    topic: str
    decision: str
    status: str  # legacy russian status
    body: str | None  # detailed section body (None for table-only rows)


ROW_PREFIX_RE = re.compile(r"^\|\s*ADR-(\d{3,})\s*\|")
# Section headers: canonical is ``### ADR-NNN — Title``; legacy variants use H2 and/or
# a colon separator (``## ADR-161: ...``, ``### ADR-152: ...``). All are accepted.
SECTION_RE = re.compile(r"^#{2,3}\s+ADR-(\d{3,})\s*[—:–]\s*(.+)$")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COMMIT_RE = re.compile(r"(?<![0-9a-f])([0-9a-f]{40})(?![0-9a-f])")


def parse_legacy(text: str) -> dict[int, LegacyAdr]:
    """Parse the DECISIONS.md registry table + detailed sections.

    HTML comment blocks (``<!-- ... -->``) are skipped entirely — they hold retired
    rows and the format contract, and must never become ADRs.
    """
    rows: dict[int, LegacyAdr] = {}
    sections: dict[int, tuple[str, str]] = {}
    section_order: list[int] = []
    current_section: int | None = None
    section_lines: list[str] = []
    in_comment = False

    def flush_section() -> None:
        nonlocal current_section, section_lines
        if current_section is not None and current_section not in rows:
            # orphan section without a table row — still captured for check
            sections.setdefault(current_section, ("", ""))
        current_section = None
        section_lines = []

    for line in text.splitlines():
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        m = ROW_PREFIX_RE.match(line)
        if m:
            num = int(m.group(1))
            cells = [c.strip() for c in line.split("|")]
            status = cells[-2] if len(cells) >= 2 else ""
            # Two row layouts exist:
            #   canonical: | ADR | date | topic | decision… | status |  (date in cell 2)
            #   legacy-6:  | ADR | topic | category | date | commit | status | (date in cell 4)
            date_idx = 2
            if not (len(cells) > 2 and _DATE_RE.match(cells[2])):
                date_idx = 4 if len(cells) > 4 and _DATE_RE.match(cells[4]) else 0
            if date_idx:
                date = cells[date_idx]
                topic = cells[2] if date_idx == 4 else (cells[3] if len(cells) > 3 else "")
                if date_idx == 4:
                    # legacy-6: | ADR | topic | category | date | commit | status |
                    decision_cells = [c for i, c in enumerate(cells[3:-2], start=3) if c and i != date_idx]
                    decision = " | ".join(decision_cells)
                else:  # canonical: | ADR | date | topic | decision… | status |
                    # The decision is authored as ONE cell; literal pipes inside it
                    # (e.g. ``tracker|timer|combined``) reach us as extra fragments
                    # after split('|'). Re-join with the bare pipe to reconstruct
                    # the original value (identity for single-cell rows).
                    decision = "|".join(cells[4:-2]).strip()
            else:  # unrecognized layout — keep a minimal record
                date = ""
                topic = cells[3] if len(cells) > 3 else ""
                decision = ""
            rows[num] = LegacyAdr(
                num=num,
                date=date,
                topic=topic,
                decision=decision,
                status=status,
                body=None,
            )
            continue
        sm = SECTION_RE.match(line)
        if sm:
            flush_section()
            current_section = int(sm.group(1))
            sections[current_section] = (sm.group(2).strip(), "")
            section_order.append(current_section)
            continue
        if current_section is not None:
            section_lines.append(line)
    flush_section()

    # attach detailed bodies to table rows (061-068), keeping header titles
    for num, (_title, _) in sections.items():
        if num in rows:
            # body = everything after the section header line; rebuild from source
            rows[num].body = _extract_section_body(text, num)

    # attach detailed titles when the table topic is less specific
    for num, (title, _) in sections.items():
        if num in rows and rows[num].topic == "":
            rows[num].topic = title

    # Promote section-only ADRs (no table row) into the registry: the section IS the
    # decision record. Date/status come from the body's ``**Date:**``/``**Status:**``
    # lines when present; default status is принято (historical registry default).
    for num, (title, _body) in sections.items():
        if num in rows:
            continue
        date, status = _date_status_from_section(text, num)
        rows[num] = LegacyAdr(
            num=num,
            date=date,
            topic=title,
            decision="",
            status=status,
            body=None,
        )
        rows[num].body = _extract_section_body(text, num)
    return rows


def _date_status_from_section(text: str, num: int) -> tuple[str, str]:
    body = _extract_section_body(text, num) or ""
    date = ""
    status = "принято"
    for line in body.splitlines():
        m = re.match(r"\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", line.strip())
        if m:
            date = m.group(1)
            continue
        m = re.match(r"\*\*Статус:\*\*\s*(.+?)\.?$", line.strip())
        if m:
            status = m.group(1).strip().rstrip(".")
            continue
        m = re.match(r"\*\*Status:\*\*\s*(.+?)\.?$", line.strip())
        if m:
            status = m.group(1).strip().rstrip(".")
    return date, _normalize_section_status(status)


def _normalize_section_status(raw: str) -> str:
    """Map free-form section status lines onto the legacy status vocabulary.

    Sections written by different agents use either a clean status word or an
    implementation report ("✅ Реализовано, 8 новых тестов, ..."). Reports marked
    with a checkmark or containing 'реализован' mean the decision was accepted.
    """
    cleaned = raw.strip().lstrip("✅✔☑").strip()
    key = cleaned.split(",")[0].strip().lower().rstrip(".")
    if key in ("принято", "отложено", "отклонено"):
        return key
    if key in _STATUS_MAP:
        # english/synonym statuses translate back to the legacy vocabulary;
        # 'superseded' has no legacy equivalent and is kept as-is
        return {
            "accepted": "принято",
            "proposed": "отложено",
            "rejected": "отклонено",
        }.get(_STATUS_MAP[key], key)
    if raw.startswith(("✅", "✔", "☑")) or "реализован" in cleaned.lower():
        return "принято"
    return raw


def _extract_section_body(text: str, num: int) -> str | None:
    """Return the raw body of a ``### ADR-NNN — …`` section (without its header)."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        m = SECTION_RE.match(line)
        if m and int(m.group(1)) == num:
            start = i
            break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        # A registry row after a section belongs to the table, not to the
        # preceding ADR body. This matters when detailed sections and rows are
        # interleaved in the legacy DECISIONS.md file.
        if ROW_PREFIX_RE.match(line) or SECTION_RE.match(line) or line.strip() == "---":
            break
        body.append(line)
    # strip leading/trailing blank lines
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body) if body else None


def decision_type(num: int) -> str:
    return _DECISION_TYPE_OVERRIDES.get(num, "technical")


def _implementation_commits(adr: LegacyAdr) -> tuple[str, ...]:
    """Return full commit SHAs explicitly recorded in an ADR's decision text."""
    found: list[str] = []
    for text in (adr.decision, adr.body or ""):
        for sha in _COMMIT_RE.findall(text):
            if sha not in found:
                found.append(sha)
    return tuple(found)


def _implementation_ref(adr: LegacyAdr, sha: str) -> str:
    return f"  - type: git_commit\n    sha: {sha}\n    anchor: ADR-{adr.num:03d}\n    relation: implementation\n"


def _status(num: int, legacy: str) -> str:
    # Compound statuses ("принят, реализован") resolve by their first token.
    key = legacy.strip().lower().rstrip(".").split(",")[0].strip()
    mapped = _STATUS_MAP.get(key)
    if mapped is None:
        raise ValueError(f"ADR-{num:03d}: unknown legacy status {legacy!r}")
    return mapped


def _frontmatter(adr: LegacyAdr, head: str, verified_at: str = VERIFIED_AT) -> str:
    status = _status(adr.num, adr.status)
    accepted_at = f"{adr.date}T00:00:00Z" if (adr.date and status == "accepted") else "null"
    return (
        "---\n"
        "schema_version: memory/v2alpha1\n"
        f"id: ADR-{adr.num:03d}\n"
        "kind: adr\n"
        f"title: {adr.topic or f'ADR-{adr.num:03d}'}\n"
        f"status: {status}\n"
        "authority: technical\n"
        f"decision_type: {decision_type(adr.num)}\n"
        "deciders:\n"
        "  - project-owner\n"
        "owners:\n"
        "  - project-owner\n"
        "scope:\n"
        "  - engineering\n"
        f"accepted_at: {accepted_at}\n"
        "supersedes: []\n"
        "superseded_by: null\n"
        "source_refs:\n"
        f"  - path: {LEGACY_SOURCE}\n"
        f"    anchor: ADR-{adr.num:03d}\n"
        "    relation: origin\n"
        + "".join(_implementation_ref(adr, sha) for sha in _implementation_commits(adr))
        + f"last_verified_at: {verified_at}\n"
        f"last_verified_commit: {head}\n"
        "review_on: source-change\n"
        "---\n"
    )


def _body(adr: LegacyAdr) -> str:
    if adr.body:
        return (
            f"# ADR-{adr.num:03d} — {adr.topic}\n"
            "\n"
            f"{adr.body}\n"
            "\n"
            f"> Source: `{LEGACY_SOURCE}` (legacy registry, section `ADR-{adr.num:03d}`).\n"
            "> Compiled by `memoryctl adr compile` — human review before relying on it.\n"
        )
    legacy_note = "принято" if adr.status == "принято" else adr.status
    return (
        f"# ADR-{adr.num:03d} — {adr.topic}\n"
        "\n"
        f"**Decision:** {adr.decision}\n"
        "\n"
        f"**Status:** {_status(adr.num, adr.status)} (legacy: {legacy_note})\n"
        "\n"
        "> Source: `" + LEGACY_SOURCE + "` (legacy registry, table row only — no detailed section).\n"
        "> Compiled by `memoryctl adr compile` — draft body; human review before relying on it.\n"
    )


def compile_adrs(root: Path, head: str | None = None) -> list[int]:
    """Generate docs/adr/ADR-NNN.md + README.md. Returns sorted ADR numbers."""
    decisions = root / LEGACY_SOURCE
    if not decisions.exists():
        raise FileNotFoundError(f"{LEGACY_SOURCE} not found")
    text = decisions.read_text(encoding="utf-8")
    adrs = parse_legacy(text)
    if not adrs:
        raise ValueError(f"no ADR rows parsed from {LEGACY_SOURCE}")

    if head is None:
        head = _git_head(root) or "0" * 40

    out_dir = root / "docs" / "adr"
    out_dir.mkdir(parents=True, exist_ok=True)

    marker = "Compiled by `memoryctl adr compile`"
    for num in sorted(adrs):
        adr = adrs[num]
        path = out_dir / f"ADR-{num:03d}.md"
        # Preserve verification metadata for unchanged generated ADRs, but never
        # report verification before the ADR date. Explicit implementation SHAs
        # are stronger provenance than the compile snapshot for restored records.
        head_at = VERIFIED_AT
        head_sha = head
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if marker not in existing:
                # Hand-maintained ADR (owner/agent reviewed) — never overwrite.
                continue
            m_at = re.search(r"^last_verified_at:\s*(.+)$", existing, re.M)
            m_sha = re.search(r"^last_verified_commit:\s*([0-9a-f]{40})\s*$", existing, re.M)
            if m_at:
                head_at = m_at.group(1).strip()
            if m_sha:
                head_sha = m_sha.group(1)
        if adr.date:
            head_at = max(head_at, f"{adr.date}T00:00:00Z")
        implementation_commits = _implementation_commits(adr)
        if implementation_commits:
            head_sha = implementation_commits[-1]
        content = _frontmatter(adr, head_sha, verified_at=head_at) + "\n" + _body(adr).rstrip("\n") + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue  # no churn
        path.write_text(content, encoding="utf-8")

    (out_dir / "README.md").write_text(_render_index(sorted(adrs), adrs), encoding="utf-8")
    return sorted(adrs)


def _render_index(nums: list[int], adrs: dict[int, LegacyAdr]) -> str:
    lines = [
        "# ADR index (generated)",
        "",
        "<!-- GENERATED by `memoryctl adr compile` — do not edit. Source: memory/DECISIONS.md -->",
        "",
        "| ID | Дата | Тема | Статус |",
        "| --- | --- | --- | --- |",
    ]
    for num in nums:
        adr = adrs[num]
        lines.append(f"| [ADR-{num:03d}](ADR-{num:03d}.md) | {adr.date} | {adr.topic} | {_status(num, adr.status)} |")
    lines.append("")
    return "\n".join(lines)


def _git_head(root: Path) -> str | None:
    import subprocess

    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True, timeout=30)
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", out) else None


def check_bidirectional(root: Path) -> tuple[bool, list[str]]:
    """Gate: legacy registry ADRs == generated docs/adr files (id set equality)."""
    errors: list[str] = []
    decisions = root / LEGACY_SOURCE
    if not decisions.exists():
        return False, [f"{LEGACY_SOURCE} not found"]
    legacy = set(parse_legacy(decisions.read_text(encoding="utf-8")))
    adr_dir = root / "docs" / "adr"
    if not adr_dir.exists():
        return False, ["docs/adr/ not found — run 'memoryctl adr compile'"]

    generated: set[int] = set()
    for path in sorted(adr_dir.glob("ADR-*.md")):
        m = re.fullmatch(r"ADR-(\d{3,})\.md", path.name)
        if m:
            generated.add(int(m.group(1)))

    missing = sorted(legacy - generated)
    extra = sorted(generated - legacy)
    if missing:
        errors.append(f"legacy ADRs without a generated file: {[f'ADR-{n:03d}' for n in missing]}")
    if extra:
        errors.append(f"generated ADR files with no legacy row: {[f'ADR-{n:03d}' for n in extra]}")
    if not errors:
        errors.append(f"OK: {len(legacy)} ADRs split bidirectionally (legacy == generated)")
    return not (missing or extra), errors
