"""Medication substances, composition and daily-limit flag (ADR-190, phase E).

- med_substances: canonical active-ingredient registry (norm_key unique, INN,
  synonyms, daily_max_*) — grouping/search/replacement key;
- med_variants: pill variants inside one pack (Femoston 2/10: white 1-14 /
  grey 15-28);
- med_components: many-to-many medication <-> substance with amount/unit,
  optional variant link;
- medications.allow_ul_override: explicit permit to exceed daily limits.

Backfill: existing medications.active_ingredient -> one substance + one
component (amount NULL, filled later by the user).

Revision ID: 097_substances_components
Revises: 096_courses_kit_locations
Create Date: 2026-09-04
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "097_substances_components"
down_revision: str | None = "096_courses_kit_locations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NORM_RE = re.compile(r"[^a-zа-я0-9 ]")


def _norm_key(name: str) -> str:
    """Must stay in sync with med_service.normalize_substance (ADR-190 §3.1)."""
    s = name.lower().replace("ё", "е")
    s = _NORM_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _uuid_expr() -> str:
    return "gen_random_uuid()"


def upgrade() -> None:
    op.create_table(
        "med_substances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("norm_key", sa.String(length=200), nullable=False, unique=True),
        sa.Column("inn", sa.String(length=200), nullable=True),
        sa.Column("synonyms", sa.JSON(), nullable=True),
        sa.Column("daily_max_amt", sa.Numeric(), nullable=True),
        sa.Column("daily_max_unit", sa.String(length=10), nullable=True),
        sa.Column("daily_max_note", sa.String(length=300), nullable=True),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "med_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "medication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("count_per_pack", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_med_variants_medication_id", "med_variants", ["medication_id"])
    op.create_table(
        "med_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "medication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("med_variants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "substance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("med_substances.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_med_components_medication_id", "med_components", ["medication_id"])
    op.create_index("ix_med_components_substance_id", "med_components", ["substance_id"])
    op.add_column(
        "medications",
        sa.Column(
            "allow_ul_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ── Data backfill: legacy active_ingredient -> substance + component ──
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, active_ingredient FROM medications "
            "WHERE active_ingredient IS NOT NULL AND btrim(active_ingredient) <> ''"
        )
    ).fetchall()
    seen: dict[str, str] = {}  # norm_key -> substance id
    for med_id, ai in rows:
        ai = ai.strip()
        norm = _norm_key(ai)
        sub_id = seen.get(norm)
        if sub_id is None:
            sub_id = conn.execute(
                sa.text("SELECT id FROM med_substances WHERE norm_key = :nk"),
                {"nk": norm},
            ).scalar_one_or_none()
        if sub_id is None:
            sub_id = conn.execute(
                sa.text(
                    f"INSERT INTO med_substances (id, name, norm_key, inn, synonyms, is_custom) "
                    f"VALUES ({_uuid_expr()}, :nm, :nk, NULL, NULL, false) RETURNING id"
                ),
                {"nm": ai, "nk": norm},
            ).scalar_one()
            seen[norm] = sub_id
        conn.execute(
            sa.text(
                f"INSERT INTO med_components "
                f"(id, medication_id, variant_id, substance_id, amount, unit, sort_order) "
                f"VALUES ({_uuid_expr()}, :mid, NULL, :sid, NULL, NULL, 0) "
                f"ON CONFLICT DO NOTHING"
            ),
            {"mid": med_id, "sid": sub_id},
        )


def downgrade() -> None:
    op.drop_index("ix_med_components_substance_id", table_name="med_components")
    op.drop_index("ix_med_components_medication_id", table_name="med_components")
    op.drop_table("med_components")
    op.drop_index("ix_med_variants_medication_id", table_name="med_variants")
    op.drop_table("med_variants")
    op.drop_table("med_substances")
    op.drop_column("medications", "allow_ul_override")
