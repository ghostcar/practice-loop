"""LLM Generation Pipeline (REFACTORING.md step 7).

Sub-modules:
- generate.py — single + weekly task generation, helpers, get_active_llm_config
- training.py — daily plan generation + day analysis
- diet.py — diet generation + evaluation + training synergy

Re-exports the full public surface of the pre-split ``pipeline.py`` so every
historical import keeps working unchanged:

    from app.llm.pipeline import (
        generate_task, generate_daily_plan, generate_diet,
        call_llm, build_context, TOOLS, ActivityLog, ...
    )

Note on testability: the sub-modules reference ``call_llm``, ``build_context``
and ``get_allowed_ids`` through their source modules at call time
(``app.llm.client`` / ``app.llm.context_builder`` / ``app.llm.validator``),
so tests patch those source modules directly — not this package.
"""

# --- cross-module helpers (were module-level names in the original pipeline.py)
from app.llm.client import call_llm  # noqa: F401
from app.llm.context_builder import (  # noqa: F401
    build_context,
    filter_automation_eligible,
    format_context_abstract,
    format_context_for_prompt,
)

# --- prompt constants
from app.llm.diet_prompts import (  # noqa: F401
    DIET_EVALUATE_SYSTEM,
    DIET_GENERATE_SYSTEM,
    DIET_TRAINING_SYNERGY_SYSTEM,
)

# --- pipeline functions + constants
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
    SYSTEM_PROMPT_TEMPLATE,
    _generate_task_title,
    _resolve_raw_response,
    generate_task,
    generate_weekly_tasks,
    get_active_llm_config,
)
from app.llm.pipeline.health import analyze_labs  # noqa: F401
from app.llm.pipeline.insights import (  # noqa: F401
    analyze_insights,
    build_insights_context,
)
from app.llm.pipeline.templates import (  # noqa: F401
    extract_template_vars,
    generate_from_template,
)
from app.llm.pipeline.training import (  # noqa: F401
    SUBTASK_LIMIT,
    SUBTASK_MAX_LENGTH,
    analyze_training_day,
    generate_daily_plan,
)
from app.llm.repair import JsonRepairError, parse_llm_json  # noqa: F401
from app.llm.tools import TOOLS  # noqa: F401
from app.llm.training_prompts import (  # noqa: F401
    ANALYZE_DAY_SYSTEM,
    PLAN_DAY_SYSTEM,
    SUGGEST_NEXT_DAY_SYSTEM,
)
from app.llm.validator import (  # noqa: F401
    get_allowed_ids,
    validate_llm_response,
    validate_params_against_schema,
)

# --- models (were imported at module level in the original pipeline.py)
from app.models.activity_log import ActivityLog  # noqa: F401
from app.models.body_part import TaskBodyTarget  # noqa: F401
from app.models.diet import (  # noqa: F401
    Diet,
    DietConsumption,
    DietEvaluation,
    DietItem,
    DietTrainingReview,
)
from app.models.llm_config import LLMProviderConfig  # noqa: F401
from app.models.task_inventory import TaskInventoryUsage  # noqa: F401
from app.models.task_location import TaskLocationUsage  # noqa: F401
from app.models.training import TrainingDay  # noqa: F401
