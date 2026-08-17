"""042_add_med_adherence_achievements — Шаг 12 (ADR-085).

Idempotently inserts the medication-adherence achievements so existing databases
(where SEED_ACHIEVEMENTS already ran and the table is non-empty) also get them.
New installs get the same rows via SEED_ACHIEVEMENTS in app/gamification/achievements.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "0b1c2d3e4f5a"  # 041_add_medication_organizer
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACHIEVEMENTS = [
    {
        "code": "med_first",
        "name": "First Dose",
        "description": "First on-time medication dose",
        "condition_type": "med_adherence",
        "condition_value": 0,
        "color": "emerald",
    },
    {
        "code": "med_adherence_3",
        "name": "Medication Routine",
        "description": "3-day medication adherence streak",
        "condition_type": "med_adherence",
        "condition_value": 3,
        "color": "teal",
    },
    {
        "code": "med_adherence_7",
        "name": "Consistent Care",
        "description": "7-day medication adherence streak",
        "condition_type": "med_adherence",
        "condition_value": 7,
        "color": "emerald",
    },
    {
        "code": "med_adherence_30",
        "name": "Health Guardian",
        "description": "30-day medication adherence streak",
        "condition_type": "med_adherence",
        "condition_value": 30,
        "color": "green",
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    table = sa.table(
        "achievements",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("condition_type", sa.String),
        sa.column("condition_value", sa.Integer),
        sa.column("color", sa.String),
    )
    for data in _ACHIEVEMENTS:
        exists = bind.execute(
            sa.select(table.c.code).where(table.c.code == data["code"])
        ).first()
        if exists is None:
            bind.execute(table.insert().values(**data))


def downgrade() -> None:
    bind = op.get_bind()
    table = sa.table("achievements", sa.column("code", sa.String))
    for data in _ACHIEVEMENTS:
        bind.execute(table.delete().where(table.c.code == data["code"]))
