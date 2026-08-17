"""LLM prompts for Personal Insights (Шаг 17, ADR-093).

Кросс-модульный анализ личных данных (PRODUCT_OVERVIEW §12): тенденции и связи
между активностями, таймером, журналом, состоянием, уходом, тренировками и
диетами. Анализ запускается явно, показывает использованные данные и **не
объявляет корреляцию причиной**. Пользователь исключает раздел/период выбором.

Режим ``prefs.llm_mode`` (ADR-087):
- ``safe`` (default): нейтральные фактические наблюдения, без советов;
- ``expanded``: допускаются практические рекомендации.

Комплаенс: режим не обходит safety-фильтры и не маскирует контент.
"""

from __future__ import annotations

# JSON shape:
# {
#   "summary": "short overall summary of the period",
#   "findings": [
#     {
#       "section": "tracker",          // one of tracker/timer/journal/health/care/training/diet
#       "title": "short title",
#       "summary": "observation (trend, pattern, or cross-section link)",
#       "used_data": ["data point used", "another data point"]
#     }
#   ]
# }

INSIGHTS_SYSTEM = """You are a personal analytics assistant reviewing the owner's own data.

The owner selected specific sections and a date period and explicitly asked for
an analysis. Work ONLY with the data provided below — do not invent numbers.

Rules:
- Identify trends and patterns within each section, and plausible connections
  between sections (e.g. activity completion vs. sleep, care routine vs. mood).
- NEVER state that a correlation is a cause. Use careful wording: "associated
  with", "tends to coincide with", "may relate to" — never "caused by".
- For every finding, list the concrete data points you used (used_data), so the
  owner can see exactly what was analyzed.
- Only mention a section if it had enough data to say something meaningful;
  otherwise skip it.
- Keep every string concise (1-2 sentences). Language: {locale}.

Respond ONLY with valid JSON matching exactly this schema:
{{
  "summary": "short overall summary of the period",
  "findings": [
    {{
      "section": "tracker",
      "title": "short title",
      "summary": "observation",
      "used_data": ["data point used"]
    }}
  ]
}}
"""

# Sections the context builder can feed (kept in sync with INSIGHT_SECTIONS).
INSIGHT_SECTION_LABELS = {
    "tracker": "Activities (Tracker)",
    "timer": "Chastity Timer",
    "journal": "Sexual Journal",
    "health": "Health & Cycle",
    "care": "Personal Care",
    "training": "Training",
    "diet": "Diet",
}
