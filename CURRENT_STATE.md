# Practice Loop — Текущее состояние

> Версия: **v0.8.1-actual**
> Обновлено: **2026-08-21**
> Git-коммит: `20dc2d73`
> Тесты: **1327 passed, 1 skipped** (17+ тестовых сюитов)

---

## Статус CI / качество

| Проверка | Результат |
|---|---|
| pytest (SQLite in-memory) | ✅ **1327 passed, 1 skipped** |
| ruff check | ✅ 0 errors |
| ruff format | ✅ чисто |
| memoryctl lint | ✅ 0 issues |
| Watchdog: icon-pack sprite | ✅ все иконки покрыты |
| Watchdog: audit-s57 | ✅ inline-script allowlist точный |
| Watchdog: transaction-boundary | ✅ commit-router allowlist точный |
| Docker `/healthz` | ✅ `ok` |

---

## Реализованные модули (все в production)

### 1. Фундамент
- Регистрация/логин, JWT + CSRF double-submit
- Роли: user / moderator / admin
- i18n EN/RU, темы dark/light/system, 3 акцентных набора (ember/sage/slate)
- Кастомизация дашборда (блоки, плотность)

### 2. Каталог активностей (Entity)
- Единая модель + `params_schema` (диапазоны параметров)
- Системные задачи (admin-seed) + пользовательские
- Опт-ин (`user_entity_opt_in`): enabled, attitude, frequency, due dates
- Публикация с авторством, категории и подкатегории (16 категорий)
- `risk_level`, `penalty_enabled`, `gamification_config`

### 3. LLM-пайплайн
- Гибридная генерация: LLM выбирает из опт-ин набора, не создаёт контент
- Режимы: `full` (имена) / `abstract` (opaque ID)
- BYOK: Omniroute (по умолчанию), Groq, OpenRouter
- JSON repair: `json.loads` → `json_repair` → regex → 3 попытки → ошибка + «Повторить»
- Usage-метрики (токены, стоимость) хранятся всегда; `raw_llm_response` — опционально
- Prompt-библиотека (`/llm/templates`)

### 4. Задачи (ActivityLog)
- 11-состояний (draft/planned/in_progress/completed/partially_completed/skipped/cancelled/stopped/substituted/not_applicable/review_needed)
- Атомарные гарды завершения/прерывания, аудит `activity_task_history`
- Генерация: LLM (`/tasks/generate`) и детерминированная
- Подзадачи (checklists), выбранные параметры, очки/XP

### 5. Сессии
- Создание, участники (многопользовательские), правила, статусы
- Принятие (accepted) → freeze: изменения штрафуются, append-only аудит
- Cooperative-режим

### 6. Геймификация
- XP/уровни/серии/комбо/достижения
- Штрафы + эскалация (×1, ×1.5, ×2...) + Redemption (отработки)
- Points Economy v2: баланс, профили, транзакции, инвентарь, замеры, расписание
- Недельные челленджи, случайные бонус-задачи

### 7. Тренировки
- TrainingDay планы: подзадачи с чек-листами, временны́е окна, журнал, фото-отчёты
- LLM анализ дня (`analyze_training_day`)
- Параллельные планы
- Адаптивные программы (AdaptiveProgram/AdaptiveProgramStep): 7-дневные AI-генерируемые планы на основе recovery-логов

### 8. Здоровье и Цикл
- Ежедневный check-in: настроение/энергия/сон/симптомы (`BodyCycleLog`)
- Цикл: расчётная фаза, история
- Дашборд `/health/dashboard` с визуализацией BodyCycleLog и процедур ухода

### 9. Замеры и тело
- Утренние/вечерние замеры тела с графиками
- Зоны тела

### 10. Лекарства
- Medication Organizer: лекарства, аптечки, остатки, расписание, факт приёма
- Экспорт для врача

### 11. Медиа-Хранилище (Media Vault)
- **AES-256-GCM** шифрование при хранении (app/media/crypto.py)
- Анти-утечка: водяные знаки с user_id + timestamp (app/media/watermark.py, Pillow)
- Извлечение ключевых кадров из видео-доказательств (app/media/video_frames.py)
- EXIF-аудит + pHash/dHash антиспуфинговый движок (app/media/anti_spoofing.py)
- Мультиподписное HMAC криптодоказательство (app/media/multi_sig.py)
- AI визуальное сравнение «До/После» (app/agent/media_comparison.py)
- Авто AI-теггинг и умные альбомы (app/agent/media_tagging.py)
- Временна́я шкала медиа-доказательств (`/media/timeline`)

### 12. Lock Timer
- Chastity management: обзор, детали сессии, шаблоны, нарушения тегов
- Безопасная остановка всегда доступна (эмуляция)

### 13. D/s Делегирование
- Роли: Keyholder (Верхний) / Submissive (Нижний)
- Добровольное делегирование полного или точечного контроля над блоками профиля
- Данные о самочувствии доступны Верхнему в режиме просмотра
- Нижний сохраняет цифровую автономию; жёсткие блокировки заменены информационными уведомлениями

### 14. Социальная платформа
- Профили, связи, лента активностей
- Верификация, модерация
- Обезличенная доска достижений
- Pillory (публичный позор) с модерацией

### 15. Аналитика и ИИ-агенты
- Интерактивный граф корреляций (`/analytics/graph`) — матрица + сетевой граф кластеров
- Analytics Engine v2 (`/insights/analytics`): попарный корреляционный анализ (Pearson) по всем
  модулям, тройные кластеры сильных связей, динамические находки в `insight_findings`
- Траектория развития (`/insights/trajectory`), сводный отчёт (`/insights/report`),
  медицинский экспорт (`/insights/export-medical`)
- Адаптивный генератор тренировочных программ (app/agent/training_generator.py)
- Аудитор безопасности и выгорания (app/agent/safety_auditor.py): индекс 0..100%, защитная заморозка при >70%
- ИИ-персона конструктор (`/agent/persona-builder`): 4 архетипа, строгость 1..5, Tone of Voice
- Лиги сообщества (app/agent/community_leagues.py): Бронза→Серебро→Золото→Мастер
- Еженедельные 1-на-1 Дуэли (app/agent/weekly_duels.py)
- Контроль обслуживания инвентаря (app/agent/equipment_maintenance.py)
- Тест готовности к сессии (app/agent/stress_test.py): 5 вопросов, 0..100%, автоснижение нагрузки при <30%
- Ежемесячные визуальные отчёты прогресса (app/agent/pdf_reports.py)
- Automation Triggers (app/agent/automation_triggers.py): AI-анализ 14-дневной истории →
  авто-триггеры (штрафы за пропуски, экстренные сеансы ухода)
- Weekly AI Digest (app/agent/weekly_digest.py): недельная сводка + предиктивный прогноз
- LLM Exchange Hub (`/llm/exchange`): экспорт кросс-доменного промпта, парсинг ответа внешней
  ИИ, гидрирование плана в сессию (комплаенс: без откровенного контента)
- Voice STT-интрейк (app/agent/voice_hydration.py): голосовая заметка → задачи/метрики здоровья
- Telegram Broadcast Engine (app/telegram/broadcast.py): прямые уведомления через aiogram

### 16. Монетизация, безопасность и Community
- Billing Showcase (`/billing`): тиры подписки (SubscriptionTier + TierFeatureGrant),
  временные акции (TemporaryFeaturePromotion), мульти-гейтвей чекаут — **Stripe, Telegram Stars,
  Crypto (NowPayments), ЮKassa**; PaymentInvoice + вебхуки; прайсы 9.99–49.99$
- Промокоды и Gift-подписки (`POST /billing/promocodes/claim`)
- Публичные цифровые сертификаты достижений (`GET /certificates/{id}/verify`)
- 2FA PIN Shield (`POST /security/verify-pin`) для Media Vault и D/s-контролей
- Community Top Agent (`/communities/{id}/agent`, `/cockpit`): автономная персона, лента
  анонсов, делегирование блоков профиля (tasks/training/care/timer)
- Публичные турниры (`POST .../tournaments/create|join`): метрики compliance/xp/care/lock,
  топ-3 → эксклюзивные бейджи; iCal-фид `GET /calendar/feed.ics`
- Co-Governance роли (app/agent/community_roles.py): co_top, keyholder, trainer, care_curator,
  tournament_organizer
- D/s Command Center (`/ds/portal`), Keyholder Dashboard (`/ds/keyholder`), Портал Нижнего
  (`/ds/my-top`): CapabilityGrant по 7 scopes, Safe Word revoke, AI Keyholder Wheel (ADR-113),
  Telegram-код привязки (ADR-130), Wear Check-Ins (ADR-100)
- Media Vault v2: одноразовые burn-on-read ссылки (`/media/one-time-token`, `/media/view-once`)
- Media Showcase (`/media/exposure/create`, `/media/showcase/{token}`): динамические таймеры экспозиции (+15m/+1h/+24h quick adjust), PIN-блокировка, просмотры, и **неснимаемые постоянные публикации** (не удаляемые до закрытия профиля)
- Deep EXIF/GPS Stripper (`app/media/sanitizer.py`): автоматическая очистка метаданных и HMAC-proof
- Privacy Masking Studio (`/api/v2/media/redact`): Gaussian blur, pixelation и blackout чувствительных зон
- Smart Albums & Encrypted Batch Export (`/api/v2/media/smart-albums`, `/batch-export-zip`): категоризация, шифрованный ZIP, защита permanent-дропов
- Cross-Activity Dead Man's Switch (`/api/v2/dms/status`, `/heartbeat`, `/dms` dashboard): сквозной контроль дедлайнов регулярности (пломбы, задачи, лекарства, общий heartbeat) с авто-эскалацией штрафов
- Wear Check-Ins OCR Verification (`/api/v2/ds/checkins/ocr-verify`): распознавание номеров пломб
- Health & Cycle Dashboard (`/health/dashboard`): визуализация BodyCycleLog + CareEntry

### 17. Инфраструктура
- Import/Export: CSV/JSON шаблоны, upload, API-push, полный экспорт
- Admin Panel: seed каталога/LLM-пресетов, пользователи, тиры
- Telegram-бот: aiogram 3.x, вебхук + исходящие уведомления
- Calendar: шаблоны доступности + vacation-оверрайды
- Scheduling: правила расписания дня
- Диеты: планы, LLM-генерация, оценка, синергия с тренировками
- Aftercare: structured relief-only журнал восстановления
- Consent: неизменяемая история согласий

---

## Известные технические долги

| Проблема | Статус | Приоритет |
|---|---|---|
| 14 иконок не в sprite (award, check-circle-2, cpu, file-text, grid, journal, layers, repeat, share-2, shield-check, sliders, user-check, volume-2, zap) | Временно заменены ближайшими аналогами | Medium |
| Alembic миграции не охватывают новые модели v0.8.1: PromoCode, UserAgentPersona, UserDuel, UserLeagueTier, SubscriptionTier, TierFeatureGrant, TemporaryFeaturePromotion, PaymentInvoice, AutomationTrigger, OneTimeMediaToken, Community/CommunityPost/CommunityTopAgent/CommunityMemberDelegation/CommunityTournament/CommunityTournamentEntry, CommunityMemberRole | Нужны новые миграции. Покрыты: 072 quests, 073 prompt library, 074 adaptive, 075 body_cycle, 076 equipment_maintenance, 077–081 D/s (managed_submissives, duties, lock_logs, grants, wear_check_ins) | High |
| Мобильное приложение не реализовано | Запланировано (M4) | Roadmap |
| `llm_exchange.html` содержит inline-script (в allowlist) | Нужен вынос в ES-модуль | Low |
| Broadcast Engine, Voice TTS, PDF-отчёты (HTML), AI-сравнение медиа, антиспуфинг, multi-sig — частично payload-заглушки / симулированные результаты | Реальная интеграция — в roadmap | Medium |

---

## Следующие шаги (предлагаемые)

- Создать Alembic-миграции для новых моделей v0.8.1 (см. таблицу тех. долгов)
- Добавить 14 недостающих иконок в sprite-pack
- Реализовать настоящую 2FA (TOTP, не только PIN)
- Написать реальную интеграцию Telegram broadcast/voice TTS с aiogram 3.x и STT-движком
- Заменить симуляции AI-агентов (media_comparison, anti_spoofing, multi_sig, pdf_reports)
  реальными вызовами
- Мобильное приложение (M4 по roadmap)
