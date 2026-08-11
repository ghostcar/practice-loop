# Открытые вопросы и отложенные решения

| № | Вопрос | Статус | Когда решать |
| --- | --- | --- | --- |
| 1 | Конкретные модели для seed-конфигов Groq/OpenRouter | ✅ решён (Groq: llama-3.3-70b-versatile, OpenRouter: google/gemini-2.0-flash-001) | Phase 2 |
| 2 | Стартовый набор задач 30+: пользователь расширит черновик из спеки (раздел 10.5) | открыт | до/во время Phase 2 |
| 3 | Формула XP по умолчанию и примеры кастомных формул (раздел 9.5 спеки) | ✅ решён (S57): точная формула задокументирована в tracker-spec §9.5 — BASE_XP (25/50/15), серии +5/день, комбо +10%/потолок +50%, интенсивность +10%/уровень, пороги 0…25000, штраф 25×эскалация (потолок ×5) | Phase 4 |
| 4 | Точные тексты/формат Telegram-уведомлений и карточек задач | частично | Phase 4 |
| 5 | Механика оплаты/тарифы (`subscription_tier`) | отложено | при открытии публичного доступа |
| 6 | Рейт-лимиты и лимиты расходов | отложено | при открытии доступа другим пользователям |
| 7 | **Bif: REMEDIATION_SPEC.md ↔ ADR-029–034** | **принято владельцем (Сессия 37)** | Закрепить в AGENTS.md как «актуальная сборка v0.8-actual отличается от целевой спецификации v0.7» — перенос в Сессию 38 |
| 8 | **Audited defects (Q из AUDIT_SESSION_37)** | **открыт** | P0: Production gate секретов; P0: innerHTML-аудит + XSS-fixture (REM A14); P1: расширение LLM validator (REM 7.4); P1: `risk_level` enum (REM 5.2); P1: `store_raw_response` флаг (REM 7.5) |
| 9 | **Frontend audited defects (Q из FRONTEND_AUDIT_SESSION_38)** | **всё закрыто (S39+S40+S57)** | **ЗАКРЫТО**: P0 catalog.html enum, P0 training.html RU, P1 dashboard_v2 графики, P2 calendar/inventory JS i18n, P2 Inter self-hosted font, P2 mobile bottom nav (DESIGN 4.4), P2 JS-hoist в ES modules — **все в S57** |
| 10 | **Backend audited defects (Q из AUDIT_SESSION_37 + DEFERRED_FIX_SESSION_40)** | **всё закрыто (S40+S55+S57)** | **ЗАКРЫТО** в S40: production gate, store_raw_response, LLM validator, bif-комментарий, XSS-fixtures, import_data URL. **В S55**: deps/CSRF/safety gate. **В S57**: P1 risk_level enum (REM §5.2) + gate, P1 generate_daily_plan subtasks gate (REM §7.1), P2 typed gamification_config DSL |
