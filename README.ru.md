# Telegram Weather Bot

[English](README.md) | [Русский](README.ru.md)

Телеграм-бот, который присылает ежедневную сводку по погоде: текущие условия, почасовой
разбор остатка дня, прогноз на завтра, что надеть и заметку для метеозависимых.
Написан на Python, работает на любом Linux-сервере, хранит данные в SQLite, не требует
ничего платить.

Работает на [OpenWeatherMap](https://openweathermap.org/) и Telegram Bot API.

---

## Возможности

### Ежедневная сводка

Каждое сообщение собирается из текущей погоды (`/weather`) и прогноза 3-часовыми шагами
(`/forecast`) — то есть вы видите реальную картину дня, а не одно число:

```
🌍 Москва
☁️ Пасмурно

🌡 Сейчас: 15,9°C  ·  ощущается как 15,9°C
💧 Влажность: 92%   💨 Ветер: 4,7 м/с   📊 Давление: 1018 гПа

🕐 Остаток дня — сейчас утро
   ▁█▅▁  16,4 → 16,2°C
   12:00    16,4°C  ☁️ Пасмурно
   15:00    19,4°C  ☁️ Пасмурно
   18:00    17,8°C  ☁️ Пасмурно
   21:00    16,2°C  ☁️ Пасмурно

🔮 Что ожидается
🌡 Температура. Сейчас 15,9°C, дальше растёт: 16,2…19,4°C. Ночью 16,2°C...
🌧 Осадки. Сухо, осадков не ожидается.
📈 Давление. Сейчас 1018 гПа, ... почти стабильно (Δ -1 гПа) — ровная погода
   без резких перемен. (давление ровное — метеозависимым, скорее всего, всё нормально)

👕 Что надеть
   👕 Основа: лёгкая куртка или толстовка
   👖 Низ: джинсы или брюки

🟢 Самочувствие: хорошее
   📎 Факторы: резких перемен нет

   Что может беспокоить:
   • явных симптомов не ожидается

   Что сделать:
   • обычный день, специальных мер не требуется
```

Отдельный блок **«Завтра»**: ночной и дневной диапазоны температур, преобладающая погода,
окна осадков, ветер, тренд давления и две-три подсказки по одежде.

### Команды

| Команда / кнопка | Что делает |
|---|---|
| `/start` | приветствие и главное меню |
| 🌤 Погода сейчас | текущая погода + остаток дня + ожидания + одежда |
| 🌙 Завтра | `/tomorrow` — прогноз на следующие сутки |
| 📅 На 5 дней | прогноз по дням |
| 📍 Указать город | задать город (геокодинг через OpenWeatherMap) |
| ⏰ Время рассылки | выбрать время ежедневной сводки |
| ⚙️ Настройки | единицы и язык (в разработке) |
| ❌ Отписаться | отключить ежедневную сводку |

Можно просто написать название города — бот поймёт.

### Из чего собираются сводки

- **Остаток дня** — 3-часовые слоты от текущего момента до полуночи по местному времени
  города, со спарклайном температуры и вероятностью осадков по каждому слоту.
- **Что ожидается** — тренд температуры с ночным минимумом, окна осадков с вероятностью
  и миллиметрами, направление и скорость изменения давления с человеческим объяснением.
- **Что надеть** — до восьми советов на основе ощущаемой температуры (восемь градаций),
  ветра, влажности, дождя, дневного перепада температур и ночного минимума.
- **Самочувствие** — изменение давления, скачки температуры, ветер и сырость на холоде
  сводятся в четыре уровня риска, а затем в списки «что может беспокоить» и «что сделать».

Если запрос прогноза не прошёл, сообщение деградирует мягко: блок текущей погоды и советы
по одежде всё равно уйдут, отпадут только блоки про день.

---

## Как начать

### 1. Получить токен Telegram-бота

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather).
2. Отправьте `/newbot`.
3. Задайте отображаемое имя и username, оканчивающийся на `bot`.
4. Бот ответит токеном вида `123456789:AAExampleToken...`. Держите его в секрете.

Если нужен собственный Telegram user id для `ADMIN_ID`, напишите боту [@getmyid_bot](https://t.me/getmyid_bot).

### 2. Получить API-ключ OpenWeatherMap

1. Зарегистрируйтесь на [openweathermap.org](https://openweathermap.org/).
2. Подтвердите почту и откройте [API keys](https://home.openweathermap.org/api_keys).
3. Создайте новый ключ и скопируйте его.

**Бесплатного тарифа достаточно** — 60 запросов в минуту и 1000 в сутки с запасом покрывают
несколько пользователей. Новый ключ активируется в течение пары часов; до этого API отвечает `401`.

Бот использует два эндпоинта: `/data/2.5/weather` (текущая погода) и `/data/2.5/forecast`
(3-часовые шаги на 5 дней). Оба доступны на бесплатном тарифе.

### 3. Настройте проект

```bash
git clone https://github.com/PrEvAl85/telegram-weather-bot.git
cd telegram-weather-bot

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
```

Отредактируйте `.env`:

```ini
BOT_TOKEN=123456789:AAExampleTokenReplaceMe
WEATHER_API_KEY=your_openweathermap_api_key
TIMEZONE=Europe/Moscow
```

`.env` добавлен в `.gitignore` и никогда не попадёт в репозиторий.

### 4. Запустите

```bash
python bot.py
```

Бот сам создаст `data/weather_bot.db` и `logs/bot.log`. Напишите ему в Телеграм, задайте
город и время рассылки — готово.

---

## Развёртывание на Linux-сервере

Подойдёт минимальный VPS у любого провайдера. Ниже пример для Ubuntu 24.04.

```bash
# системный пользователь, чтобы бот никогда не работал от root
sudo useradd -r -m -s /usr/sbin/nologin weatherbot
sudo mkdir -p /opt/weather-bot
sudo chown weatherbot:weatherbot /opt/weather-bot

# код и виртуальное окружение
sudo -u weatherbot git clone https://github.com/PrEvAl85/telegram-weather-bot.git /opt/weather-bot
sudo -u weatherbot python3 -m venv /opt/weather-bot/venv
sudo -u weatherbot /opt/weather-bot/venv/bin/pip install -r /opt/weather-bot/requirements.txt
```

Создайте `/opt/weather-bot/.env` от root (`chown weatherbot:weatherbot`, `chmod 600`),
затем настройте systemd:

```bash
sudo cp /opt/weather-bot/deploy/weather-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now weather-bot
sudo systemctl status weather-bot
```

Логи:

```bash
sudo journalctl -u weather-bot -f
```

### Ротация логов

`deploy/logrotate-weather-bot` ротирует лог ежедневно, а также при превышении 50 МБ.
Хранятся 7 архивов, сжатие gzip.

```bash
sudo apt install -y logrotate
sudo cp /opt/weather-bot/deploy/logrotate-weather-bot /etc/logrotate.d/weather-bot
sudo logrotate -d /etc/logrotate.d/weather-bot   # пробный прогон, проверяет конфиг
```

`copytruncate` здесь обязателен: Python держит открытый файловый дескриптор на логе, поэтому
без этой опции бот продолжал бы писать в старый файл, а новый остался бы пустым навсегда.

### Обновление

```bash
sudo -u weatherbot git -C /opt/weather-bot pull
sudo systemctl restart weather-bot
```

---

## Структура проекта

```
bot.py                        вся логика: хендлеры, форматирование, планировщик
config.py                     читает настройки из .env
requirements.txt              зафиксированные зависимости
.env.example                  шаблон для .env
deploy/
  weather-bot.service         юнит systemd
  logrotate-weather-bot       конфиг ротации логов
data/weather_bot.db           база SQLite (создаётся при запуске, не в репозитории)
logs/bot.log                  лог (создаётся при запуске, не в репозитории)
```

### База данных

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

### Ключевые функции

| Функция | Назначение |
|---|---|
| `get_forecast_safe` | запрос прогноза, который никогда не бросает исключение |
| `collect_day` | раскладывает слоты прогноза по локальной дате (`day_offset=0` — сегодня, `1` — завтра) |
| `format_current` | собирает основную сводку |
| `format_tomorrow` | собирает блок «Завтра» |
| `format_forecast` | сводка на пять дней |
| `outlook_temperature` / `outlook_rain` / `outlook_pressure` | три строки «Что ожидается» |
| `advice_clothes` | советы по одежде |
| `wellbeing` | оценка дня и блок «Самочувствие» |
| `_rain_windows` | склеивает соседние мокрые слоты в временные окна |
| `_sparkline` | спарклайн температуры из символов блока |

Числа форматируются через `_fmt` — с десятичной запятой, как принято в ru-локали.

---

## Безопасность

- Токен бота и API-ключ лежат только в `.env`. Не коммитьте его и не вставляйте в README
  или в issue.
- `python-telegram-bot` пишет полный URL запроса вместе с токеном на уровне `INFO`. Если
  делитесь логами, сначала их за redact'ьте — либо поднимите HTTP-логгеры до `WARNING`:

  ```python
  import logging
  logging.getLogger("httpx").setLevel(logging.WARNING)
  logging.getLogger("telegram").setLevel(logging.WARNING)
  ```

- Сервис работает от непривилегированного системного пользователя, а не от root.
- `/opt/weather-bot/.env` должен иметь права `600`.

---

## Поддержка проекта

Telegram Weather Bot создан и поддерживается в свободное время; он бесплатный и без рекламы.
Если он оказался полезным, можно помочь его развитию:

- ⭐ **Поставить звезду на GitHub** — [PrEvAl85/telegram-weather-bot](https://github.com/PrEvAl85/telegram-weather-bot)
- 🐛 **Сообщить о баге или предложить идею** — [Issues](https://github.com/PrEvAl85/telegram-weather-bot/issues)
- 📣 **Рассказать другим** — поделиться с теми, кому это может пригодиться

**Финансовая поддержка:**

- ⭐ **Boosty** — https://boosty.to/pws/donate
- 💛 **DonationAlerts** — https://www.donationalerts.com/r/photowithoutstudio

Другие проекты того же автора: [Life Calendar](https://github.com/PrEvAl85/life-calendar-android)
и другие на [github.com/PrEvAl85](https://github.com/PrEvAl85).

Спасибо, что пользуетесь ботом!

---

## Лицензия

GPL-3.0. Подробности в файле [LICENSE](LICENSE).