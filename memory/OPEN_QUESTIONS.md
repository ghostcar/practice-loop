# Открытые вопросы и отложенные решения

| № | Вопрос | Статус | Когда решать |
| --- | --- | --- | --- |
| 1 | Конкретные модели для seed-конфигов Groq/OpenRouter | ✅ решён (Groq: llama-3.3-70b-versatile, OpenRouter: google/gemini-2.0-flash-001) | Phase 2 |
| 2 | Стартовый набор задач 30+ (раздел 10.5 спеки) | ✅ **закрыт (S62)**: `SEED_ENTITIES` в app/seed.py — ровно 30 задач (требование спеки), идемпотентный seed; каталог расширяется личными сущностями через /entities/my | — |
| 3 | Формула XP по умолчанию и примеры кастомных формул (раздел 9.5 спеки) | ✅ решён (S57): точная формула задокументирована в tracker-spec §9.5 — BASE_XP (25/50/15), серии +5/день, комбо +10%/потолок +50%, интенсивность +10%/уровень, пороги 0…25000, штраф 25×эскалация (потолок ×5) | Phase 4 |
| 4 | Точные тексты/формат Telegram-уведомлений и карточек задач | ✅ **закрыт (S62)**: базовый формат реализован — Markdown-уведомления всех типов (level_up/achievement/streak/threshold/penalty) через `send_telegram_notification`, inline-клавиатуры в боте; точечная кастомизация текстов — как косметика при желании | — |
| 5 | Механика оплаты/тарифы (`subscription_tier`) | ⏸ отложено | при открытии публичного доступа |
| 6 | Рейт-лимиты и лимиты расходов | ⏸ отложено | при открытии доступа другим пользователям |
| 7 | **Bif: REMEDIATION_SPEC.md ↔ ADR-029–034** | ✅ **принято владельцем (Сессия 37)**, зафиксировано в AGENTS.md §0 (S38) | — |
| 8 | **Backend audited defects (AUDIT_SESSION_37)** | ✅ **закрыт (S40+S55+S57)** — дублирует Q10: production gate, innerHTML/XSS-fixtures, LLM validator, risk_level, store_raw_response | — |
| 9 | **Frontend audited defects (FRONTEND_AUDIT_SESSION_38)** | ✅ **закрыт (S39+S40+S57)** | — |
| 10 | **Backend audited defects (Q из AUDIT_SESSION_37 + DEFERRED_FIX_SESSION_40)** | ✅ **закрыт (S40+S55+S57)** | — |
| 11 | **Новая модель хранения активностей (examples/update.md → ADR-035…042)** | ✅ **полностью закрыт (S58–S62)** | — |

## Q11 — итоговый статус (S58 → S62)

- ✅ **Phase 1 (S58)**: ActivityCategory + seed 16 категорий, эволюция Entity/ActivityLog/ActivitySession, activity_task_history, статус-машина 11, миграция 022 (PG15 ✅).
- ✅ **Phase 2 (S58)**: типизированный DSL параметров (ADR-041), title-генератор i18n (ADR-042), API переходов статусов с аудитом (ADR-040).
- ✅ **Phase 2 остаток (S62)**: LLM-адаптация planned/actual (actual_parameters в контексте и промптах, геймификация XP/Points по фактическим параметрам), scheduler интегрирован в transition API (set_next_due / set_retry_block с идемпотентностью), валидация actual_parameters против схемы.
- ✅ **update2.md (S59–S60)**: справочники BodyPart / TaskLocation / InventoryCategory + link-таблицы + DSL-селекторы + импорт/экспорт (миграция 023, PG15 ✅).
- ✅ **Phase 3 UI (S61)**: каталог с иерархическими фильтрами по категориям, динамическая форма параметров, быстрые действия по статус-машине, карточка выполнения, статистика.
- ✅ **Phase 4 (S62)**: 419/419 тестов, память обновлена, деплой подготовлен (миграция 023 + seed-кнопки + runbook).

**Итог**: 419/419 тестов ✅, ruff ✅, PG15-валидации 022/023 ✅. Осталось отложенным только то, что зависит от открытия публичного доступа: оплата/тарифы (Q5) и рейт-лимиты (Q6).

## Q12 — Deferred Timer items ✅ (Session 76)

- ✅ **Tag audit UI**: страница `/locktimer/tag-violations/{session_id}` — список violation'ов по сессии с expected/provided tag, причиной и временем. API endpoint `/api/v1/locktimer/tag-violations/{session_id}` уже существовал, добавлен HTML-вариант. +8 i18n ключей EN/RU.
- ✅ **Timer-only deploy smoke test**: `tests/test_timer_standalone.py` — 7 тестов (overview, new draft, templates, tag violations page, API endpoints, capabilities, route isolation). Проверяет что Timer работает без Tracker-зависимостей.

## Q13 — OCR/LLM верификация одноразовых кодов (отложено, Session 81)

- ⏸ **OCR/LLM-распознавание кода по фото**: verification_challenges реализованы (HMAC-SHA256, constant-time, TTL, max attempts, code never returned после создания) — это ручная верификация (пользователь вводит код с фото). OCR/LLM-распознавание кода по загруженной фотографии **отложено** (три места: `app/models/media.py`, `app/services/media.py`, `app/api/verification.py` — «OCR support deferred»).
- **Когда**: при предметной обвязке Chastity Timer (Этап 3) или по отдельному решению владельца.
- **Замечание**: LLM не должен быть источником истины для кода (PD-014) — OCR/LLM допустим только как подсказка/ускорение ввода, финальная верификация остаётся constant-time HMAC.

