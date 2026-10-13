# Telegram Weather Bot

[English](README.md) | [Русский](README.ru.md)

A Telegram bot that sends you a daily weather briefing: current conditions, an hour-by-hour
walk through the rest of the day, a forecast for tomorrow, what to wear, and a wellbeing note
for weather-sensitive people. Written in Python, runs on any Linux VPS, stores data in SQLite,
costs nothing to run.

Based on the [OpenWeatherMap](https://openweathermap.org/) API and the Telegram Bot API.

---

## Features

### The daily briefing

Every message is assembled from the current observation (`/weather`) and a 3-hour forecast
(`/forecast`), so you get a real picture of the day instead of a single number:

```
🌍 London
☁️ Пасмурно

🌡 Сейчас: 9,3°C  ·  ощущается как 8,8°C
💧 Влажность: 87%   💨 Ветер: 4,2 м/с   📊 Давление: 1014 гПа

🕐 Остаток дня — сейчас утро
   ▅▂▁▄██▆▆  9,3 → 17,2°C
   12:00     9,3°C  ☁️ Пасмурно
   15:00    13,8°C  🌦 Небольшой дождь  💧40%
   18:00    17,2°C  ⛅️ Облачно

🔮 Что ожидается
🌡 Температура. Сейчас 9,3°C, дальше растёт: 9,3…17,2°C. Ночью 9,3°C...
🌧 Осадки. Возможен дождь: 15:00–18:00, вероятность до 40%.
📈 Давление. Сейчас 1014 гПа, ... падает на 6 гПа — похоже на приближение фронта...
   (давление немного снижается — может начаться лёгкая головная боль)

👕 Что надеть
   🧥 Основа: куртка или тёплый плащ
   💨 Ветер сильный — ветровка, застёгивай куртку до горла
   ☂️ Возможен небольшой дождь — зонт в сумку не помешает
   👖 Низ: джинсы или брюки
   👟 Обувь: непромокаемые кроссовки или ботинки

🟡 Самочувствие: нормальное
   📎 Факторы: давление падает на 6 гПа за ~9 ч, ветер до 12,0 м/с

   Что может беспокоить:
   • головная боль, скачки артериального давления
   • раздражительность от ветра

   Что сделать:
   • не планируй ничего изнуряющего, держи воду под рукой
   • на ветру меньше открытых участков тела
```

Plus a separate **Tomorrow** block: night and day temperature ranges, dominant weather,
precipitation windows, wind, pressure trend, and two or three clothing notes.

### Commands

| Command / button | What it does |
|---|---|
| `/start` | greeting and the main menu |
| 🌤 Погода сейчас | current weather + rest of the day + expectations + clothing |
| 🌙 Завтра | `/tomorrow` — tomorrow's forecast |
| 📅 На 5 дней | five-day forecast |
| 📍 Указать город | set your city (geocoded through OpenWeatherMap) |
| ⏰ Время рассылки | pick the time for your daily briefing |
| ⚙️ Настройки | units and language (work in progress) |
| ❌ Отписаться | stop the daily briefing |

You can also just type a city name — the bot picks it up.

### What the briefings are built from

- **Rest of the day** — 3-hour forecast slots from now until midnight, in the city's local
  time, with a temperature sparkline and per-slot precipitation probability.
- **Expectations** — temperature trend with the night minimum, precipitation windows with
  probability and millimetres, pressure direction and rate with a plain-language reading.
- **What to wear** — up to eight notes driven by apparent temperature (eight tiers), wind,
  humidity, rain, the day's temperature swing, and the night minimum.
- **Wellbeing** — pressure change, temperature swings, wind and damp cold are scored into
  four risk levels, then turned into "what might bother you" and "what to do" lists.

If the forecast request fails, the message degrades gracefully: the current-conditions block
and the clothing advice still go out, only the day-ahead parts are dropped.

---

## Getting started

### 1. Get a Telegram bot token

1. Open Telegram and find [@BotFather](https://t.me/BotFather).
2. Send `/newbot`.
3. Pick a display name and a username ending in `bot`.
4. BotFather replies with a token like `123456789:AAExampleToken...`. Keep it secret.

You can use `@getmyid_bot` in Telegram if you need your own user id for `ADMIN_ID`.

### 2. Get an OpenWeatherMap API key

1. Sign up at [openweathermap.org](https://openweathermap.org/).
2. Confirm your email and go to [API keys](https://home.openweathermap.org/api_keys).
3. Create a new key and copy it.

The **free tier is enough** — 60 calls/minute and 1000 calls/day covers a handful of users.
New keys take up to a couple of hours to activate; the API answers `401` until then.

The bot calls two endpoints: `/data/2.5/weather` (current) and `/data/2.5/forecast` (3-hour
steps, 5 days). Both are on the free tier.

### 3. Configure the project

```bash
git clone https://github.com/PrEvAl85/telegram-weather-bot.git
cd telegram-weather-bot

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
```

Edit `.env`:

```ini
BOT_TOKEN=123456789:AAExampleTokenReplaceMe
WEATHER_API_KEY=your_openweathermap_api_key
TIMEZONE=Europe/Moscow
```

`.env` is in `.gitignore` and will never be committed.

### 4. Run it

```bash
python bot.py
```

The bot creates `data/weather_bot.db` and `logs/bot.log` automatically. Talk to it in Telegram,
set your city and your briefing time, and you are done.

---

## Deployment on a Linux server

A minimal VPS from any provider is enough. The example below uses Ubuntu 24.04.

```bash
# system user, so the bot never runs as root
sudo useradd -r -m -s /usr/sbin/nologin weatherbot
sudo mkdir -p /opt/weather-bot
sudo chown weatherbot:weatherbot /opt/weather-bot

# code and virtualenv
sudo -u weatherbot git clone https://github.com/PrEvAl85/telegram-weather-bot.git /opt/weather-bot
sudo -u weatherbot python3 -m venv /opt/weather-bot/venv
sudo -u weatherbot /opt/weather-bot/venv/bin/pip install -r /opt/weather-bot/requirements.txt
```

Create `/opt/weather-bot/.env` as root (`chown weatherbot:weatherbot`, `chmod 600`), then set
up systemd:

```bash
sudo cp /opt/weather-bot/deploy/weather-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now weather-bot
sudo systemctl status weather-bot
```

Logs:

```bash
sudo journalctl -u weather-bot -f
```

### Log rotation

`deploy/logrotate-weather-bot` rotates the log file daily, and also whenever it grows past
50 MB. Seven archives are kept and compressed with gzip.

```bash
sudo apt install -y logrotate
sudo cp /opt/weather-bot/deploy/logrotate-weather-bot /etc/logrotate.d/weather-bot
sudo logrotate -d /etc/logrotate.d/weather-bot   # dry run, verifies the config
```

`copytruncate` is required: Python holds an open file descriptor on the log, so without it
the bot would keep writing into the rotated file and the new one would stay empty forever.

### Updating

```bash
sudo -u weatherbot git -C /opt/weather-bot pull
sudo systemctl restart weather-bot
```

---

## Project structure

```
bot.py                        all logic: handlers, formatting, the scheduler
config.py                     reads settings from .env
requirements.txt              pinned dependencies
.env.example                  template for .env
deploy/
  weather-bot.service         systemd unit
  logrotate-weather-bot       log rotation config
data/weather_bot.db           SQLite database (created at runtime, not committed)
logs/bot.log                  log file (created at runtime, not committed)
```

### Database

```sql
CREATE TABLE users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    city          TEXT DEFAULT 'Москва',
    lat           REAL,
    lon           REAL,
    notify_time   TEXT,
    units         TEXT DEFAULT 'metric',
    lang          TEXT DEFAULT 'ru',
    subscribed    INTEGER DEFAULT 1
)
```

### Key functions

| Function | Purpose |
|---|---|
| `get_forecast_safe` | forecast request that never raises |
| `collect_day` | groups forecast slots by local date (`day_offset=0` today, `1` tomorrow) |
| `format_current` | builds the main briefing |
| `format_tomorrow` | builds the tomorrow block |
| `format_forecast` | five-day summary |
| `outlook_temperature` / `outlook_rain` / `outlook_pressure` | the three "expectations" lines |
| `advice_clothes` | the clothing notes |
| `wellbeing` | scores the day and builds the wellbeing block |
| `_rain_windows` | merges neighbouring wet slots into time windows |
| `_sparkline` | temperature sparkline from block characters |

Numbers are formatted with `_fmt`, which uses a decimal comma, the Russian locale convention.

---

## Security notes

- The bot token and API key live in `.env` only. Never commit it, never paste it into a README
  or an issue.
- `python-telegram-bot` logs the full request URL, including the token, at `INFO`. If you share
  logs, redact them first — or raise the HTTP loggers to `WARNING`:

  ```python
  import logging
  logging.getLogger("httpx").setLevel(logging.WARNING)
  logging.getLogger("telegram").setLevel(logging.WARNING)
  ```

- The service runs as an unprivileged system user, not root.
- `/opt/weather-bot/.env` should be mode `600`.

---

## Support the Project

Telegram Weather Bot is created and maintained in free time; it is free and ad-free.
If it is useful to you, you can help its development:

- ⭐ **Star on GitHub** — [PrEvAl85/telegram-weather-bot](https://github.com/PrEvAl85/telegram-weather-bot)
- 🐛 **Bug reports and ideas** — [Issues](https://github.com/PrEvAl85/telegram-weather-bot/issues)
- 📣 **Tell others** — share it with those who might find it useful

**Financial support:**

- ⭐ **Boosty** — https://boosty.to/pws/donate
- 💛 **DonationAlerts** — https://www.donationalerts.com/r/photowithoutstudio

Other projects by the same author: [Life Calendar](https://github.com/PrEvAl85/life-calendar-android)
and others on [github.com/PrEvAl85](https://github.com/PrEvAl85).

Thank you for using the bot!

---

## License

GPL-3.0. See [LICENSE](LICENSE).