"""048_add_activity_catalog — сквозной каталог активностей (ADR-091).

Единый универсальный каталог «видов активностей» (как Entity: категории/теги/
описание), на который ссылаются любые модули личного контура:

- ``activity_catalog`` — новая таблица (owner_id NULL = системная запись);
- ``sj_entries.catalog_item_id``      — вид активности в Sexual Journal;
- ``care_routines.catalog_item_id``   — вид процедуры ухода;
- ``lock_slot_rules.catalog_item_id`` — причина/цель окна таймера;
- ``entities.catalog_item_id``        — трекер-задача ссылается на универсальный вид.

Системный сид (owner_id NULL, идемпотентно по name) — стартовый набор видов
активностей по доменам (journal/care/timer/tracker).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a0b1c2d3e4f5"
down_revision: str | None = "f6a7b8c9d0e1"  # 047_add_personal_care
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, description, domains, tags)
_SYSTEM_ITEMS: list[tuple[str, str | None, list[str], list[str]]] = [
    # Sexual Journal (journal)
    ("Массаж", "Расслабляющий или эротический массаж", ["journal", "care", "tracker"], ["touch", "relax"]),
    ("Оральный", "Оральная стимуляция", ["journal"], ["oral"]),
    ("Проникновение", "Вагинальное или анальное проникновение", ["journal"], ["penetration"]),
    ("Совместная мастурбация", "Взаимная мастурбация", ["journal"], ["mutual"]),
    ("Ролевая игра", "Сексуальная ролевая игра", ["journal"], ["roleplay"]),
    ("Связывание", "Бондаж и фиксация", ["journal", "tracker"], ["bondage"]),
    ("Использование устройства", "Активность с chastity-устройством", ["journal", "timer"], ["device"]),
    ("Оргазм-контроль", "Контроль оргазма / tease & denial", ["journal", "tracker"], ["control"]),
    # Personal Care (care)
    ("Уход за лицом", "Очищение, тоники, маски", ["care"], ["face"]),
    ("Уход за телом", "Скрабы, увлажнение, лосьоны", ["care"], ["body"]),
    ("Уход за волосами", "Мытьё, маски, укладка", ["care"], ["hair"]),
    ("Бритьё / депиляция", "Удаление волос", ["care"], ["hair_removal"]),
    ("Маникюр / педикюр", "Уход за ногтями рук и ног", ["care"], ["nails"]),
    ("Массаж", "Процедура массажа", ["care", "tracker"], ["touch"]),
    # Timer windows (timer)
    ("Гигиена", "Окно для гигиенических процедур", ["timer"], ["hygiene"]),
    ("Обслуживание устройства", "Окно для ухода за устройством", ["timer"], ["device"]),
    ("Врач", "Окно по медицинской необходимости", ["timer"], ["health"]),
    ("Поездка", "Окно на время поездки", ["timer"], ["travel"]),
    ("Спорт", "Окно для тренировки", ["timer"], ["sport"]),
    ("Личное время", "Заранее выбранное личное время", ["timer"], ["personal"]),
    ("Сексуальная активность", "Плановая сексуальная активность", ["timer", "journal"], ["sexual"]),
    # Tracker tasks (tracker)
    ("Романтика", "Романтические активности", ["tracker"], ["romance"]),
    ("Разговор", "Глубокий разговор / валидация", ["tracker"], ["communication"]),
    ("Совместный ужин", "Приготовление и совместный приём пищи", ["tracker"], ["dinner"]),
]


def upgrade() -> None:
    op.create_table(
        "activity_catalog",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "category_id",
            sa.Uuid(),
            sa.ForeignKey("activity_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("domains", sa.JSON(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_catalog_category_id", "activity_catalog", ["category_id"])
    op.create_index("ix_activity_catalog_owner_id", "activity_catalog", ["owner_id"])

    # FK reference columns on consumer modules (SET NULL — мягкие ссылки, DATA_LIFECYCLE.md)
    for table in ("sj_entries", "care_routines", "lock_slot_rules", "entities"):
        op.add_column(table, sa.Column("catalog_item_id", sa.Uuid(), nullable=True))

    op.create_foreign_key(
        "fk_sj_entries_catalog_item", "sj_entries", "activity_catalog", ["catalog_item_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_care_routines_catalog_item",
        "care_routines",
        "activity_catalog",
        ["catalog_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_lock_slot_rules_catalog_item",
        "lock_slot_rules",
        "activity_catalog",
        ["catalog_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_entities_catalog_item", "entities", "activity_catalog", ["catalog_item_id"], ["id"], ondelete="SET NULL"
    )

    # System seed (owner_id NULL, idempotent by name)
    bind = op.get_bind()
    for name, description, domains, tags in _SYSTEM_ITEMS:
        exists = bind.execute(
            sa.text("SELECT id FROM activity_catalog WHERE owner_id IS NULL AND name = :n"),
            {"n": name},
        ).fetchone()
        if exists:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO activity_catalog (id, name, description, domains, tags, is_public) "
                "VALUES (:id, :name, :desc, :domains, :tags, false)"
            ),
            {
                "id": str(__import__("uuid").uuid4()),
                "name": name,
                "desc": description,
                "domains": __import__("json").dumps(domains),
                "tags": __import__("json").dumps(tags),
            },
        )


def downgrade() -> None:
    for table in ("sj_entries", "care_routines", "lock_slot_rules", "entities"):
        op.drop_constraint(
            {
                "sj_entries": "fk_sj_entries_catalog_item",
                "care_routines": "fk_care_routines_catalog_item",
                "lock_slot_rules": "fk_lock_slot_rules_catalog_item",
                "entities": "fk_entities_catalog_item",
            }[table],
            table,
            type_="foreignkey",
        )
        op.drop_column(table, "catalog_item_id")

    op.drop_index("ix_activity_catalog_owner_id", table_name="activity_catalog")
    op.drop_index("ix_activity_catalog_category_id", table_name="activity_catalog")
    op.drop_table("activity_catalog")
