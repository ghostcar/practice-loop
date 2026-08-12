"""LLM Generation Pipeline (REFACTORING.md step 7).

Sub-modules:
- generate.py — single + weekly task generation, helpers, get_active_llm_config
- training.py — daily plan generation + day analysis
- diet.py — diet generation + evaluation + training synergy

Re-exports all public names so existing imports and monkeypatches remain unchanged:
    from app.llm.pipeline import generate_task, call_llm, ...
"""

# Re-export sub-module contents (backward compat for tests that monkeypatch these).
from app.llm.client import call_llm  # noqa: F401
from app.llm.context_builder import build_context  # noqa: F401
from app.llm.pipeline.diet import (  # noqa: F401
    DIET_DESC_MAX,
    DIET_ITEM_LIMIT,
    DIET_NAME_MAX,
    analyze_diet_training_synergy,
    evaluate_diet,
    generate_diet,
)
from app.llm.pipeline.generate import (  # noqa: F401
    MAX_RETRIES,
    RAW_RESPONSE_TTL_DAYS,
    _generate_task_title,
    _resolve_raw_response,
    generate_task,
    generate_weekly_tasks,
    get_active_llm_config,
)
from app.llm.pipeline.training import (  # noqa: F401
    SUBTASK_LIMIT,
    SUBTASK_MAX_LENGTH,
    analyze_training_day,
    generate_daily_plan,
)
from app.llm.validator import get_allowed_ids  # noqa: F401
