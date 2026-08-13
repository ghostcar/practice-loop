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

_STATUS_MAP = {
    "принято": "accepted",
    "отложено": "proposed",
    "отклонено": "rejected",
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
SECTION_RE = re.compile(r"^###\s+ADR-(\d{3,})\s+—\s+(.+)$")


def parse_legacy(text: str) -> dict[int, LegacyAdr]:
    """Parse the DECISIONS.md registry table + detailed sections."""
    rows: dict[int, LegacyAdr] = {}
    sections: dict[int, tuple[str, str]] = {}
    section_order: list[int] = []
    current_section: int | None = None
    section_lines: list[str] = []

    def flush_section() -> None:
        nonlocal current_section, section_lines
        if current_section is not None and current_section not in rows:
            # orphan section without a table row — still captured for check
            sections.setdefault(current_section, ("", ""))
        current_section = None
        section_lines = []

    for line in text.splitlines():
        m = ROW_PREFIX_RE.match(line)
        if m:
            num = int(m.group(1))
            cells = [c.strip() for c in line.split("|")]
            # cells = ['', 'ADR-NNN', date, topic, decision…, status, '']
            # decision may itself contain '|' (e.g. ADR-048), so rejoin the middle cells.
            date = cells[2] if len(cells) > 2 else ""
            topic = cells[3] if len(cells) > 3 else ""
            status = cells[-2] if len(cells) >= 2 else ""
            decision = "|".join(c for c in cells[4:-2]) if len(cells) > 5 else ""
            rows[num] = LegacyAdr(
                num=num,
                date=date,
                topic=topic,
                decision=decision,
                status=status,
                body=None,
            )
            continue
        m = SECTION_RE.match(line)
        if m:
            flush_section()
            current_section = int(m.group(1))
            sections[current_section] = (m.group(2).strip(), "")
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
    return rows


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
        if SECTION_RE.match(line) or line.strip() == "---":
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


def _status(num: int, legacy: str) -> str:
    mapped = _STATUS_MAP.get(legacy.strip())
    if mapped is None:
        raise ValueError(f"ADR-{num:03d}: unknown legacy status {legacy!r}")
    return mapped


def _frontmatter(adr: LegacyAdr, head: str) -> str:
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
        f"last_verified_at: {VERIFIED_AT}\n"
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

    for num in sorted(adrs):
        adr = adrs[num]
        path = out_dir / f"ADR-{num:03d}.md"
        path.write_text(_frontmatter(adr, head) + "\n" + _body(adr) + "\n", encoding="utf-8")

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
