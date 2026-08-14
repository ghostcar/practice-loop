"""Prompt Library (ADR-070, Step 6) — единый реестр типовых системных промптов.

Каждый промпт описан метаданными (ключ, назначение, категория, когда
использовать) и системным промптом. Существующие константы
(SYSTEM_PROMPT_TEMPLATE, PLAN_DAY_SYSTEM, DIET_GENERATE_SYSTEM, …) остаются
экспортируемыми из своих модулей — здесь они **переиспользуются**, а не
дублируются, чтобы не было двух источников истины.

Пользовательские приватные промпты живут в таблице ``prompt_templates``
(см. app/api/prompt_templates.py) и могут создаваться «из библиотеки».
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.diet_prompts import (
    DIET_EVALUATE_SYSTEM,
    DIET_GENERATE_SYSTEM,
    DIET_TRAINING_SYNERGY_SYSTEM,
)
from app.llm.pipeline.generate import SYSTEM_PROMPT_TEMPLATE
from app.llm.training_prompts import (
    ANALYZE_DAY_SYSTEM,
    PLAN_DAY_SYSTEM,
    SUGGEST_NEXT_DAY_SYSTEM,
)


@dataclass(frozen=True)
class PromptDefinition:
    """Описание типового промпта в библиотеке."""

    key: str  # machine key, e.g. "task.single"
    category: str  # "task" | "training" | "diet" | "analysis"
    title_key: str  # i18n key for the title
    description_key: str  # i18n key for the description
    system_prompt: str
    # Переменные, которые подставляются в system_prompt (format()) при использовании.
    format_vars: tuple[str, ...] = field(default_factory=tuple)
    # Можно ли порождать приватный шаблон из этого промпта.
    template_source: bool = True


# Собираем реестр из существующих констант — единый источник истины.
PROMPT_LIBRARY: tuple[PromptDefinition, ...] = (
    PromptDefinition(
        key="task.single",
        category="task",
        title_key="pl_task_single_title",
        description_key="pl_task_single_desc",
        system_prompt=SYSTEM_PROMPT_TEMPLATE,
        format_vars=("locale",),
    ),
    PromptDefinition(
        key="task.weekly",
        category="task",
        title_key="pl_task_weekly_title",
        description_key="pl_task_weekly_desc",
        system_prompt=(
            "You are a weekly activity planner. Distribute activities across the upcoming days. "
            "Respect calendar windows, align with diet goals, vary activities. "
            "Output in {locale}.\n\n"
            'Response format (JSON): {"plan": [{"date": "YYYY-MM-DD", "entity_id": "<uuid>",'
            '"entity_name": "<name>", "params": {...}, "reasoning": "..."}]}'
        ),
        format_vars=("locale",),
    ),
    PromptDefinition(
        key="training.plan_day",
        category="training",
        title_key="pl_training_plan_title",
        description_key="pl_training_plan_desc",
        system_prompt=PLAN_DAY_SYSTEM,
        format_vars=("locale",),
    ),
    PromptDefinition(
        key="training.analyze_day",
        category="training",
        title_key="pl_training_analyze_title",
        description_key="pl_training_analyze_desc",
        system_prompt=ANALYZE_DAY_SYSTEM,
        format_vars=("locale",),
    ),
    PromptDefinition(
        key="training.suggest_next",
        category="training",
        title_key="pl_training_suggest_title",
        description_key="pl_training_suggest_desc",
        system_prompt=SUGGEST_NEXT_DAY_SYSTEM,
        format_vars=("locale",),
    ),
    PromptDefinition(
        key="diet.generate",
        category="diet",
        title_key="pl_diet_generate_title",
        description_key="pl_diet_generate_desc",
        system_prompt=DIET_GENERATE_SYSTEM,
        format_vars=("locale",),
    ),
    PromptDefinition(
        key="diet.evaluate",
        category="diet",
        title_key="pl_diet_evaluate_title",
        description_key="pl_diet_evaluate_desc",
        system_prompt=DIET_EVALUATE_SYSTEM,
        format_vars=("locale",),
    ),
    PromptDefinition(
        key="diet.synergy",
        category="diet",
        title_key="pl_diet_synergy_title",
        description_key="pl_diet_synergy_desc",
        system_prompt=DIET_TRAINING_SYNERGY_SYSTEM,
        format_vars=("locale",),
    ),
)

_PROMPTS_BY_KEY: dict[str, PromptDefinition] = {p.key: p for p in PROMPT_LIBRARY}


def get_prompt(key: str) -> PromptDefinition | None:
    """Lookup a prompt definition by machine key."""
    return _PROMPTS_BY_KEY.get(key)


def list_prompts(category: str | None = None) -> list[PromptDefinition]:
    """List library prompts, optionally filtered by category."""
    prompts = list(PROMPT_LIBRARY)
    if category:
        prompts = [p for p in prompts if p.category == category]
    return prompts


def prompt_categories() -> list[str]:
    """Sorted list of available categories."""
    return sorted({p.category for p in PROMPT_LIBRARY})


def render_system_prompt(prompt: PromptDefinition, **kwargs: object) -> str:
    """Format a library prompt's system_prompt with the given variables.

    Missing variables are left as-is (safe when a prompt has optional vars).
    """
    if not kwargs:
        return prompt.system_prompt
    try:
        return prompt.system_prompt.format(**{k: v for k, v in kwargs.items() if k in prompt.format_vars})
    except (KeyError, IndexError, ValueError):
        return prompt.system_prompt
