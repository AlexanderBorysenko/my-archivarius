# AI Diary — деплой

## Передумови

- VPS з Docker і Docker Compose
- Домен з HTTPS (reverse proxy через CloudPanel, Caddy, nginx тощо)
- Telegram-бот (створений через @BotFather)

## 1. Створити Telegram-бота

1. Відкрий **@BotFather** в Telegram → `/newbot`
2. Обери ім'я та username → отримаєш токен виду `7123456789:AAH...`
3. Число до `:` — це **Bot ID** (наприклад, `7123456789`)
4. `/setdomain` → обери бота → вкажи домен (наприклад, `journal.example.com`)

Домен обов'язковий — без нього вхід через Telegram на веб-інтерфейсі не працюватиме.

## 2. Отримати API ключі

| Ключ                | Для чого                                  | Де отримати                              |
| ------------------- | ----------------------------------------- | ---------------------------------------- |
| `ANTHROPIC_API_KEY` | Claude API (генерація записів, хайлайтів) | https://console.anthropic.com → API Keys |
| `OPENAI_API_KEY`    | Whisper API (транскрибація голосових)     | https://platform.openai.com → API Keys   |

## 3. Клонувати та налаштувати

```bash
git clone https://github.com/AlexanderBorysenko/bachelor-job-ai-journal.git ai-diary
cd ai-diary
cp .env.example .env
nano .env
```

Заповнити `.env`:

```env
MONGODB_URL=mongodb://mongodb:27017
MONGODB_DB_NAME=ai_diary

TELEGRAM_BOT_TOKEN=7123456789:AAHxxx_твій_токен
VITE_TELEGRAM_BOT_ID=7123456789
TELEGRAM_WEBHOOK_URL=https://journal.example.com/api/webhook/telegram

ANTHROPIC_API_KEY=sk-ant-api03-твій_ключ
CLAUDE_MODEL=claude-sonnet-4-6
OPENAI_API_KEY=sk-proj-твій_ключ

JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

AUDIO_FILES_PATH=/app/audio_files
```

Згенерувати `JWT_SECRET_KEY`:

```bash
openssl rand -hex 32
```

## 4. Запустити

```bash
docker compose up -d --build
```

Перший запуск — 3-5 хв. Перевірити: `https://journal.example.com/api/health` → `{"status": "ok"}`.

## 5. Reverse proxy

Створити reverse proxy для домену на порт `3004` (або який вказано в `docker-compose.yml`).
Frontend nginx всередині контейнера сам проксює `/api/` запити на backend.

## 6. Зареєструвати webhook

### Обмеження Telegram

Telegram не доставляє webhook-запити на IP-адреси зі своїх власних діапазонів (`91.108.0.0/16`, `149.154.160.0/20`) — це захист від SSRF.

Перевірити IP сервера: `dig your-domain.com +short`. Якщо IP починається з `91.108.` або `149.154.` — потрібен проксі (див. нижче).

### Варіант A: Прямий webhook (якщо IP не в діапазоні Telegram)

```bash
curl -X POST "https://api.telegram.org/bot<ТОКЕН>/setWebhook" -H "Content-Type: application/json" -d '{"url": "https://journal.example.com/api/webhook/telegram"}'
```

### Варіант B: Через Cloudflare Tunnel (якщо IP в діапазоні Telegram)

1. Встановити `cloudflared`:

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

2. Створити systemd-сервіс для постійної роботи:

```bash
sudo tee /etc/systemd/system/cloudflared-tunnel.service > /dev/null <<'EOF'
[Unit]
Description=Cloudflare Quick Tunnel for Telegram Webhook
After=network.target docker.service

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:3004
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared-tunnel
```

3. Отримати URL тунелю:

```bash
journalctl -u cloudflared-tunnel --no-pager -n 20 | grep "trycloudflare.com"
```

4. Встановити webhook на URL тунелю:

```bash
curl -X POST "https://api.telegram.org/bot<ТОКЕН>/setWebhook" -H "Content-Type: application/json" -d '{"url": "https://TUNNEL-URL.trycloudflare.com/api/webhook/telegram"}'
```

> **Увага:** Quick Tunnel (без акаунта Cloudflare) генерує новий URL при кожному перезапуску сервісу.
> Після перезавантаження сервера потрібно оновити webhook URL.
> Для стабільного URL створіть безкоштовний Cloudflare-акаунт і налаштуйте Named Tunnel.

### Перевірка webhook

```bash
curl "https://api.telegram.org/bot<ТОКЕН>/getWebhookInfo"
```

Очікувана відповідь: `"description":"Webhook was set"`, `"pending_update_count": 0`.

## 7. Перевірити роботу

- **Веб:** відкрити `https://journal.example.com` → "Увійти через Telegram" → авторизація
- **Бот:** знайти бота в Telegram → Start → надіслати повідомлення → `/bake`

---

## Оновлення

```bash
cd ai-diary
git pull
docker compose up -d --build
```

## Зупинка

```bash
docker compose down        # зберегти дані
docker compose down -v     # видалити дані
```

## Логи

```bash
docker compose logs -f           # всі сервіси
docker compose logs -f backend   # тільки backend
```

## Тести

```bash
docker compose exec backend python -m pytest tests/ -v
```

## Типові проблеми

| Проблема                               | Рішення                                                                         |
| -------------------------------------- | ------------------------------------------------------------------------------- |
| `port already in use`                  | Змінити порт у `docker-compose.yml` або зупинити конфлікт                       |
| Бот не відповідає                      | Перевірити webhook: `curl .../getWebhookInfo`                                   |
| Webhook: `Connection timed out`        | IP сервера в діапазоні Telegram — налаштувати Cloudflare Tunnel (розділ 6B)     |
| Webhook URL змінився після перезапуску | Quick Tunnel дає новий URL — повторити `setWebhook` або перейти на Named Tunnel |
| Telegram Login не працює               | Перевірити домен у BotFather (`/setdomain`)                                     |
| Помилка транскрибації                  | Перевірити `OPENAI_API_KEY`, баланс на platform.openai.com                      |
| Помилка запікання                      | Перевірити `ANTHROPIC_API_KEY`, баланс на console.anthropic.com                 |
| Біла сторінка                          | DevTools → Console, подивитись помилку                                          |
