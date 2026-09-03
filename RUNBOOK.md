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

### Automated backup + restore drill (installed 2026-09-03)

Scripts: `scripts/backup_prod.sh`, `scripts/restore_drill.sh`. Cron (user `roman`):

```
0 3 * * * BACKUP_DIR=/home/roman/backups ~/tracker/scripts/backup_prod.sh >> /var/log/pl-backup.log 2>&1
0 5 * * 0 BACKUP_DIR=/home/roman/backups ~/tracker/scripts/restore_drill.sh >> /var/log/pl-restore-drill.log 2>&1
```

- Daily: `pg_dump` + uploads-volume archive, gzip-integrity + dump-header check, 14-day retention.
- Weekly (Sun 05:00): automatic restore drill into throwaway DB `tracker_restore_drill`
  (tables / users / alembic head verified, DB dropped afterwards).
- Off-site: set `OFFSITE_DIR=/mnt/backup-remote` in the cron line to rsync backups to a second
  location (NFS/CIFS/sshfs mount). Error notification: `NOTIFY_ON_ERROR` template (see script header).
- Move the backup dir to `/opt/backups` (or any mounted volume) once created; the cron
  `BACKUP_DIR` value is the single place to change.
- Verified 2026-09-03: manual run `BACKUP_OK tracker_20260903_0505 (272K)` and
  `DRILL_OK (tracker_restore_drill restored ... tables=145 users=156 alembic=093_portal_selection)`.

### Manual backup

```bash
BACKUP_DIR=/home/roman/backups scripts/backup_prod.sh
```

### Manual restore drill

```bash
BACKUP_DIR=/home/roman/backups scripts/restore_drill.sh          # newest backup
BACKUP_FILE=/home/roman/backups/tracker_YYYYMMDD_HHMM.sql.gz scripts/restore_drill.sh
KEEP_DRILL_DB=1 BACKUP_DIR=/home/roman/backups scripts/restore_drill.sh   # keep for inspection
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
- **Векторный индекс (ADR-069, shadow/assist)**: `pip install -e '.[memory]'` (только
  `qdrant-client`), затем `python -m tools.memoryctl index-code` (2167 units ≈ 4 мин, ~$0.01) и
  `python -m tools.memoryctl search-code --query "..."` (hybrid dense+lexical → RRF → exact
  confirmation). Эмбеддинги — через Omniroute: `OMNIROUTE_HOST` / `OMNIROUTE_API_KEY` в `.env`
  (модель `openrouter/openai/text-embedding-3-small`, 1536-dim; эти же параметры позже
  используются порталом). A/B: `python -m tools.memoryctl benchmark --vectors`.
- **Инварианты**: `docs/state/*` и `docs/adr/*` генерируются (никогда руками); секреты/uploads/
  raw LLM/эпизоды не индексируются и не коммитятся; продуктовые/safety-решения — только владелец.

