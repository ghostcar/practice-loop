# ROADMAP_V1.md — PracticeLoop v0.9.1 → v1.1

> **Дата:** 2026-08-25  
> **Версия плана:** 1.0  
> **Владелец:** PracticeLoop  
> **Базовый коммит:** `5fcf0f18` (CI green — ruff 0, 1380 tests, memoryctl 0/0)

---

## 📐 Архитектурный контекст

```
v0.8-actual  →  1380 tests, персональный контур (tracker+timer)
v0.9.1 (OCR) →  +OCR верификация (pytesseract + vision), +прод-смок
v1.0 (Social)→  +Социальный контур (профили, фид, сообщества, лидерборд)
v1.1 (Multi) →  +Многопользовательский контур (D/s, делегирование, кейхолдер)
```

**Принцип:** каждый этап — автономный, тестируемый, деплоимый.

---

## 🔖 v0.9.1 — OCR & Verification (цель: 1–3 сессии)

### Почему 0.9.1
OCR — недостающий фундамент для всех последующих контуров:
- D/s check-in нуждается в OCR пломб
- Social verification опирается на доверенную верификацию фото
- Media vault требует извлечения метаданных из фото

### A. Foundation — окружение (1 сессия)

| # | Шаг | Файлы | Что |
|---|---|---|---|
| A.1 | **Добавить pytesseract в зависимости** | `pyproject.toml` | `pytesseract>=0.3,<0.4` |
| A.2 | **Добавить tesseract-ocr в Docker** | `Dockerfile` | `apt install tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng` |
| A.3 | **Добавить Pillow-зависимость** | `pyproject.toml` | Уже есть (pillow>=10.3) ✅ |
| A.4 | **Docker build + healthz** | — | Проверить что контейнер собирается с tesseract |

### B. OCR Engine — hardening (1 сессия)

| # | Шаг | Файлы | Что |
|---|---|---|---|
| B.1 | **Убрать SAMPLE-байты** | `app/services/ds_service.py`, `app/media/ocr_seals.py` | Передать реальные photo_bytes из формы загрузки |
| B.2 | **Загрузка фото в check-in** | `app/api/ds.py` | `UploadFile` параметр в `log_wear_checkin_endpoint` |
| B.3 | **Preprocessing пайплайн** | `app/media/ocr_seals.py` | Резкость, контраст, бинаризация перед OCR |
| B.4 | **Confidence threshold** | `app/media/ocr_seals.py` | `OCR_CONFIDENCE_THRESHOLD = 0.75` — ниже → vision-fallback |
| B.5 | **Таймаут + fallback** | `app/media/ocr_seals.py` | OCR timeout 5s → vision-эвристика |
| B.6 | **Тесты OCR** | `tests/test_ocr_seals.py` | 5+ тестов: real tesseract, regex fallback, confidence, timeout, no-tag |

### C. Verification API — production (1 сессия)

| # | Шаг | Файлы | Что |
|---|---|---|---|
| C.1 | **Страница media verify → OCR** | `app/templates/media_verify.html` | Добавить таб/режим OCR (рядом с LLM-vision) |
| C.2 | **OCR в LLM media verify** | `app/llm/pipeline/media_verify.py` | `code_match` → сначала OCR, затем vision |
| C.3 | **Verification challenge → код из OCR** | `app/api/verification.py` | Принимать фото, извлекать код через OCR, сверять с HMAC |
| C.4 | **OCR в модуле media vault** | `app/services/media.py` | Извлечение текстовых метаданных при загрузке фото |
| C.5 | **ADR-181** | `docs/adr/ADR-181.md` | Фиксация решения |
| C.6 | **Тесты verification API** | `tests/test_verification_ocr.py` | E2E: upload → OCR → challenge → verify |

### D. Финализация (1 сессия)

| # | Шаг | Что |
|---|---|---|
| D.1 | **Полный pytest** | 1380+ → зелёный |
| D.2 | **Docker build + prod deploy** | — |
| D.3 | **Prod smoke** | OCR seal check-in, media verify, challenge |
| D.4 | **Обновить PLAN.md, CHANGELOG, memory** | memoryctl facts + ADR |
| D.5 | **Git tag `v0.9.1`** | — |

### Контрольные точки v0.9.1

- [ ] pytesseract устанавливается в Docker
- [ ] OCR извлекает теги из фото (tesseract + regex)
- [ ] Confidence-порог работает (< 0.75 → fallback)
- [ ] Check-in принимает UploadFile (не SAMPLE bytes)
- [ ] Verification challenge поддерживает OCR-код
- [ ] 1400+ тестов, ruff 0, memoryctl 0/0
- [ ] Prod smoke: seal check-in с реальным фото

---

## 🚀 v1.0 — Social to Production (цель: 3–5 сессий)

### E. Enablement — разблокировка (1 сессия)

| # | Шаг | Файлы | Что |
|---|---|---|---|
| E.1 | **Включить флаги** | `app/config.py` | `social_enabled=True`, `social_tracker_adapter_enabled=True`, `community_creation_limit=3` |
| E.2 | **Sidebar: навигация** | `app/templates/base.html` | Группа «Связи» — Communities, Social Profile, Leaderboard, Pillory, Verification (уже есть при `social_operational`) |
| E.3 | **Onboarding: social module** | `app/templates/onboarding.html` | Чекбокс «Social & Communities» |
| E.4 | **Settings: social toggle** | `app/api/settings.py` | Флаг в `enabled_modules` |
| E.5 | **Consent gate** | `app/api/social/profile.py` | Проверить что `/social/profile/create` требует consent |
| E.6 | **ADR-182** | `docs/adr/ADR-182.md` | Enablement decision |

### F. Social Core — полировка (2 сессии)

| # | Шаг | Файлы | Что |
|---|---|---|---|
| F.1 | **Profile page — доработка** | `app/templates/social/profile.html` | Аватар placeholder (иконка profile), bio Markdown, privacy controls |
| F.2 | **Feed page — empty state** | `app/templates/social/feed.html` | Placeholder: «No publications yet — create your first!» |
| F.3 | **Feed page — pagination** | `app/platform/social/api/feed.py` | limit/offset, cursor-based |
| F.4 | **Relationships page** | `app/templates/social/relationships.html` | Invite list, pending/accepted, blocks, grants |
| F.5 | **Notifications bell** | `app/templates/base.html` | Иконка колокольчика + unread count |
| F.6 | **Reaction-иконки** | `design/icons/svg/` | Добавить `thumbs-up.svg`, `fire.svg`, `party.svg`, `muscle.svg` |
| F.7 | **i18n — все строки** | `app/i18n/en.py`, `app/i18n/ru.py` | Ни одной хардкод-строки в social-шаблонах |
| F.8 | **API-тесты social core** | `tests/test_social_api.py` | Profile CRUD, consent, feed, publish, comment, encourage |

### G. Communities — production (2 сессии)

| # | Шаг | Файлы | Что |
|---|---|---|---|
| G.1 | **Список сообществ** | `app/templates/community_list.html` | Публичный каталог, поиск, фильтр по типу |
| G.2 | **Карточка сообщества** | `app/templates/community_detail.html` | Участники, правила, кнопка join |
| G.3 | **Community feed** | `app/api/communities.py` | Публикации участников сообщества |
| G.4 | **Управление участниками** | `app/api/communities.py` | approve/reject/remove (владелец/модератор) |
| G.5 | **Передача владения** | `app/api/communities.py` | transfer ownership |
| G.6 | **Community Agent UI** | `app/templates/community_agent.html` | Дашборд, турниры, persona |
| G.7 | **Тесты communities** | `tests/test_communities_api.py` | CRUD, join/leave, moderation, transfer |

### H. Safety & Launch (1 сессия)

| # | Шаг | Что |
|---|---|---|
| H.1 | **Модерация — рабочий flow** | Report → assign → action (UI + E2E тест) |
| H.2 | **Pillory — прозрачность** | Публичная доска accountability |
| H.3 | **Анонимный leaderboard** | Без раскрытия email |
| H.4 | **Browser smoke** | Social profile → invite → accept → feed → publish → comment → leaderboard |
| H.5 | **ADR-183** | Social architecture decision |
| H.6 | **Git tag `v1.0.0`** | — |

### Контрольные точки v1.0

- [ ] `social_enabled=True` в .env по умолчанию
- [ ] Social навигация в sidebar
- [ ] Profile: alias + bio + discoverable
- [ ] Feed: публикации + пагинация
- [ ] Communities: список → деталь → join → participants
- [ ] Moderation: report → action
- [ ] i18n: 0 хардкод-строк
- [ ] 1450+ тестов, ruff 0, memoryctl 0/0
- [ ] Prod smoke: полный social-цикл

---

## 🌐 v1.1 — Multi-User & D/s Contour (цель: 3–5 сессий)

### I. Multiuser Foundation (1 сессия)

| # | Шаг | Что |
|---|---|---|
| I.1 | **User discovery** | Поиск по alias, invite by alias |
| I.2 | **Partner linking** | Привязка партнёра из journal к social-relationship |
| I.3 | **Shared dashboards** | Просмотр статистики партнёра (read-only, по grant) |
| I.4 | **Cross-user sessions** | Совместные сессии с участием нескольких пользователей |
| I.5 | **Notification routing** | Уведомления партнёру при действиях (in-app + Telegram) |
| I.6 | **ADR-184** | Multi-user architecture |

### J. D/s Contour — Full Controller/Submissive (2 сессии)

| # | Шаг | Что |
|---|---|---|
| J.1 | **D/s relationship model** | `ds_relationships` таблица: controller_id, sub_id, scope, status |
| J.2 | **Controller portal** | `/ds/portal` — обзор всех сабов, дашборды, управление |
| J.3 | **Granular delegation** | По модулям: tasks, training, timer, medication, inventory, care |
| J.4 | **Command execution** | Controller назначает задачи/тренировки → sub видит и выполняет |
| J.5 | **Check-in flow** | Submissive check-in с OCR верификацией пломбы → контроллер видит |
| J.6 | **Safe-word protocol** | Аварийная остановка сессии, уведомление контроллера |
| J.7 | **Punishment/Reward engine** | XP-штрафы/бонусы, escalation, redemption |
| J.8 | **Audit trail** | Все действия контроллера логируются (immutable) |
| J.9 | **ADR-185** | D/s architecture |

### K. D/s Keyholder — Timer Integration (1 сессия)

| # | Шаг | Что |
|---|---|---|
| K.1 | **Remote lock control** | Keyholder управляет locktimer-сессией саба |
| K.2 | **Timer delegation** | Submissive делегирует timer-управление keyholder'у |
| K.3 | **Emergency release** | Safe-word → немедленный safety-stop |
| K.4 | **Verification chain** | OCR seal → keyholder verify → unlock |
| K.5 | **Timer dashboard** | Keyholder видит статус таймеров всех сабов |

### L. Launch (1 сессия)

| # | Шаг | Что |
|---|---|---|
| L.1 | **Полный E2E тест** | Register → partner invite → D/s relationship → delegate → task → check-in → OCR → verify |
| L.2 | **Browser matrix** | Smoke + a11y на всех новых страницах |
| L.3 | **Documentation** | ADR, PLAN.md, FUNCTIONAL.md, RUNBOOK.md |
| L.4 | **Git tag `v1.1.0`** | — |

### Контрольные точки v1.1

- [ ] Multi-user: partner linking + discovery + shared dashboards
- [ ] D/s: controller portal + delegation + command execution
- [ ] Timer: keyholder remote control + OCR seal verification
- [ ] Audit trail: все действия логируются
- [ ] 1500+ тестов, ruff 0, memoryctl 0/0
- [ ] Prod smoke: полный D/s цикл с OCR

---

## 📊 Сводная таблица

| Этап | Тестов | Ключевые ADR | Сессии | Tag |
|---|---|---|---|---|
| v0.9.1 (OCR) | 1400+ | ADR-181 | 1–3 | `v0.9.1` |
| v1.0 (Social) | 1450+ | ADR-182, ADR-183 | 3–5 | `v1.0.0` |
| v1.1 (Multi+D/s) | 1500+ | ADR-184, ADR-185 | 3–5 | `v1.1.0` |

---

## 🟡 Сознательно за v1.1

| Пункт | Почему |
|---|---|
| TOTP/Passkeys (P5) | Отдельный security-этап |
| Media CDN (S3) | Инфраструктурный долг |
| Public comment threads | Нужна авто-модерация |
| Telegram social-команды | После стабилизации web |
| mobile PWA | Отдельный фронтенд-проект |
| billing/payments | Отдельный бизнес-этап |

---

*План зафиксирован 2026-08-25. Следующий шаг — v0.9.1, шаг A.1.*