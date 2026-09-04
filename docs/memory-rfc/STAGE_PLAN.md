# Practice Loop — план на 5 шагов вперёд

> Статус: рабочий roadmap. Memory v2 (Этапы 1–3 ниже) — ✅ завершены (Сессии 114–118).
> **Принцип владельца (Сессия 119):** проект на данном этапе — **личный контур** (первая
> очередь разработки). Все социальные и общедоступные функции — **вторая очередь**.
> LLM подключается в личном контуре полностью: Omniroute (первым источником), подбор моделей,
> harness, инструменты, приватная база знаний для промптов, библиотека типовых промптов,
> переутверждение границ работы LLM (владелец: текущие ограничения консервативны для
> личного контура, готов расширить).
> Дисциплина: шаги выполняются последовательно; память и аудит/разработка не смешиваются
> внутри одного шага.

---

## План на 5 шагов (принят владельцем, Сессия 119)

| # | Шаг | Состав | Gate |
|---|---|---|---|
| 1 | **Gate A остаток — безопасность (малые)** | P1-1 innerHTML→textContent + XSS-regression тест; P2-3 readiness без текста исключения; P1-6 базовые security headers (HSTS/nosniff/Referrer/X-Frame-Options) + CSP report-only | `pytest tests/` зелёный; XSS-тест с HTML payload; headers в ответах |
| 2 | **LLM/media границы (средние)** | P1-2 weekly planner: exact dates + uniqueness + completeness + атомарный save; P1-3 media finalize: owner-target check через registry; P1-7 version из одного источника | даты из target_dates, атомарность, cross-user bind отклонён |
| 3 | **Память — завершение Этапа 3** | M5 freeze legacy `memory/*` (период наблюдения 118 сессий пройден); required CI `memory-lint`; impact-recall метрика в benchmark (задел под graph-пилот) | `memoryctl lint` 0/0 в CI required; freeze-политика задокументирована |
| 4 | **Полировка личного контура таймера** ✅ | Q14 закрыт по ADR-072: penalty в HTTP (skip/late-close через `rule.penalty_policy`/`late_close_policy`); внедрение OMNIROUTE_HOST/KEY в портал (Settings + LLM-конфиги) | skip/late-close применяют явную политику и возвращают фактический penalty; Omniroute-пресет активен |
| 5 | **Gate B остаток — стабилизация поведения** | P1-5 transaction ownership (единый owner — сервис коммитит); P2-2 async media (streaming/thread-pool, decompression bomb guard); P1-4 browser smoke (Playwright RU/EN × light/dark × 360/768/1280: login/dashboard/task/timer) | P1-5+P2-2+P1-4 покрыты тестами; browser matrix зелёный |

| 6 | **LLM harness личного контура (ADR-070)** | Omniroute — первый источник моделей: пресет в LLM-конфигах активен, подбор бесплатных/дешёвых моделей; **библиотека типовых промптов** по функциональным блокам; **промпт-шаблоны** (параметрическая генерация: пользователь создаёт шаблон с параметрами → LLM генерирует по нему); **приватная база знаний** для промптов (векторный индекс + Omniroute-эмбеддинги, выбранные заметки в контекст) | шаблоны CRUD + validate, KB в промпте, Omniroute-пресет активен; тесты |
| 7 | **LLM/OCR-верификация медиа (истина в последней инстанции)** | Соло-игры: OCR-first подтверждение кодов и LLM-vision для fallback/оценки закрытия пояса; media → verification → OCR/LLM-оценка → статус; UI результата | match/mismatch по фото, код не хранится plaintext, HMAC остаётся источником истины; ADR-181 и тесты |

**После шага 7** (вторая очередь, по отдельному решению): Social/public, Gate C (frontend
унификация + enforcing CSP), Gate D (публичная эксплуатация), M6 (MCP), Q5/Q6 (оплата/лимиты),
а также medication-specific OCR.

---

## Решение владельца по границам LLM — ADR-070 (Сессия 119)

Зафиксировано в `memory/DECISIONS.md` (ADR-070). Ключевое:
- **Гибрид сохраняется** (каталог + opt-in), режим названий per-provider через `llm_mode` (full/abstract).
- **Параметрическая генерация через промпт-шаблоны** — осознанно создано пользователем, сохранено как шаблон.
- **LLM-верификация медиа** — истина в последней инстанции для соло-игр (подтверждение кодов, закрытие пояса верности).
- **Приватная база знаний** для промптов + **библиотека типовых промптов** по функциональным блокам.
- Omniroute — первый источник моделей (подбор бесплатных/дешёвых); параметры OMNIROUTE_HOST/KEY уже в `.env`.
- Комплаенс-красная линия не снимается: никакого обхода safety-фильтров провайдеров и маскирования контента (ToS + блокировка ключа).

Реализация — шаги 6–7 плана выше (после Gate B стабилизации, шаги 1–5).

---

## Исторический план Memory v2 (Этапы 1–3, завершён)

> Статус: ✅ пройден (Сессии 114–118). Сохранён как историческая справка.

## Этап 1 — M3 base: `memoryctl bootstrap` (детерминированный, stdlib-only)

Результат: воспроизводимый context pack + sentinel из текущего HEAD, без внешних зависимостей.

- классификация задачи (product/fact/code/ui/data/security/deploy + scope);
- выбор L0 (AGENTS.md + root/domain knowledge.md) и релевантных L1 (ADR/wiki/questions по scope/keyword);
- exact/lexical поиск кода (pure-Python, fallback без `rg`);
- impact frontier (тесты, миграции, call sites);
- context pack + sentinel (`.agent-runtime/`, gitignored);
- risks + required_checks из классификации.

Gate: unit-тесты на классификацию, выбор docs, поиск, детерминизм, denylist/HEAD staleness.

## Этап 2 — M3 benchmark + пилоты (только с доказанным приростом)

- [x] harness по `BENCHMARK_TASKS.md` (12 задач): recall@5, MRR, размер pack, лишние чтения
      (`tools/memoryctl/benchmark.py` → `docs/state/BENCHMARK.json`, Сессия 115);
- [x] baseline M3-base измерен: recall@5 0.26, MRR 0.356, pack ≤9 KiB, 0 forbidden;
- [x] решение владельца по пилотам (Сессия 116, **ADR-069**):
      - **embedding**: BGE-M3 (multilingual, fastembed/ONNX, local-only);
      - **пилот**: только Qdrant local vectors (shadow);
      - QMD (docs) и codebase-memory-mcp (graph) — отложены;
      - code-specific второй named-вектор — только если BGE-M3 слаб на коде;
      - зависимости — только в optional dev-group, рантайм продукта не трогается.
- [x] реализация пилота (Сессия 118): `memoryctl index-code` (структурные code units,
      stdlib `ast`/regex parser) + `memoryctl search-code` (hybrid dense+lexical, клиентский RRF
      fusion, exact confirmation) + A/B флаг `benchmark --vectors`; graceful degradation без
      optional `memory` dev-group; ~25 новых тестов.
- [x] **реальный A/B** (Сессия 118, Omniroute): embedding через локальный LLM-прокси
      Omniroute (`openrouter/openai/text-embedding-3-small`, 1536-dim; ADR-069 amended —
      BGE-M3 невозможна на VPS: fastembed не поддерживает + OOM локальной fp32-модели).
      Индекс 2167 units ≈ 4 мин, ~$0.01. **Результат: recall@5 0.24 → 0.37 (+0.13),
      MRR 0.356 → 0.496 (+0.14), pack ≤12 KiB, 0 forbidden; прирост на RU→EN задачах
      (T3/T4/T5/T8). Gate пройден → пилот admit (shadow/assist-режим).**

Gate: прирост recall@5/MRR против baseline 0.26/0.356 с pack ≤12 KiB; иначе пилот остаётся off/optional.

## Этап 3 — M4 preflight (обязательный)

- [x] `memoryctl sentinel` — проверка свежего preflight (status/head-ancestor/pack hash/TTL);
- [x] `memoryctl impact` — advisory: изменения кода vs impact frontier последнего pack;
- [x] `bin/practice-agent` launcher (bootstrap → sentinel-check → exec агента);
- [x] `.agents/skills/project-memory/SKILL.md` — единый workflow;
- [x] `.githooks/pre-commit` (opt-in: `git config core.hooksPath .githooks`) — блокирует code-commit без sentinel;
- [x] RUNBOOK.md §12 — как пользоваться;
- [ ] `.agents/practice-loop.ts` (Freebuff custom agent) — отложено: требует pinned Freebuff SDK, формат не верифицирован;
- [ ] `.agents/mcp.json` (per-agent MCP profiles) — отложено: MCP-серверы не подключены (M6);
- [ ] required CI `memory-lint` после периода наблюдения (сейчас informational);
- [ ] M5 (freeze legacy `memory/*` сессионных логов) — отдельным шагом после 10 сессий.

Gate: `memoryctl sentinel` блокирует code-commit без preflight; launcher отказывается стартовать без `ready`-sentinel.

## Вне этого плана (не смешивать)

- Social/public (вторая очередь — после личного контура), Q5/Q6 (оплата/лимиты),
  medication-specific OCR, Gate C/D, M6 (MCP), `.agents/practice-loop.ts` (Freebuff SDK не верифицирован).
