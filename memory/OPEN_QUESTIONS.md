# Открытые вопросы и отложенные решения

| № | Вопрос | Статус | Когда решать |
| --- | --- | --- | --- |
| 1 | Конкретные модели для seed-конфигов Groq/OpenRouter | ✅ решён (Groq: llama-3.3-70b-versatile, OpenRouter: google/gemini-2.0-flash-001) | Phase 2 |
| 2 | Стартовый набор задач 30+: пользователь расширит черновик из спеки (раздел 10.5) | открыт | до/во время Phase 2 |
| 3 | Формула XP по умолчанию и примеры кастомных формул (раздел 9.5 спеки) | открыт | Phase 4 |
| 4 | Точные тексты/формат Telegram-уведомлений и карточек задач | частично | Phase 4 |
| 5 | Механика оплаты/тарифы (`subscription_tier`) | отложено | при открытии публичного доступа |
| 6 | Рейт-лимиты и лимиты расходов | отложено | при открытии доступа другим пользователям |
| 7 | **Bif: REMEDIATION_SPEC.md ↔ ADR-029–034** | **принято владельцем (Сессия 37)** | Закрепить в AGENTS.md как «актуальная сборка v0.8-actual отличается от целевой спецификации v0.7» — перенос в Сессию 38 |
| 8 | **Audited defects (Q из AUDIT_SESSION_37)** | **открыт** | P0: Production gate секретов; P0: innerHTML-аудит + XSS-fixture (REM A14); P1: расширение LLM validator (REM 7.4); P1: `risk_level` enum (REM 5.2); P1: `store_raw_response` флаг (REM 7.5) |
| 9 | **Frontend audited defects (Q из FRONTEND_AUDIT_SESSION_38)** | **9 закрыто в S39+S40, 3 открыто** | **ЗАКРЫТО**: P0 catalog.html enum, P0 training.html RU, P1 dashboard_v2 графики (4→2+summary), P2 calendar JS i18n, P2 inventory JS i18n. **ОТКРЫТО**: P2 Inter self-hosted font, P2 mobile bottom nav (DESIGN 4.4), P2 JS-hoist в ES modules |
| 10 | **Backend audited defects (Q из AUDIT_SESSION_37 + DEFERRED_FIX_SESSION_40)** | **6 закрыто в S40, 3 открыто** | **ЗАКРЫТО** в S40: production gate секретов, store_raw_response flag, LLM validator schema, AGENTS.md bif-комментарий, XSS-fixtures, import_data localhost→app_url. **ОТКРЫТО**: P1 risk_level enum (REM §5.2), P1 generate_daily_plan subtasks gate (REM §7.1), P2 typed gamification_config DSL |
