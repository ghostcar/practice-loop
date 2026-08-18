# K-S8 — Personal release gate

Актуально на 18 августа 2026 года. Social в этой серии не изменялся.

## Что считается закрытым

- ActivitySession: явное одноразовое принятие, append-only история, задачи с attach/detach,
  штрафуемые изменения после принятия и freeze после завершения.
- Today: локальные границы суток и отдельная очередь overdue/review.
- Privacy export: schema v2, owner-scoped, без лимита записей; корни и дочерние Personal/Timer
  агрегаты включены, секреты и внутренние file paths исключены.
- JSON actions: ActivitySession lifecycle, update Medication, done/skip Care course session.
- Admin writes явно flush-ятся до успешного ответа.

## Evidence

- Ruff check и format-check: зелёные; Alembic: одна head `c1d2e3f4a5b6` (060).
- Полный Python 3.11 regression: `1154 passed, 1 skipped, 3 warnings`.
- Production dump `/tmp/practice_loop_personal_20260818.dump` восстановлен в отдельную временную
  PostgreSQL 15 БД; совпали 101 public table, 13 users и 0 activity logs; head 060. Временная БД
  после проверки удалена.
- `tracker_uploads` архивирован отдельно в `/tmp/practice_loop_uploads_20260818.tar.gz`; volume на
  момент проверки не содержал пользовательских файлов.
- Production-like compose пересобран, `/healthz` — 200, `scripts/prod_smoke.sh` — `SMOKE_OK`.
- Chromium portal E2E: 7/7 (navigation, accepted-session audit, dark/light axe, keyboard,
  overflow, reduced motion, timer action).
- Девять созданных smoke/browser пользователей удалены каскадно.

## Операционное правило

Бэкап БД без uploads не является полным operational backup. Перед рискованным deploy нужны оба
артефакта; restore drill выполняется в отдельной БД и никогда не поверх production.
