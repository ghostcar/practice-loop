"""add activity categories, task model evolution, status machine

Revision ID: 022
Revises: 021
Create Date: 2026-08-11

Phase 1 (Session 58) — ADR-035/036/037/038/040:

1. activity_categories table (ADR-035) — hierarchical catalog categories.
2. entities → Activity evolution: slug, short_title, category_id FK, role_tags,
   task_template, updated_at, penalty_enabled (ADR-035/036/038).
3. activity_logs → ActivityTask evolution: title_override, scheduled_at,
   planned_comment, completion_comment, actual_parameters, updated_at;
   strict status enum — legacy values remapped pending→planned,
   interrupted→stopped (ADR-036/040).
4. activity_task_history — status transition audit journal (ADR-040).
5. activity_sessions: title, notes, planned_start_at, planned_end_at,
   accepted_at (ADR-037).

Non-destructive: existing rows are preserved and mapped; downgrade restores
legacy status values.
"""

import re
import uuid

import sqlalchemy as sa

from alembic import op

revision: str = "022"
down_revision: str | None = "021"
branch_labels = None
depends_on = None

# --- lightweight transliteration for slug generation (RU → EN) ---

_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def _slugify(text: str) -> str:
    lowered = text.lower().strip()
    out = []
    for ch in lowered:
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    return slug[:100] or "category"


def upgrade() -> None:
    bind = op.get_bind()

    # 1. activity_categories ------------------------------------------------
    op.create_table(
        "activity_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["activity_categories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_categories_slug", "activity_categories", ["slug"], unique=True)
    op.create_index("ix_activity_categories_parent_id", "activity_categories", ["parent_id"])

    # 2. entities evolution --------------------------------------------------
    op.add_column("entities", sa.Column("slug", sa.String(length=200), nullable=True))
    op.create_index("ix_entities_slug", "entities", ["slug"])
    op.add_column("entities", sa.Column("short_title", sa.String(length=200), nullable=True))
    op.add_column("entities", sa.Column("category_id", sa.Uuid(), nullable=True))
    op.create_index("ix_entities_category_id", "entities", ["category_id"])
    op.add_column("entities", sa.Column("role_tags", sa.JSON(), nullable=True))
    op.add_column("entities", sa.Column("task_template", sa.JSON(), nullable=True))
    op.add_column(
        "entities",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column("penalty_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_foreign_key(
        "fk_entities_category_id",
        "entities",
        "activity_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Backfill categories from legacy string values (non-destructive).
    rows = bind.execute(sa.text("SELECT DISTINCT category FROM entities WHERE category IS NOT NULL")).fetchall()
    for (cat_name,) in rows:
        cat_name = str(cat_name).strip()
        if not cat_name:
            continue
        cat_id = str(uuid.uuid4())
        slug = _slugify(cat_name)
        existing = bind.execute(sa.text("SELECT id FROM activity_categories WHERE slug = :s"), {"s": slug}).fetchone()
        if existing:
            cat_id = str(existing[0])
        else:
            bind.execute(
                sa.text(
                    "INSERT INTO activity_categories (id, slug, title, sort_order, is_active) "
                    "VALUES (:id, :slug, :title, 0, true)"
                ),
                {"id": cat_id, "slug": slug, "title": cat_name},
            )
        bind.execute(
            sa.text("UPDATE entities SET category_id = :cid WHERE category = :c AND category_id IS NULL"),
            {"cid": cat_id, "c": cat_name},
        )

    # 3. activity_logs evolution + status remap ------------------------------
    op.add_column("activity_logs", sa.Column("title_override", sa.String(length=500), nullable=True))
    op.add_column("activity_logs", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_activity_logs_scheduled_at", "activity_logs", ["scheduled_at"])
    op.add_column("activity_logs", sa.Column("actual_parameters", sa.JSON(), nullable=True))
    op.add_column("activity_logs", sa.Column("planned_comment", sa.Text(), nullable=True))
    op.add_column("activity_logs", sa.Column("completion_comment", sa.Text(), nullable=True))
    op.add_column(
        "activity_logs",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    # Strict enum: pending→planned, interrupted→stopped (ADR-040).
    bind.execute(sa.text("UPDATE activity_logs SET status = 'planned' WHERE status = 'pending'"))
    bind.execute(sa.text("UPDATE activity_logs SET status = 'stopped' WHERE status = 'interrupted'"))
    # NOTE: op.alter_column is PostgreSQL-only (SQLite lacks ALTER COLUMN TYPE);
    # migrations are run against PG15 in prod/deploy — dev/tests use create_all.
    op.alter_column("activity_logs", "status", type_=sa.String(length=30), existing_type=sa.String(length=20))

    # 4. activity_task_history (audit journal) --------------------------------
    op.create_table(
        "activity_task_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=True),
        sa.Column("new_status", sa.String(length=30), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("parameter_snapshot", sa.JSON(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["activity_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_task_history_task_id", "activity_task_history", ["task_id"])

    # 5. activity_sessions evolution (ADR-037) --------------------------------
    op.add_column("activity_sessions", sa.Column("title", sa.String(length=200), nullable=True))
    op.add_column("activity_sessions", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("activity_sessions", sa.Column("planned_start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("activity_sessions", sa.Column("planned_end_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("activity_sessions", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()

    # Restore legacy status values.
    bind.execute(sa.text("UPDATE activity_logs SET status = 'pending' WHERE status = 'planned'"))
    bind.execute(sa.text("UPDATE activity_logs SET status = 'interrupted' WHERE status = 'stopped'"))
    op.alter_column("activity_logs", "status", type_=sa.String(length=20), existing_type=sa.String(length=30))

    op.drop_column("activity_sessions", "accepted_at")
    op.drop_column("activity_sessions", "planned_end_at")
    op.drop_column("activity_sessions", "planned_start_at")
    op.drop_column("activity_sessions", "notes")
    op.drop_column("activity_sessions", "title")

    op.drop_index("ix_activity_task_history_task_id", table_name="activity_task_history")
    op.drop_table("activity_task_history")

    op.drop_column("activity_logs", "updated_at")
    op.drop_column("activity_logs", "completion_comment")
    op.drop_column("activity_logs", "planned_comment")
    op.drop_column("activity_logs", "actual_parameters")
    op.drop_index("ix_activity_logs_scheduled_at", table_name="activity_logs")
    op.drop_column("activity_logs", "scheduled_at")
    op.drop_column("activity_logs", "title_override")

    op.drop_constraint("fk_entities_category_id", "entities", type_="foreignkey")
    op.drop_column("entities", "penalty_enabled")
    op.drop_column("entities", "updated_at")
    op.drop_column("entities", "task_template")
    op.drop_column("entities", "role_tags")
    op.drop_index("ix_entities_category_id", table_name="entities")
    op.drop_column("entities", "category_id")
    op.drop_column("entities", "short_title")
    op.drop_index("ix_entities_slug", table_name="entities")
    op.drop_column("entities", "slug")

    op.drop_index("ix_activity_categories_parent_id", table_name="activity_categories")
    op.drop_index("ix_activity_categories_slug", table_name="activity_categories")
    op.drop_table("activity_categories")
