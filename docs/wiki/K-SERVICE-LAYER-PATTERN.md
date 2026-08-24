---
schema_version: memory/v2alpha1
id: K-SERVICE-LAYER-PATTERN
kind: knowledge
title: Thin Routes — Service Layer Pattern (ADR-161/162/163)
status: active
authority: technical
owners:
  - project-owner
scope:
  - engineering
created_at: 2026-08-24T00:00:00Z
source_refs:
  - path: docs/adr/ADR-161.md
  - path: docs/adr/ADR-162.md
  - path: docs/adr/ADR-163.md
  - path: AGENTS.md
    anchor: Thin Routes
last_verified_at: 2026-08-24T00:00:00Z
last_verified_commit: 7f5089375b6c4e19e1be6e75f6e7c3e0e6e3e1e7
review_on: source-change
---

# Thin Routes — Service Layer Pattern

## Паттерн

HTTP-хендлеры в `app/api/` — тонкие обёртки (3-10 строк):
```
try:
    result = await svc.do_something(db, user_id=user.id, ...)
except NotFoundError as e:
    raise HTTPException(404, str(e)) from None
except ValueError as e:
    raise HTTPException(400, str(e)) from None
return redirect_or_json(result)
```

Бизнес-логика живёт в `app/services/*_service.py`.

## Реализованные сервисы

| Сервис | Роутер | Было | Стало | Service |
|---|---|---|---|---|
| `care_service.py` | `care.py` | 1417 | 478 | 1161 |
| `med_service.py` | `medication.py` | 1303 | 536 | 1069 |
| `health_service.py` | `health.py` | 970 | 385 | 770 |

**Итого:** 3690→1399 строк в роутерах (−62%).

## Исключения

- `NotFoundError` (from `app/services/errors.py`) → HTTP 404 (entity not found / not owned)
- `ValueError` → HTTP 400 (validation error)
- HTML form handlers: `except (ValueError, NotFoundError) → 400` (user-friendly)
- JSON API: `except NotFoundError → 404`, `except ValueError → 400` (RESTful)

## Кросс-модульные переэкспорты

Для совместимости с существующими импортами сервисы переэкспортируются из роутеров:
```python
# health.py
from app.services.health_service import cycle_phase as _cycle_phase
from app.services.health_service import day_of_cycle as _day_of_cycle
from app.services.health_service import get_cycle_context as _get_cycle_context
from app.services.health_service import health_summary as _health_summary

# care.py
from app.services.care_service import get_care_summary as _care_summary

# medication.py
from app.services.med_service import schedule_summary as _schedule_summary
```

## Применение к новым роутерам

При создании нового роутера (>200 строк) — сразу выносить логику в `app/services/`.
