---
schema_version: memory/v2alpha1
id: C-LLM
kind: contract
title: LLM pipeline — domain contract
status: active
authority: technical
owners:
  - project-owner
scope:
  - llm
source_refs:
  - path: AGENTS.md
    relation: origin
  - path: docs/adr/ADR-002.md
    relation: supports
  - path: docs/adr/ADR-030.md
    relation: supports
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# LLM pipeline — domain contract

## Кратко

Гибридная генерация: каталог наполняют админ/пользователи, пользователь отмечает допустимые
задачи (опт-ин), LLM выбирает задачу и параметры из допустимого набора. LLM не генерирует
откровенный контент и не является источником истины.

## Инварианты

- Никакого обхода safety-фильтров и кодирования контента для сокрытия от LLM (ToS-риск).
- BYOK: ключи шифруются отдельным credentials key; провайдеры Omniroute (default)/Groq/OpenRouter.
- Режимы full (видит названия) и abstract (opaque IDs) — ADR-030.
- Обработка ответа: json.loads → json_repair → regex; после 3 неудач — ошибка + «Повторить».
- Usage-метрики хранятся всегда; raw_llm_response опционально (ADR-034).
- Статус машины и параметры валидируются Pydantic (без eval); actual_parameters против схемы.

## Границы

- OCR/LLM-верификация кодов — только подсказка, не источник истины (PD-014).

## Failure modes

- Weekly planner принимает произвольную дату (P1-2 аудита): валидировать даты/полноту до записи.
- Блокирующие операции в event loop — файлы/Pillow через thread pool (P2-2).

## Проверка

- `pytest tests/test_llm_*.py tests/test_phase2_task_flows.py`.
