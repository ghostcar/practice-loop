# Practice Loop — Operations Runbook

> Для VPS-деплоя, Docker Compose, PostgreSQL 15, Nginx + SSL.
> Версия: 0.9.0 / LockTimer Core C0–C8 + Universal Media.
> Последнее обновление: 2026-08-11.

## 1. Pre-deploy Checklist

- [ ] `git status` clean, reviewed commit/tag.
- [ ] `pytest tests/` — все тесты зелёные (≥507).
- [ ] `ruff check . && ruff format --check .` — чисто.
- [ ] `docker compose build` — образ собирается.
- [ ] `.env` содержит production-секреты (≥32 chars), не placeholders.
- [ ] `APP_ENV=production` в `.env`.
- [ ] `APP_PRODUCT_VARIANT=combined` (или явно tracker/timer).
- [ ] `LOCKTIMER_CORE_ENABLED=true` (для Timer-фич).
- [ ] `CHALLENGE_HMAC_KEY` задан (отдельный от JWT/ENCRYPTION) — **обязателен**: production gate завершает startup при пустом/placeholder/<32 chars.
- [ ] `UPLOAD_DIR` том примонтирован, доступен для записи.
- [ ] `TG_AUTO_ANALYSIS_TZ` задан (опционально; по умолчанию UTC — часовой пояс автоанализа тренировок).
- [ ] SSL-сертификат валиден (certbot или CF Origin Certificate).
- [ ] pg_dump сделан и проверен размер/exit code.
- [ ] `docker compose ps` — все сервисы healthy.

## 2. Deploy

```bash
cd /opt/practice-loop
git pull origin main
docker compose up -d --build
docker compose exec app alembic upgrade head
docker compose restart app
curl -sk https://localhost:8443/healthz  # или твой домен
```

## 3. Migration Runbook

1. Сделать backup: `pg_dump -U tracker -h localhost tracker > backup_$(date +%Y%m%d_%H%M).sql`
2. Проверить размер: `ls -lh backup_*.sql`
3. `docker compose exec app alembic current` — зафиксировать текущую ревизию.
4. `docker compose exec app alembic upgrade head`
5. Проверить: `docker compose exec app alembic current`
6. Smoke test: `curl /healthz`, открыть дашборд, проверить /locktimer.
7. Если миграция обнаружила неожиданные данные — остановиться, не auto-delete.

### Downgrade (только при необходимости)

```bash
docker compose exec app alembic downgrade <target_revision>
# Затем forward fix, не оставлять downgraded состояние.
```

## 4. Rollback

| Сценарий | Действие |
|----------|---------|
| App bug, schema совместима | Отключить affected flag → deploy предыдущий образ → forward fix |
| Migration failure до commit | Alembic/transaction rollback → inspect → не retry blindly |
| Migration succeeded, app fails | Flags off → prefer forward fix → downgrade only if no LockTimer rows |
| Media processor bug | Disable verification flag → keep uploads manual/review |
| Social incident | Disable public → disable adapter → disable Social → private Tracker/Timer usable |
| Неверный product variant | Вернуть прежнее значение → перезапустить → проверить данные read-only |

## 5. Backup & Restore

### Backup (cron daily)

```bash
#!/bin/bash
BACKUP_DIR=/opt/backups
RETENTION=30
DB_NAME=tracker
DB_USER=tracker
FILE="$BACKUP_DIR/tracker_$(date +%Y%m%d_%H%M).sql.gz"
pg_dump -U $DB_USER -h localhost $DB_NAME | gzip > "$FILE"
# Ротация
ls -t $BACKUP_DIR/tracker_*.sql.gz | tail -n +$((RETENTION+1)) | xargs -r rm
```

### Media backup

```bash
# Том uploads — отдельный backup (rsync или tar)
tar -czf /opt/backups/uploads_$(date +%Y%m%d).tar.gz /var/lib/docker/volumes/tracker_uploads/_data/
```

### Restore drill (quarterly)

```bash
createdb -U tracker -h localhost tracker_restore
gunzip -c backup_*.sql.gz | psql -U tracker -h localhost tracker_restore
# Проверить: таблицы, counts, snapshot hash, media manifest
# Удалить: dropdb tracker_restore
```

## 6. Health Checks

```bash
# App
curl -s http://localhost:8000/healthz          # "ok"
curl -s http://localhost:8000/api/v1/platform/capabilities | jq .

# DB
docker compose exec db pg_isready -U tracker

# Alembic
docker compose exec app alembic current

# Nginx
nginx -t
systemctl status nginx
```

## 7. Incident Playbooks

### Unauthorized access
1. Отключить media/public flags.
2. Ротировать credentials.
3. Сохранить access logs.
4. Withdraw publications.
5. Patch + regression test.

### Timer state corruption
1. Отключить state-changing Timer routes (LOCKTIMER_CORE_ENABLED=false).
2. Snapshot DB.
3. Инспектировать audit.
4. Forward reconciliation only — не редактировать audit.

### Duplicate penalties/rewards
1. Отключить consumer.
2. Идентифицировать duplicate source IDs.
3. Append compensating ledger entries.
4. Fix idempotency constraint.
5. Не удалять accounting trail.

### LLM/provider leak
1. Disable provider/cloud media.
2. Revoke key.
3. Inspect consent/audit.
4. Purge debug payload.
5. Deterministic features remain available.

### Docker cleanup
```bash
docker system prune -af --volumes  # Осторожно: удаляет все неиспользуемые тома!
docker compose down --remove-orphans
docker compose up -d --build
```

## 8. Monitoring Commands

```bash
# Логи app
docker compose logs -f --tail=100 app

# Логи nginx
tail -f /var/log/nginx/access.log /var/log/nginx/error.log

# DB connections
docker compose exec db psql -U tracker -c "SELECT count(*) FROM pg_stat_activity;"

# Disk usage
df -h / /opt/backups /var/lib/docker
du -sh /var/lib/docker/volumes/tracker_uploads/_data/

# Docker stats
docker stats --no-stream
```

## 9. Feature Flag Reference

| Флаг | Default | Назначение |
|------|---------|-----------|
| `LOCKTIMER_CORE_ENABLED` | false | Timer routes/nav/jobs (C1–C8) |
| `LOCKTIMER_VERIFICATION_ENABLED` | false | Photo verification (C6) |
| `SOCIAL_ENABLED` | false | Platform Social (S0–S8) |
| `SOCIAL_TRACKER_ADAPTER_ENABLED` | false | Social adapter for Tracker |
| `SOCIAL_TIMER_ADAPTER_ENABLED` | false | Social adapter for Timer |
| `SOCIAL_PUBLIC_ENABLED` | false | Public feed/comments |
| `LOCKTIMER_KEYHOLDER_ENABLED` | false | Keyholder features (future) |
| `LOCKTIMER_CLOUD_MEDIA_ENABLED` | false | Cloud media processing (future) |

## 10. Variant Reference

| `APP_PRODUCT_VARIANT` | Enabled | Disabled |
|-----------------------|---------|----------|
| `tracker` | Tracker routes/jobs/nav | Timer routes/jobs/nav |
| `timer` | Timer routes/jobs/nav (requires LOCKTIMER_CORE_ENABLED) | Tracker routes/jobs/nav |
| `combined` | Both domains (default) | — |

## 11. SLOs (Internal Pilot)

- API availability: 99.5%
- Safety stop: 99.99% success, p95 <1s
- Job lag: <5 минут
- No lost/duplicate state transitions
- RPO: 24h (private pilot)
- RTO: 4h (private pilot)

## 12. Memory v2 preflight (agent workflow, dev-only)

Для задач с изменением кода используется детерминированный preflight (`memoryctl`).

- **Вход через launcher**: `bin/practice-agent "<задача>"` — запускает
  `memoryctl bootstrap`, отказывается стартовать без `ready`-sentinel, затем `exec` агента.
- **Preflight**: `python -m tools.memoryctl bootstrap --task "<задача>"` → классификация,
  L0/L1-отбор, exact/lexical code search, impact frontier → `.agent-runtime/context-pack.json`
  + `session.json` (sentinel, gitignored).
- **Перед завершением**: `python -m tools.memoryctl impact` (advisory) — изменения кода вне
  impact frontier = сигнал перезапустить bootstrap.
- **Pre-commit (опционально, локально)**: `git config core.hooksPath .githooks` — блокирует
  commit кода без свежего sentinel (`memoryctl sentinel`). Docs/memory-only commit всегда проходит.
- **CI**: job `memory-lint` (informational) — `memoryctl lint` + `facts --check`.
- **Инварианты**: `docs/state/*` и `docs/adr/*` генерируются (никогда руками); секреты/uploads/
  raw LLM/эпизоды не индексируются и не коммитятся; продуктовые/safety-решения — только владелец.

