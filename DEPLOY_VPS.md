# Practice Loop — VPS Deployment Runbook

> **Версия:** 0.8.0 (commit `576c432`, session 40)
> **Цель:** голый VPS → рабочий `https://your-domain.com` с PostgreSQL, app, Telegram-ботом.
> **Стиль:** только блоки кода — копируй и выполняй по порядку.

---

## 0. Предусловия

```bash
# Ubuntu 22.04/24.04, замени YYY.YYY.YYY.YYY на IP, your-domain.com — на домен
sudo apt update && sudo apt -y upgrade
sudo apt install -y docker.io docker-compose-v2 postgresql-client nginx git ufw
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker          # или перелогинься
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

Опционально (ставь **только ту версию, что подходит под §8**):

```bash
# Если домен напрямую на VPS без Cloudflare (grey cloud / DNS-only):
sudo apt install -y certbot python3-certbot-dns-cloudflare

# Если через Cloudflare (orange cloud) — НЕ СТАВЬ certbot.
# Сертификат возьмёшь в Cloudflare Dashboard → SSL/TLS → Origin Server.
```

Проверь:
```bash
docker --version          # Docker version 24+
docker compose version    # Docker Compose version v2.20+
```

---

## 1. DNS

В панели регистратора создай `A`-запись:
```
your-domain.com   →   YYY.YYY.YYY.YYY
```

Подожди 2–5 минут, проверь:
```bash
dig +short your-domain.com
```

---

## 2. Каталог проекта

```bash
sudo mkdir -p /opt/tracker && sudo chown $USER:$USER /opt/tracker
cd /opt/tracker
git clone https://github.com/ghostcar/practice-loop.git .
git log --oneline -1      # 576c432 feat(s40): deferred fixes — production gate, bif, JS i18n, XSS fixtures
```

---

## 3. Генерация секретов

```bash
cd /opt/tracker
openssl rand -base64 48 | tr -d '/+=' | cut -c1-48 > /tmp/.jwt.tmp
openssl rand -base64 48 | tr -d '/+=' | cut -c1-48 > /tmp/.enc.tmp
openssl rand -hex 24                 > /tmp/.tg.tmp
openssl rand -base64 24 | tr -d '/+=' | cut -c1-24 > /tmp/.pg.tmp.SECRETS
# пароль для PostgreSQL (16+ chars)
echo -n "tracker_$(openssl rand -hex 12)" > /tmp/.pg.tmp.DB
JWT=$(cat /tmp/.jwt.tmp); ENC=$(cat /tmp/.enc.tmp); TG=$(cat /tmp/.tg.tmp); PG=$(cat /tmp/.pg.tmp.DB)
echo "JWT:        $JWT  (len=${#JWT})"
echo "ENC:        $ENC  (len=${#ENC})"
echo "TG secret:  $TG   (len=${#TG})"
echo "PG password $PG   (len=${#PG})"
```

Все длины должны быть **≥32** для JWT/ENC, **≥16** для PG. Если меньше — повтори генерацию.

---

## 4. Файл `.env`

```bash
cd /opt/tracker
JWT=$(cat /tmp/.jwt.tmp); ENC=$(cat /tmp/.enc.tmp); TG=$(cat /tmp/.tg.tmp); PG=$(cat /tmp/.pg.tmp.DB)
cat > .env <<EOF
# === App mode ===
APP_ENV=production

# === PostgreSQL (используется внутри compose) ===
POSTGRES_DB=tracker
POSTGRES_USER=tracker
POSTGRES_PASSWORD=${PG}
POSTGRES_PORT=5432

# === Secrets (production gate требует >=32 chars, отлично от change-me-*) ===
JWT_SECRET_KEY=${JWT}
CREDENTIALS_ENCRYPTION_KEY=${ENC}
TG_WEBHOOK_SECRET=${TG}

# === LLM (BYOK пользователя — пусто, добавляется через /llm-configs) ===
# Omniroute уже доступен на хосте: http://host.docker.internal:20128/v1

# === Telegram (опционально, можно пустым) ===
TG_BOT_TOKEN=
TG_POLLING=true
TG_BOT_USERNAME=practice_loop_bot
EOF
chmod 600 .env
rm -f /tmp/.jwt.tmp /tmp/.enc.tmp /tmp/.tg.tmp /tmp/.pg.tmp.DB
echo "=== sanity: APP_ENV=production считает .env, gate сработает если забыл сменить ==="
APP_ENV=test python3 -c "from app.config import settings; print('ok: jwt',len(settings.jwt_secret_key),'enc',len(settings.credentials_encryption_key))"
```

> ⚠️ Если `JWT_SECRET_KEY` или `CREDENTIALS_ENCRYPTION_KEY` окажутся короче 32 — контейнер **упадёт при старте**. Это by design (production gate).

---

## 5. Сборка и подъём

```bash
cd /opt/tracker
docker compose --profile prod up -d --build
```

Проверь:
```bash
docker compose ps          # db + app должны быть 'Up'
docker compose logs --tail=30 db   | tail -20
docker compose logs --tail=30 app  | tail -20
curl -sS http://127.0.0.1:8000/healthz   # {"status":"ok"}
```

Если приложение стартует, но `/healthz` пустой — посмотри логи:
```bash
docker compose logs --tail=80 app | grep -iE 'error|trace|fail|gate'
```

---

## 6. Миграции (выполняются при первом старте контейнера автоматически)

```bash
docker compose exec app alembic upgrade head
docker compose exec app alembic current        # 016_add_store_raw_response (head)
```

---

## 7. Регистрация первого пользователя

Открой в браузере (после шага 8, чтобы был доступ через домен):
```
https://your-domain.com/register
```

Создай аккаунт. Запомни email — он нужен для seed.

Подними его до **admin** через БД:
```bash
cd /opt/tracker
docker compose exec db psql -U tracker -d tracker -c \
  "UPDATE users SET role='admin' WHERE email='your@email.com';"
```

---

## 8. SSL — выбери свою ветку

Есть **три варианта**. Выбор зависит от того, как настроен домен в Cloudflare:

| Режим в CF | Где видно | Сертификат | Авто-продление |
|---|---|---|---|
| 🅰️ **🟠 Proxied** (рекомендую) | DNS → запись с оранжевым облачком | **CF Origin Certificate** (15 лет) | Нет срока — никогда |
| 🅱️ **⚪ DNS-only** | DNS → запись с серым облачком, без CF proxy | **Let's Encrypt** через DNS-01 | Да, certbot cron |
| 🅲️ **Без CF вообще** | NS-серверы НЕ на CF | **Let's Encrypt** через standalone | Да, certbot cron |

Определись:

```bash
# Проверь CF-проксирование (если NS на CF)
dig +short your-domain.com
# Если в ответе IP — это адрес CF (orange cloud, Proxied), значит ветка 🅰️
# Если IP совпадает с твоим VPS-IP напрямую — ветка 🅱️ или 🅲️

# Альтернативно — зайди в Cloudflare Dashboard → DNS → записи:
# 🟠 оранжевое облачко → ветка 🅰️
# ⚪ серое облачко   → ветка 🅱️
```

> **По умолчанию рекомендую ветку 🅰️ (CF Origin Certificate).** Сертификат живёт 15 лет, certbot не нужен, никаких DNS-01 токенов. Переходи на 🅱️ только если сознательно хочешь grey-cloud (CF не проксирует трафик).

---

### 8.🅰️ Cloudflare Proxied → CF Origin Certificate (рекомендую)

**Навигация по CF Dashboard** (клик за кликом):

1. Открой `https://dash.cloudflare.com/` → кликни **на свой домен** в списке.
2. **Левая панель → SSL/TLS** → кликни. Откроется Overview.
3. В **подменю SSL/TLS** (внизу панели) кликни **`Origin Server`** (не `Edge Certificates`).
4. В правом верхнем углу секции "Origin Certificates" — большая синяя кнопка **`Create Certificate`**. Нажми.
5. В форме:
   - **Private key type**: `RSA` (по умолчанию) или `ECDSA`.
   - **Hostnames**: впиши два имени — `tracker.your-domain.com` и `*.tracker.your-domain.com`.
   - **Certificate Validity**: `15 years` (по умолчанию).
   - Кликни **`Next`**.
6. CF покажет **два блока**:
   - **Certificate** (начинается с `-----BEGIN CERTIFICATE-----`)
   - **Private Key** (начинается с `-----BEGIN PRIVATE KEY-----`).
   - Скопируй оба блока. **Private Key показывается ОДИН РАЗ.**

**Перед созданием сертификата** — в `SSL/TLS → Overview` поставь **Encryption mode = Full** (НЕ Strict — Origin Cert не trusted публичными CA).

**DNS-проверка перед стартом** (что домен реально proxied через CF):

```bash
dig +short tracker.your-domain.com
# Если ответ — IP-адрес CF (104.16.x.x, 172.64.x.x) → Proxied ✅
# Если ответ — IP твоего VPS → DNS-only, нужна ветка 🅱️
```

**Сохранение сертификата на VPS:**

```bash
sudo mkdir -p /etc/ssl/cloudflare
sudo tee /etc/ssl/cloudflare/tracker.your-domain.com.pem > /dev/null <<'EOF'
# (вставь Certificate из CF — текст целиком, включая BEGIN/END)
EOF

sudo tee /etc/ssl/cloudflare/tracker.your-domain.com.key > /dev/null <<'EOF'
# (вставь Private Key из CF — целиком, включая BEGIN/END)
EOF

sudo chmod 600 /etc/ssl/cloudflare/tracker.your-domain.com.key
sudo chmod 644 /etc/ssl/cloudflare/tracker.your-domain.com.pem
```

**Sanity-check пары:**

```bash
sudo openssl x509 -in /etc/ssl/cloudflare/tracker.your-domain.com.pem -noout -subject -dates
# Должно показать Subject: CN = tracker.your-domain.com и notAfter ~+15 лет

sudo openssl x509 -in /etc/ssl/cloudflare/tracker.your-domain.com.pem -noout -modulus | openssl md5
sudo openssl rsa -in /etc/ssl/cloudflare/tracker.your-domain.com.key -noout -modulus 2>/dev/null | openssl md5
# Два MD5 должны СОВПАДСТИ → пара валидна (nginx сможет стартануть)
```

**Конфиг хоста-nginx:**

```bash
sudo tee /etc/nginx/sites-available/tracker.your-domain.com.conf > /dev/null <<'NGINX'
upstream tracker_app {
    server 127.0.0.1:8000;
    keepalive 32;
}

# HTTP → HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name tracker.your-domain.com;

    location /.well-known/acme-challenge/ {
        root /var/www/html;     # на случай смены схемы в будущем — безвредно
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS — CF Origin Certificate
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name tracker.your-domain.com;

    # === Cloudflare Origin Certificate ===
    ssl_certificate     /etc/ssl/cloudflare/tracker.your-domain.com.pem;
    ssl_certificate_key /etc/ssl/cloudflare/tracker.your-domain.com.key;

    # === SSL hardening (Mozilla Intermediate) ===
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    client_max_body_size 50m;

    location / {
        proxy_pass http://tracker_app;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $http_cf_connecting_ip;  # CF подставляет реальный IP клиента
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_read_timeout 90s;
    }

    location /static/ {
        proxy_pass http://tracker_app;
        proxy_set_header Host $host;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/tracker.your-domain.com.conf /etc/nginx/sites-enabled/
sudo grep -q 'limit_req_zone.*zone=auth' /etc/nginx/nginx.conf || \
sudo sed -i '/^http {/a\    limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;' /etc/nginx/nginx.conf
# (опционально: rate-limit на /auth/)
sudo nginx -t && sudo systemctl reload nginx
```

**В CF Dashboard:**
- DNS → A-запись `tracker` → переключи на 🟠 **Proxied** (если был ⚪).

**Проверка:**

```bash
curl -sI https://tracker.your-domain.com/ | head -10
# Ожидаешь: HTTP/2 200, server: cloudflare, cf-ray: <hash>

curl -sS https://tracker.your-domain.com/healthz   # {"status":"ok"}

echo | openssl s_client -servername tracker.your-domain.com -connect tracker.your-domain.com:443 2>/dev/null | \
    openssl x509 -noout -issuer
# Issuer: O = "Cloudflare, Inc."   ← значит ветка 🅰️ активна
```

---

### 8.🅱️ Cloudflare DNS-only (⚪ серое облачко) — Let's Encrypt через DNS-01

**Понадобится:** CF API Token с правом `Zone / DNS / Edit` для твоего домена.

Создай токен: **CF Dashboard → My Profile → API Tokens → Create Token → Edit zone DNS**.

```bash
# Установка certbot + плагин DNS-01 (НЕ нужен открытый порт 80)
sudo apt install -y certbot python3-certbot-dns-cloudflare

# Креды для certbot
sudo mkdir -p /etc/letsencrypt
sudo tee /etc/letsencrypt/cloudflare.ini > /dev/null <<'EOF'
dns_cloudflare_api_token = ВСТАВЬ_СЮДА_CF_API_TOKEN
EOF
sudo chmod 600 /etc/letsencrypt/cloudflare.ini

# Получи сертификат (DNS-01 — без HTTP challenge)
sudo certbot certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
    --dns-cloudflare-propagation-seconds 30 \
    --agree-tos -m your-email@example.com \
    -d tracker.your-domain.com \
    -d "*.tracker.your-domain.com"
# Будет ждать ~30 сек пока CF опубликует TXT-record
# Сертификаты: /etc/letsencrypt/live/tracker.your-domain.com/{fullchain.pem,privkey.pem}

# certbot автоматически поставит cron на обновление (через DNS-01, без порта 80)
```

**Конфиг хоста-nginx (тот же что и для ветки 🅰️, но пути к сертификатам от Let's Encrypt):**

```bash
sudo tee /etc/nginx/sites-available/tracker.your-domain.com.conf > /dev/null <<'NGINX'
upstream tracker_app {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    listen [::]:80;
    server_name tracker.your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name tracker.your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/tracker.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tracker.your-domain.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;

    client_max_body_size 50m;

    location / {
        proxy_pass http://tracker_app;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_read_timeout 90s;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/tracker.your-domain.com.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

**Проверка:**

```bash
curl -sI https://tracker.your-domain.com/ | head -10
echo | openssl s_client -servername tracker.your-domain.com -connect tracker.your-domain.com:443 2>/dev/null | \
    openssl x509 -noout -issuer
# Issuer: O = Let's Encrypt   ← значит ветка 🅱️ активна
```

---

### 8.🅲️ Без Cloudflare — standalone certbot (порт 80 должен быть свободен)

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d your-domain.com --agree-tos -m your-email@example.com
# Сертификаты: /etc/letsencrypt/live/your-domain.com/{fullchain.pem,privkey.pem}
```

Потом — конфиг nginx из ветки 🅱️ (но с портами 80/443 напрямую открытыми через `sudo ufw allow 80/tcp`, который у тебя уже включён в §0).

---

### 8.4. Типичные ошибки SSL

| Симптом | Причина | Фикс |
|---|---|---|
| `Error 526: Invalid SSL certificate` в CF | Full Strict, а на origin standalone cert | Понизь до **Full** или используй CF Origin Cert |
| `Error 521: Web server is down` | Origin не слушает 443 или app упал | `docker compose logs app \| tail -30` |
| `Error 522: Connection timed out` | ufw блокирует, или IP в CF DNS неверный | `sudo ufw status` — должны быть 80, 443 |
| `Error 520` | App вернул мусор (часто — заголовок Host неверный) | В nginx → `proxy_set_header Host $host;` (уже есть) |
| `curl: (60) SSL certificate problem` | Стучишься на IP, минуя CF | Используй **доменное имя** |

---

## 9. Seed (опционально)

Админ-аккаунт уже создан на шаге 7. Если нужен каталог из 30+ системных практик:
```bash
cd /opt/tracker
docker compose exec app python seed_prod.py --email your@email.com
```

---

## 10. Telegram (опционально)

### 10.1. Создание бота

1. Открой `@BotFather` в Telegram → `/newbot` → имя → username (например `practice_loop_bot`).
2. Скопируй токен в формате `123456789:AAF…`.

### 10.2. Подключение

```bash
cd /opt/tracker
sed -i 's|^TG_BOT_TOKEN=.*|TG_BOT_TOKEN=<вставить токен>|' .env
sed -i 's|^TG_BOT_USERNAME=.*|TG_BOT_USERNAME=practice_loop_bot|' .env
sed -i 's|^TG_POLLING=.*|TG_POLLING=false|' .env          # для HTTPS — webhook
docker compose restart app
```

### 10.3. Регистрация webhook

После того как nginx + SSL работают (любая ветка §8), webhook настраивается автоматически при старте. Проверь:
```bash
docker compose logs app | grep -iE 'webhook|telegram'
curl -sS "https://api.telegram.org/bot<TOKEN>/getWebhookInfo" | python3 -m json.tool
```

### 10.4. Привязка пользователя

В приложении: `/dashboard` → карточка «Link Telegram» → «Generate code» → скопируй 6-значный код → в боте отправь `/link CODE`.

---

## 11. Бэкапы PostgreSQL (cron)

```bash
sudo mkdir -p /backups && sudo chown $USER:$USER /backups
(crontab -l 2>/dev/null; echo \
"# PracticeLoop: daily pg_dump at 03:00 UTC, keep last 7 days") | crontab -
(crontab -l 2>/dev/null; echo \
"0 3 * * * docker compose -f /opt/tracker/docker-compose.yml exec -T db pg_dump -U tracker -d tracker | gzip > /backups/tracker_\$(date +\\%Y\\%m\\%d).sql.gz && find /backups -name 'tracker_*.sql.gz' -mtime +7 -delete") | crontab -
crontab -l | tail -5
```

Проверить вручную:
```bash
docker compose exec -T db pg_dump -U tracker -d tracker | gzip > /tmp/test_backup.sql.gz
gunzip -c /tmp/test_backup.sql.gz | head -20
rm -f /tmp/test_backup.sql.gz
```

Восстановление (если что-то пошло не так):
```bash
# 1) остановить app
docker compose stop app
# 2) залить дамп
gunzip -c /backups/tracker_YYYYMMDD.sql.gz | docker compose exec -T db psql -U tracker -d tracker
# 3) поднять app
docker compose start app
```

---

## 12. Обновление версии (deploy update)

```bash
cd /opt/tracker
git pull                                      # новые коммиты
docker compose --profile prod up -d --build   # пересборка + перезапуск
docker compose logs --tail=20 app | tail -20   # смотрим что стартанул
curl -sS https://your-domain.com/healthz       # {"status":"ok"}
```

Если что-то сломалось с миграцией — откат:
```bash
docker compose exec app alembic downgrade -1   # на одну миграцию назад
# или до конкретной:
docker compose exec app alembic downgrade 015  # до ревизии 015
```

---

## 13. Полезные аварийные команды

```bash
cd /opt/tracker

# Логи в реальном времени
docker compose logs -f app

# Зайти внутрь контейнера
docker compose exec app bash

# Перезапуск только app (накат миграций при старте)
docker compose restart app

# Полностью пересобрать без кэша
docker compose build --no-cache app

# Полный дамп и подъём с нуля (ОСТОРОЖНО, удаляет данные)
docker compose down -v
docker compose --profile prod up -d --build

# Сколько занято места
docker system df
docker compose exec db psql -U tracker -d tracker -c "\dt+"
```

---

## 13.1. Troubleshooting: «address already in use: 127.0.0.1:8000»

**Симптом:**
```
Error response from daemon: failed to set up container networking:
failed to bind host port 127.0.0.1:8000/tcp: address already in use
```

**Причина:** bind `127.0.0.1:8000` — эксклюзивный, на хосте может быть только один владелец.

**Диагностика (выполняй по порядку):**

```bash
# 1. Что есть из compose (включая остановленные)
docker compose ps -a

# 2. Кто слушает порт 8000
sudo ss -ltnp | grep ':8000'

# 3. Все контейнеры проекта (включая orphan)
docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -i tracker
```

**Решение:**

```bash
# A. Остановить ВСЕ возможные compose-профили этого проекта
docker compose down --remove-orphans
docker compose --profile full down --remove-orphans 2>/dev/null || true
docker compose --profile prod down --remove-orphans 2>/dev/null || true

# B. Проверить порт
sudo ss -ltnp | grep ':8000' || echo "OK: port 8000 free"

# Если всё ещё занят — найти PID и убить
sudo fuser -k 8000/tcp 2>/dev/null && sleep 2

# C. Поднять заново (профиль выбери осознанно)
docker compose --profile prod up -d --build              # db + app (хост-nginx отдельно)
# ИЛИ
docker compose --profile full up -d --build              # db + app + nginx в compose

# D. Подтвердить
sleep 6
docker compose ps
curl -sS http://127.0.0.1:8000/healthz
```

**Если занят НЕ docker, а процесс на хосте:**

```bash
# В выводе ss будет: users:(("uvicorn",pid=12345,fd=7)) или ("python",...)
sudo ss -ltnp | grep ':8000'
sudo kill -TERM <PID>
# или все uvicorn-процессы разом
sudo pkill -f 'uvicorn app.main'
```

**Типичные причины:**

| Причина | Как распознать | Как избежать |
|---|---|---|
| Предыдущий `tracker-app-1` ещё жив | `docker ps -a` показывает его в статусе `Up` | `docker compose down` перед `up` |
| uvicorn напрямую (systemd/tmux/эксперимент) | `ss -ltnp` показывает `uvicorn` (НЕ `docker-proxy`) | Не запускать `uvicorn` вне compose на VPS |
| Активирован лишний профиль (`full` вместо `prod`) | В логе есть `tracker-nginx-1 Created`, хотя у вас хост-nginx | Запускай ТОЛЬКО с `--profile prod` для VPS |
| Два разных клона проекта конкурируют за 8000 | `docker ps -a` показывает два стека с разными путями | Оставить один compose-проект на VPS |

---

## 14. Проверка после деплоя (чек-лист «всё ОК»)

```bash
# 1. Healthz
curl -sS https://your-domain.com/healthz
# 2. Главная отвечает
curl -sI https://your-domain.com/ | head -3
# 3. Статика грузится
curl -sI https://your-domain.com/static/tailwindcss.js | head -3
# 4. Логин-страница рендерится
curl -sS https://your-domain.com/login | grep -E '<title>|<h1' | head -3
# 5. БД активна
docker compose exec db pg_isready -U tracker -d tracker
```

Все пять пунктов должны пройти без ошибок → деплой успешен.

---

## Шпаргалка по env-ключам

| Переменная | Где задаётся | Обязательна в prod |
|---|---|---|
| `APP_ENV` | `.env` | ✅ должно быть `production` |
| `POSTGRES_PASSWORD` | `.env` | ✅ ≥16 chars |
| `JWT_SECRET_KEY` | `.env` | ✅ **≥32 chars**, не `change-me-...` |
| `CREDENTIALS_ENCRYPTION_KEY` | `.env` | ✅ **≥32 chars**, не `change-me-...` |
| `TG_WEBHOOK_SECRET` | `.env` | ⚠️ если Telegram включён |
| `TG_BOT_TOKEN` | `.env` | ⚠️ желателен, опционален для теста |
| `TG_BOT_USERNAME` | `.env` | для `/start` ссылки в UI |
| `TG_POLLING` | `.env` | webhook либо polling, не оба |

Production gate (`app/config.py`) валит старт, если хоть один из `JWT_SECRET_KEY` / `CREDENTIALS_ENCRYPTION_KEY`:
1. содержит `change-me-` (тестовый placeholder);
2. короче 32 символов.

Это сделано намеренно — лучше упасть сразу, чем ехать в production со сломанными секретами (тест: `tests/test_config.py::test_*production*`).

---

## Если что-то не работает

1. **Логи:** `docker compose logs --tail=100 app` — скопируй последние 50 строк.
2. **Production gate падает?** Проверь длину ключей (`echo -n $JWT_SECRET_KEY | wc -c`).
3. **502 Bad Gateway?** Nginx стартанул раньше app или app упал. Проверь `docker compose ps`.
4. **400 CSRF?** Куки не доходят. В `docker-compose.yml` `CORS`-параметры — для прямого доступа на `127.0.0.1:8000` без nginx.
5. **Telegram не отвечает?** Проверь webhook через `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`.

## 13.2. Troubleshooting: «порт точно свободен, но ошибка та же»

**Симптом:** `ss -ltnp | grep ':8000'` **пусто**, никакого процесса не видно, но при `docker compose up -d --build` Docker снова пишет `address already in use: 127.0.0.1:8000`.

Это значит, что блокировка не на уровне пользовательского процесса, а на уровне ядра/Docker. Три типичные причины:

### Причина A: залипшие правила iptables (самая частая)

Docker пробрасывает порт через цепочку `DOCKER` в `nat`. После внезапной остановки контейнера правило может остаться, **процесса уже нет, а резервация DNAT висит**.

```bash
sudo iptables -t nat -L DOCKER -n --line-numbers | head -10
# Видно правило: 0  0  DNAT  tcp  --  *  *  0.0.0.0/0  0.0.0.0/0  tcp dpt:8000 to:172.18.0.2:8000
```

Фикс:
```bash
cd /opt/tracker
docker compose down --remove-orphans

# Сбросить только Docker-цепочки (не трогает host-firewall ufw)
sudo iptables -t nat -F DOCKER
sudo iptables -t nat -F DOCKER-USER

# Поднять заново
docker compose --profile prod up -d --build

sleep 8
docker compose ps
curl -sS -m 8 http://127.0.0.1:8000/healthz; echo
```

### Причина B: контейнер app падает мгновенно, но Docker уже зарезервировал сокет

Docker **заранее** резервирует bind на `127.0.0.1:8000 при старте контейнера, до того как приложение реально поднимется. Если app крашится (production gate, миграция, ошибка в коде), Docker пытается пересоздать контейнер — а сокет ещё считается занятым предыдущей попыткой.

**Диагностика** — обязательно посмотри лог:
```bash
docker compose logs --no-log-prefix --tail=100 app 2>&1 | tail -40
```

Самые частые причины мгновенного краша app:

1. **Production gate валит старт** — секреты короче 32 или содержат `change-me-`:
   ```bash
   cd /opt/tracker
   grep -E '^(JWT_SECRET_KEY|CREDENTIALS_ENCRYPTION_KEY|APP_ENV)' .env
   echo "$JWT_SECRET_KEY" | wc -c
   echo "$CREDENTIALS_ENCRYPTION_KEY" | wc -c
   ```
   Должно быть ≥32 символа. Если меньше — повтори шаг 3 из runbook.

2. **PostgreSQL ещё не готов** (race condition):
   ```
   sqlalchemy.exc.OperationalError: connection to server ... failed: Connection refused
   ```
   Лог `docker compose logs db` показывает стартует ли БД. Если часто — добавить healthcheck-retry в `docker-compose.yml`.

3. **Миграция падает** на старте (например, 016 на пустой БД):
   ```
   alembic.util.exc.CommandError: Can't locate revision identified by '016'
   ```
   Фикс: `docker compose exec app alembic upgrade head` принудительно.

**Фикс общего случая (принудительная чистка):**
```bash
cd /opt/tracker

# Полная остановка + чистка iptables + prune сетей
docker compose down --remove-orphans
sudo iptables -t nat -F DOCKER 2>/dev/null
sudo iptables -t nat -F DOCKER-USER 2>/dev/null
docker network prune -f 2>&1 | tail -3

# Поднять, но сначала одной БД
docker compose up -d db
docker compose logs db | grep -E 'database system is ready|listening'
docker compose exec db pg_isready -U tracker -d tracker   # "accepting connections"

# Теперь app
docker compose up -d app --no-deps
docker compose logs app | tail -30

sleep 8
curl -sS -m 8 http://127.0.0.1:8000/healthz; echo
```

### Причина C: имя сети `tracker_default` уже используется другим compose-проектом

Если на VPS два клона проекта (или один проект + один экспериментальный), оба хотят сеть `tracker_default`. Резервирование bind на `127.0.0.1:8000` происходит в сетевом namespace ядра, и для двух проектов с одним именем сети возникает коллизия.

```bash
docker network ls --format 'table {{.Name}}\t{{.Driver}}' | grep tracker
# Если две строки с именем tracker_default (от разных проектов) — конфликт
```

**Фикс — переименовать проект:**
```bash
cd /opt/tracker
docker compose --project-name tracker1 down --remove-orphans 2>&1 | tail -3
docker compose --project-name tracker1 --profile prod up -d --build
# Второй клон будет называть сеть tracker2_default и не будет конфликтовать
```

### Диагностический блок «всё-в-одном» (если ничего из A/B/C не помогло)

```bash
cd /opt/tracker

# 1. Прямая правда по порту на уровне ядра (включая не-LISTEN сокеты)
sudo ss -ltnap state listening 2>/dev/null | grep ':8000' || echo "[kernel] 8000 free"
sudo ss -ap state time-wait 2>/dev/null | grep ':8000' | head -3 || echo "[kernel] no TIME_WAIT"

# 2. Все контейнеры со словом tracker
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -iE 'tracker|practice|NAMES'

# 3. Логи app — настоящая причина краша
docker compose logs --no-log-prefix --tail=80 app 2>&1 | tail -40

# 4. iptables DOCKER-цепочка
sudo iptables -t nat -L DOCKER -n 2>&1 | head -10

# 5. Все compose-сети
docker network ls --format 'table {{.Name}}\t{{.Driver}}' | grep -E 'tracker|NAME'
```

Скопируйте весь вывод блока в чат — по нему точно увидим причину.

---

> Все перечисленные проверки работают без интернета, только через локальные ресурсы.
