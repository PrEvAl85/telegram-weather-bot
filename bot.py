#!/usr/bin/env python3
# Telegram Weather Bot
# Copyright (C) 2026 PrEvAl85
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import html
import logging
import os
import pytz
import sqlite3
import requests
import signal
import sys
from datetime import datetime, timedelta, timezone
from collections import Counter
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    CallbackContext, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import BOT_TOKEN, WEATHER_API_KEY, DB_PATH, LOG_PATH, ADMIN_ID

TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== СОСТОЯНИЯ ====================
SET_CITY, SET_TIME = range(2)

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        city TEXT DEFAULT 'Москва',
        lat REAL,
        lon REAL,
        notify_time TEXT,
        units TEXT DEFAULT 'metric',
        lang TEXT DEFAULT 'ru',
        subscribed INTEGER DEFAULT 1
    )''')
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_user(user_id, username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
              (user_id, username))
    conn.commit()
    conn.close()

def update_city(user_id, city, lat, lon):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET city=?, lat=?, lon=? WHERE user_id=?",
              (city, lat, lon, user_id))
    conn.commit()
    conn.close()

def update_time(user_id, notify_time):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET notify_time=? WHERE user_id=?",
              (notify_time, user_id))
    conn.commit()
    conn.close()

def toggle_subscription(user_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET subscribed=? WHERE user_id=?", (status, user_id))
    conn.commit()
    conn.close()

def get_all_subscribed_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, city, lat, lon, notify_time FROM users WHERE subscribed=1 AND notify_time IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return rows

# ==================== ПОГОДА ====================
def get_coordinates(city_name):
    url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_name}&limit=1&appid={WEATHER_API_KEY}"
    try:
        r = requests.get(url, timeout=10).json()
        if r:
            return r[0]['name'], r[0]['lat'], r[0]['lon']
    except Exception as e:
        logger.error(f"Ошибка геокодинга: {e}")
    return None, None, None

def get_current_weather(lat, lon, units='metric', lang='ru'):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units={units}&lang={lang}"
    return requests.get(url, timeout=10).json()

def get_forecast_5days(lat, lon, units='metric', lang='ru'):
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units={units}&lang={lang}"
    return requests.get(url, timeout=10).json()

def get_forecast_safe(lat, lon, units='metric', lang='ru'):
    """Прогноз 3-часовыми шагами. None, если не получилось — выдача деградирует мягко."""
    try:
        data = get_forecast_5days(lat, lon, units, lang)
    except Exception as e:
        logger.warning(f"Прогноз недоступен: {e}")
        return None
    return data if data.get('cod') in (200, '200') else None

# ==================== АНАЛИТИКА ПОГОДЫ ====================
SPARK_CHARS = "▁▂▃▄▅▆▇█"

WEATHER_ICONS = {
    2: "⛈", 3: "🌦",
    500: "🌦", 501: "🌧", 502: "🌧", 503: "🌧", 504: "🌧", 511: "🌨",
    520: "🌦", 521: "🌧", 522: "🌧", 531: "🌧",
    600: "🌨", 601: "🌨", 602: "❄️", 611: "🌨", 612: "🌨",
    615: "🌨", 616: "🌨", 620: "🌨", 622: "❄️",
    701: "🌫", 711: "🌫", 721: "🌫", 731: "🌪", 741: "🌫",
    751: "🌫", 761: "🌫", 762: "🌋", 771: "💨", 781: "🌀",
    800: "☀️", 801: "🌤", 802: "⛅️", 803: "☁️", 804: "☁️",
}

PRECIP_GROUPS = {2: "гроза", 3: "ливень", 5: "дождь", 6: "снег", 7: "смешанные осадки"}


def _esc(value):
    return html.escape(str(value), quote=False)


def _icon(code):
    return WEATHER_ICONS.get(code, "🌡")


def _precip_kind(code):
    """Что ожидается по коду WMO: дождь / снег / гроза / нет осадков."""
    return PRECIP_GROUPS.get(int(code) // 100)


def _local_time(ts, offset):
    """Время слота прогноза в местном времени точки."""
    return datetime.fromtimestamp(ts, timezone.utc) + timedelta(seconds=offset or 0)


def _part_of_day(hour):
    """Часть суток в именительном падеже — для заголовка «сейчас ...»."""
    if hour < 5:  return "ночь"
    if hour < 12: return "утро"
    if hour < 17: return "день"
    if hour < 22: return "вечер"
    return "ночь"


def _sparkline(temps):
    if not temps:
        return ""
    lo, hi = min(temps), max(temps)
    if hi - lo < 0.05:
        return SPARK_CHARS[3] * len(temps)
    return "".join(SPARK_CHARS[min(7, int((t - lo) / (hi - lo) * 7.99))] for t in temps)


def collect_day(forecast, now_local=None, day_offset=0):
    """Разбор прогноза по суткам. day_offset=0 — сегодня, 1 — завтра, и т. д.

    Для будущих суток вся дата целиком попадает в rest (там нет «прошедшей» части),
    поэтому логика разделения однозначна.
    """
    if not forecast or not forecast.get('list'):
        return None

    offset = (forecast.get('city') or {}).get('timezone', 0)
    now_local = now_local or datetime.now(timezone.utc) + timedelta(seconds=offset)
    target = now_local.date() + timedelta(days=day_offset)

    rest, past = [], []
    for item in forecast['list']:
        local = _local_time(item['dt'], offset)
        if local.date() != target:
            continue
        slot = {
            "dt": local,
            "temp": item['main']['temp'],
            "feels": item['main']['feels_like'],
            "pressure": item['main']['pressure'],
            "wind": item['wind']['speed'],
            "humidity": item['main']['humidity'],
            "pop": item.get('pop') or 0.0,
            "rain": (item.get('rain') or {}).get('3h', 0.0),
            "snow": (item.get('snow') or {}).get('3h', 0.0),
            "code": item['weather'][0]['id'],
            "desc": item['weather'][0]['description'].capitalize(),
        }
        (rest if (day_offset > 0 or local >= now_local) else past).append(slot)

    day = past + rest
    return {
        "now": now_local,
        "rest": rest,
        "past": past,
        "day": day,
        "temp_min": min((s['temp'] for s in day), default=None),
        "temp_max": max((s['temp'] for s in day), default=None),
        "feels_min": min((s['feels'] for s in day), default=None),
        "feels_max": max((s['feels'] for s in day), default=None),
    }


def _rain_windows(slots, threshold=0.25):
    """Склеивает соседние слоты с осадками в окна вида (час начала, час конца, макс. вероятность, мм)."""
    windows = []
    for slot in slots:
        wet = slot['pop'] >= threshold or slot['rain'] > 0 or slot['snow'] > 0
        if not wet:
            continue
        end = slot['dt'] + timedelta(hours=3)
        if windows and windows[-1]['end'] == slot['dt']:
            win = windows[-1]
            win['end'] = end
            win['pop'] = max(win['pop'], slot['pop'])
            win['mm'] += slot['rain'] + slot['snow']
        else:
            windows.append({
                "start": slot['dt'], "end": end,
                "pop": slot['pop'], "mm": slot['rain'] + slot['snow'],
                "code": slot['code'],
            })
    return windows


def outlook_temperature(summary, current_temp, current_feels):
    """Что с температурой: тренд на сегодня, диапазон остатка дня, как ощущается."""
    parts = []
    rest = summary['rest']

    if rest:
        lo, hi = summary['temp_min'], summary['temp_max']
        rest_lo = min(s['temp'] for s in rest)
        rest_hi = max(s['temp'] for s in rest)

        direction = "растёт" if rest_hi > current_temp + 1 else \
                    "падает" if rest_hi < current_temp - 1 else "почти без изменений"

        parts.append(f"Сейчас {_fmt(current_temp)}°C, дальше {direction}: "
                     f"{_fmt(rest_lo)}…{_fmt(rest_hi)}°C.")

        night = [s for s in rest if s['dt'].hour >= 21 or s['dt'].hour < 6]
        if night:
            parts.append(f"Ночью {_fmt(min(s['temp'] for s in night))}°C "
                         f"({_icon(night[-1]['code'])}, ощущается {_fmt(night[-1]['feels'])}°C).")

        if hi is not None and lo is not None and hi - lo >= 10:
            parts.append(f"Разброс за сутки большой: от {_fmt(lo)}°C до {_fmt(hi)}°C — "
                         f"смена слоёв обязательна.")
        parts.append(f"Ощущается как {_fmt(summary['feels_min'])}…{_fmt(summary['feels_max'])}°C.")
    else:
        parts.append(f"Сейчас {_fmt(current_temp)}°C, ощущается как {_fmt(current_feels)}°C. "
                     f"Прогноз на остаток дня недоступен.")

    return parts


def outlook_rain(summary):
    """Что с осадками: окна дождя/снега, вероятность, количество."""
    rest = summary['rest']
    if not rest:
        return ["Прогноз на остаток дня недоступен."]

    windows = _rain_windows(rest)
    if not windows:
        return ["Сухо, осадков не ожидается."]

    kinds = {w['code'] for w in windows}
    if any(int(c) // 100 == 6 for c in kinds):
        kind = "снег"
    elif any(int(c) // 100 == 2 for c in kinds):
        kind = "гроза и дождь"
    elif all(int(c) // 100 == 7 for c in kinds):
        kind = "морось"
    else:
        kind = "дождь"

    if len(windows) >= max(3, len(rest) * 0.6):
        timing = f"почти весь день ({_hh(windows[0]['start'])}–{_hh(windows[-1]['end'])})"
    elif len(windows) > 1:
        timing = ", ".join(f"{_hh(w['start'])}–{_hh(w['end'])}" for w in windows[:3])
    else:
        timing = f"{_hh(windows[0]['start'])}–{_hh(windows[0]['end'])}"

    total_mm = sum(w['mm'] for w in windows)
    top = max(w['pop'] for w in windows)
    line = f"Ожидается {kind}: {timing}, вероятность до {int(top * 100)}%"
    if total_mm >= 0.3:
        line += f", около {_fmt(total_mm)} мм"
    return [line + "."]


def outlook_pressure(current_pressure, summary):
    """Что с давлением: направление, скорость изменения, возможные последствия."""
    rest = (summary or {}).get('rest') or []
    if not rest:
        return [f"Сейчас {current_pressure} гПа, без изменений на сегодня."]

    window = rest[:3]  # ближайшие ~9 часов
    future = window[-1]['pressure']
    delta = future - current_pressure

    parts = [f"Сейчас {current_pressure} гПа, {rest[0]['dt'].strftime('%H:%M')} — {future} гПа"]

    if delta <= -4:
        parts.append("падает на " + f"{abs(delta)} гПа — похоже на приближение фронта, "
                                  "возможны осадки и усиление ветра")
    elif delta >= 4:
        parts.append(f"растёт на {delta} гПа — фронт прошёл, погода устойчивая, "
                     f"облачность прояснится")
    else:
        parts.append(f"почти стабильно (Δ {delta:+d} гПа) — ровная погода без резких перемен")

    day_min = min(s['pressure'] for s in summary['day'])
    day_max = max(s['pressure'] for s in summary['day'])
    if day_max - day_min >= 8:
        parts.append(f"за сутки давление «гуляет» в пределах {day_min}–{day_max} гПа")

    return [", ".join(parts) + "."]


def meteo_note(current_pressure, summary):
    """Короткая пометка в скобках к строке давления — только про давление.

    Подробный разбор про температуру выносится в отдельный блок «Самочувствие».
    """
    rest = (summary or {}).get('rest') or []
    if not rest:
        return "метеозависимым — резких перемен давления не видно"

    delta = rest[min(2, len(rest) - 1)]['pressure'] - current_pressure

    if delta <= -6:
        return "давление резко падает — головная боль и скачки АД вероятны"
    if delta <= -3:
        return "давление немного снижается — может начаться лёгкая головная боль"
    if delta >= 6:
        return "давление заметно растёт — самочувствие обычно улучшается"
    if delta >= 3:
        return "давление немного растёт — в целом без перемен"
    return "давление ровное — метеозависимым, скорее всего, всё нормально"


# Пороги факторов самочувствия: список (порог, вес), вес растёт по мере движения вниз по списку.
# Каждый список отсортирован по возрастанию |порога|, поэтому проход — сверху вниз до первого совпадения.
TEMP_SWING_RISK = [(6, 0), (10, 1), (15, 2), (20, 3)]
FEELS_SWING_RISK = [(8, 0), (12, 1), (16, 2), (22, 3)]
WIND_RISK = [(7, 0), (12, 1), (18, 2)]
DROP_RISK = [(-3, 0), (-6, 2), (-10, 3)]      # падение давления за ~9 ч
RISE_RISK = [(3, 0), (6, 1), (12, 2)]         # рост давления за ~9 ч


def _weigh(table, value):
    """Вес риска по таблице порогов.

    Таблицы отсортированы по возрастанию |порога|, поэтому берём вес самого
    крупного порога, который value превысил, — а не первого совпавшего.
    """
    magnitude = abs(value)
    weight = 0
    for threshold, weight_at in table:
        if magnitude >= abs(threshold):
            weight = weight_at
    return weight


def _grade(score):
    if score == 0:
        return "🟢", "хорошее"
    if score <= 2:
        return "🟡", "нормальное"
    if score <= 4:
        return "🟠", "тревожное"
    return "🔴", "плохое"


def wellbeing(feels, wind, summary, pressure):
    """Блок «Самочувствие»: сводит давление, скачки температуры, ветер и влажность.

    Считает суммарный риск и собирает из факторов, что может беспокоить и что делать.
    """
    rest = (summary or {}).get('rest') or []
    day = (summary or {}).get('day') or []
    if not rest:
        return None

    # --- факторы и суммарный риск ---
    factors = []
    score = 0

    # давление: падение бьёт сильнее роста, поэтому у них разные таблицы
    delta = rest[min(2, len(rest) - 1)]['pressure'] - pressure
    if delta < 0:
        p_risk = _weigh(DROP_RISK, delta)
    else:
        p_risk = _weigh(RISE_RISK, delta)
    if p_risk:
        score += p_risk
        word = "падает" if delta < 0 else "растёт"
        factors.append(f"давление {word} на {abs(delta)} гПа за ~9 ч")

    # перепад температуры воздуха за сутки
    temp_swing = 0
    t_risk = 0
    if summary.get('temp_max') is not None and summary.get('temp_min') is not None:
        temp_swing = summary['temp_max'] - summary['temp_min']
        t_risk = _weigh(TEMP_SWING_RISK, temp_swing)
        if t_risk:
            score += t_risk
            factors.append(f"перепад температуры {_fmt(temp_swing)}°C за сутки")

    # перепад «ощущаемой» температуры — ветер и влажность поверх воздушной
    feels_rest = [s['feels'] for s in rest]
    feels_swing = max(feels_rest) - min(feels_rest)
    # если воздушный перепад уже учтён, второй раз не засчитываем
    f_risk = 0 if t_risk else _weigh(FEELS_SWING_RISK, feels_swing)
    if f_risk:
        score += f_risk
        factors.append(f"ощущения меняются на {_fmt(feels_swing)}°C (ветер и влажность)")

    # ветер
    wind_max = max(s['wind'] for s in rest)
    w_risk = _weigh(WIND_RISK, wind_max)
    if w_risk:
        score += w_risk
        factors.append(f"ветер до {_fmt(wind_max)} м/с")

    # сырость на холоде
    humidity = max(s['humidity'] for s in rest)
    cold = min(feels_rest)
    if humidity >= 85 and cold <= 12:
        score += 1
        factors.append("сырой воздух на холоде")

    icon, label = _grade(score)

    # --- что может беспокоить ---
    symptoms = []
    if delta <= -3:
        symptoms.append("головная боль, скачки артериального давления")
        symptoms.append("вялость, тяжелее засыпать")
    if delta >= 3:
        symptoms.append("тонус, бессонница вечером")
    if temp_swing >= 10:
        symptoms.append("ломота в суставах и мышцах")
    if f_risk >= 2:
        symptoms.append("резкие перепады «ощущаемой» температуры")
    if wind_max >= 12:
        symptoms.append("раздражительность от ветра")
    if humidity >= 85 and cold <= 12:
        symptoms.append("одышка и тяжесть в груди на холоде")

    if not symptoms:
        symptoms.append("явных симптомов не ожидается")

    # --- рекомендации ---
    advice = []
    if delta <= -6:
        advice.append("избегай резких нагрузок, следи за давлением и пей воду")
    elif delta <= -3:
        advice.append("не планируй ничего изнуряющего, держи воду под рукой")
    elif delta >= 3:
        advice.append("всё спокойно, но не перебарщивай с кофеином вечером")

    if t_risk >= 2:
        advice.append("бери с собой верхнюю одежду — за день можно переодеться")
    if f_risk >= 2:
        advice.append("на перепадах лучше не спешить и не переохлаждаться")
    if w_risk:
        advice.append("на ветру меньше открытых участков тела")
    if humidity >= 85 and cold <= 12:
        advice.append("дыши через шарф или маску, береги горло")

    if not advice:
        advice.append("обычный день, специальных мер не требуется")

    out = [f"{icon} <b>Самочувствие:</b> {label}"]
    out.append("   📎 Факторы: " + ", ".join(factors[:3]) if factors
               else "   📎 Факторы: резких перемен нет")
    out.append("")
    out.append("   Что может беспокоить:")
    out += [f"   • {s}" for s in symptoms[:3]]
    out.append("")
    out.append("   Что сделать:")
    out += [f"   • {a}" for a in advice[:3]]

    return "\n".join(out)


def _fmt(value):
    """Температура в русской локали: десятичная запятая."""
    return "—" if value is None else f"{value:.1f}".replace(".", ",")


def _hh(dt):
    return dt.strftime("%H:%M")


def _day_table(summary):
    """Компактная таблица оставшихся 3-часовых слотов со спарклайном."""
    rest = summary['rest'][:6]
    if not rest:
        return []

    temps = [s['temp'] for s in rest]
    lines = [f"   {_sparkline(temps)}  {_fmt(temps[0])} → {_fmt(temps[-1])}°C"]
    for slot in rest:
        pop = f"  💧{int(slot['pop'] * 100)}%" if slot['pop'] >= 0.2 else ""
        lines.append(f"   {_hh(slot['dt'])}  {_fmt(slot['temp']):>6}°C  "
                     f"{_icon(slot['code'])} {slot['desc']}{pop}")
    return lines


def advice_clothes(current_feels, current_temp, wind, humidity, summary):
    """Развёрнутая рекомендация по одежде: по ощущениям, ветру, осадкам, дню и ночи."""
    tips = []

    if current_feels <= -15:
        tips.append("🧥 Основа: зимняя куртка с пуховиком или два слоя")
    elif current_feels <= -5:
        tips.append("🧥 Основа: тёплая зимняя куртка")
    elif current_feels <= 5:
        tips.append("🧥 Основа: плотная куртка или пальто, шапка и шарф")
    elif current_feels <= 12:
        tips.append("🧥 Основа: куртка или тёплый плащ")
    elif current_feels <= 17:
        tips.append("👕 Основа: лёгкая куртка или толстовка")
    elif current_feels <= 24:
        tips.append("👕 Основа: свитер или лёгкая куртка")
    elif current_feels <= 29:
        tips.append("👕 Основа: футболка, можно без верхнего слоя")
    else:
        tips.append("👕 Основа: лёгкая одежда, берите воду")

    if wind >= 10:
        tips.append("💨 Ветер сильный — ветровка, застёгивай куртку до горла")
    elif wind >= 5:
        tips.append("💨 Умеренный ветер — куртка точно пригодится")

    if humidity >= 85 and current_temp <= 12:
        tips.append("💧 Высокая влажность — лучше водоотталкивающая куртка")
    elif humidity <= 30 and current_feels >= 15:
        tips.append("🏜️ Сухой воздух — слизистые могут пересохнуть, возьми воду")

    if summary and summary['rest']:
        windows = _rain_windows(summary['rest'])
        top = max((w['pop'] for w in windows), default=0.0)
        total_mm = sum(w['mm'] for w in windows)
        snow = any(int(w['code']) // 100 == 6 for w in windows)
        if snow:
            tips.append("❄️ Возможен снег — обувь на протекторе, гололёд на дорогах")
        elif top >= 0.6 or total_mm >= 1:
            tips.append("☂️ Зонт обязательно, лучше взять непромокаемую куртку")
        elif top >= 0.25:
            tips.append("☂️ Возможен небольшой дождь — зонт в сумку не помешает")

        feels_rest = [s['feels'] for s in summary['rest']]
        if feels_rest:
            if current_feels < 20 and min(feels_rest) <= current_feels - 6:
                tips.append(f"📉 Дальше ощутимо холоднее (до {_fmt(min(feels_rest))}°C) — "
                            f"возьми куртку с собой")
            elif current_feels > 18 and max(feels_rest) >= current_feels + 6:
                tips.append(f"📈 Днём заметно теплее (до {_fmt(max(feels_rest))}°C) — "
                            f"верхний слой можно снять")

        night_min = summary['temp_min']
        if night_min is not None:
            if night_min <= -20:
                tips.append("🥶 Экстремальный мороз — максимальная защита, лицо закрыть")
            elif night_min <= 2:
                tips.append("🧣 Ночью около нуля или ниже — шапка, перчатки, тонкий шарф")

    wet_rest = summary['rest'] if summary and summary['rest'] else []
    tips.append(f"👖 Низ: {'джинсы или брюки' if current_feels < 18 else 'лёгкие брюки или шорты'}")
    if any(s['pop'] >= 0.4 for s in wet_rest):
        tips.append("👟 Обувь: непромокаемые кроссовки или ботинки")

    return tips


def format_current(data, city, forecast=None):
    temp = data['main']['temp']
    feels = data['main']['feels_like']
    desc = data['weather'][0]['description'].capitalize()
    humidity = data['main']['humidity']
    pressure = data['main']['pressure']
    wind = data['wind']['speed']
    icon = data['weather'][0]['icon']
    code = data['weather'][0]['id']
    night_icon = icon.endswith('n')

    summary = collect_day(forecast) if forecast else None

    out = [
        f"🌍 <b>{_esc(city)}</b>",
        f"{_icon(code)} <b>{_esc(desc)}</b>",
        "",
        f"🌡 <b>Сейчас: {_fmt(temp)}°C</b>  ·  ощущается как {_fmt(feels)}°C",
        f"💧 Влажность: {humidity}%   💨 Ветер: {_fmt(wind)} м/с   📊 Давление: {pressure} гПа",
    ]

    pressure_line = "📈 <b>Давление.</b> " + " ".join(outlook_pressure(pressure, summary))
    meteo = f" <i>({_esc(meteo_note(pressure, summary))})</i>"

    if summary:
        out += ["", f"🕐 <b>Остаток дня</b> — сейчас {_esc(_part_of_day(summary['now'].hour))}"]
        table = _day_table(summary)
        out += table if table else ["   данных на сегодня нет"]

        out += ["", "🔮 <b>Что ожидается</b>"]
        out.append("🌡 <b>Температура.</b> " + " ".join(outlook_temperature(summary, temp, feels)))
        out.append("🌧 <b>Осадки.</b> " + " ".join(outlook_rain(summary)))
        out.append(pressure_line + meteo)
    else:
        # давление известно из текущей погоды даже без прогноза на день
        out += ["", "ℹ️ Расширенный прогноз на сегодня временно недоступен.",
                pressure_line + meteo]

    out += ["", "👕 <b>Что надеть</b>"]
    out += [f"   {tip}" for tip in advice_clothes(feels, temp, wind, humidity, summary)]

    well = wellbeing(feels, wind, summary, pressure)
    if well:
        out += ["", well]

    return "\n".join(out)

WEEKDAYS_RU = {'Monday': 'пн', 'Tuesday': 'вт', 'Wednesday': 'ср',
               'Thursday': 'чт', 'Friday': 'пт', 'Saturday': 'сб', 'Sunday': 'вс'}


def _dominant_weather(slots):
    """Самая частая погода за сутки: описание, доля от общего времени, типичная иконка."""
    counts = Counter(s['desc'] for s in slots)
    (desc, times), = counts.most_common(1)
    share = times / len(slots)
    icon = Counter(s['code'] for s in slots).most_common(1)[0][0]
    return desc, share, icon


def format_tomorrow(city, forecast):
    """Предположительная погода на завтра. None, если прогноза нет."""
    summary = collect_day(forecast, day_offset=1)
    if not summary or not summary['rest']:
        return None

    slots = summary['rest']
    night = [s for s in slots if s['dt'].hour < 6 or s['dt'].hour >= 21]
    daytime = [s for s in slots if 6 <= s['dt'].hour < 21]
    ref = daytime or slots

    date = slots[0]['dt']
    temps = [s['temp'] for s in slots]

    out = [
        f"🌙 <b>Завтра</b>, {WEEKDAYS_RU.get(date.strftime('%A'), '')} {date.strftime('%d.%m')}"
        f"   <b>{_esc(city)}</b>",
        f"   {_sparkline(temps)}  {_fmt(summary['temp_min'])} → {_fmt(summary['temp_max'])}°C",
        "",
    ]

    # температура: отдельно ночь и день (диапазоны — только по своим слотам,
    # иначе минимум суток совпадает в обеих строках)
    def _range(slots_):
        return _fmt(min(s['temp'] for s in slots_)), _fmt(max(s['temp'] for s in slots_))

    if night and daytime:
        n_lo, n_hi = _range(night)
        d_lo, d_hi = _range(daytime)
        out.append(f"🌡 Ночью {n_lo}…{n_hi}°C, днём {d_lo}…{d_hi}°C")
    else:
        out.append(f"🌡 {_fmt(summary['temp_min'])}…{_fmt(summary['temp_max'])}°C")

    feels_lo = summary['feels_min']
    feels_hi = summary['feels_max']
    if feels_lo is not None:
        out.append(f"   Ощущается как {_fmt(feels_lo)}…{_fmt(feels_hi)}°C")

    # преобладающая погода
    desc, share, code = _dominant_weather(slots)
    icon = _icon(code)
    if share >= 0.6:
        out.append(f"{icon} Преобладает: {_esc(desc.lower())}")
    elif share >= 0.35:
        out.append(f"{icon} {_esc(desc.capitalize())}, но погода переменчивая")
    else:
        out.append(f"{icon} Погода переменчивая, {_esc(desc.lower())} — не весь день")

    # осадки
    windows = _rain_windows(slots)
    if windows:
        kinds = {int(w['code']) // 100 for w in windows}
        kind = "снег" if 6 in kinds else "ливень" if 2 in kinds or 3 in kinds else "дождь"
        total = sum(w['mm'] for w in windows)
        top = max(w['pop'] for w in windows)
        first, last = windows[0], windows[-1]
        timing = (f"{_hh(first['start'])}–{_hh(last['end'])}" if len(windows) == 1
                  else f"{len(windows)} окна с {_hh(first['start'])} до {_hh(last['end'])}")
        line = f"🌧 {_kind_cap(kind)}: {timing}, до {int(top * 100)}%"
        if total >= 0.3:
            line += f", ~{_fmt(total)} мм"
        out.append(line)
    else:
        out.append("🌧 Осадков не ожидается")

    # ветер и давление
    wind_max = max(s['wind'] for s in slots)
    p_min = min(s['pressure'] for s in slots)
    p_max = max(s['pressure'] for s in slots)
    wind_word = "сильный" if wind_max >= 10 else "умеренный" if wind_max >= 5 else "слабый"
    out.append(f"💨 Ветер до {_fmt(wind_max)} м/с ({wind_word})")
    p_delta = slots[-1]['pressure'] - slots[0]['pressure']
    if p_delta <= -3:
        p_trend = "падает"
    elif p_delta >= 3:
        p_trend = "растёт"
    else:
        p_trend = "без изменений"
    p_range = f"{p_min}" if p_min == p_max else f"{p_min}–{p_max}"
    out.append(f"📊 Давление {p_range} гПа ({p_trend})")

    # короткая рекомендация по одежде — только самое важное, без строки про низ
    tips = advice_clothes(ref[len(ref) // 2]['feels'], ref[len(ref) // 2]['temp'],
                          wind_max, ref[len(ref) // 2]['humidity'], summary)
    core = [t for t in tips if "Основа" in t]
    extra = [t for t in tips if t not in core and "Низ" not in t][:2]
    out += ["", "👕 <b>На завтра</b>"] + [f"   {t}" for t in (core + extra)]

    return "\n".join(out)


def _kind_cap(kind):
    return {"дождь": "Дождь", "снег": "Снег", "ливень": "Ливень"}.get(kind, "Осадки")


def format_forecast(data, city):
    days = {}
    for item in data['list']:
        date = item['dt_txt'][:10]
        if date not in days:
            days[date] = []
        days[date].append(item)

    text = f"📅 <b>Прогноз на 5 дней — {city}</b>\n\n"
    days_ru = {'Monday':'Пн','Tuesday':'Вт','Wednesday':'Ср',
               'Thursday':'Чт','Friday':'Пт','Saturday':'Сб','Sunday':'Вс'}

    for date, items in list(days.items())[:5]:
        day_name = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
        day_ru = days_ru.get(day_name, day_name)
        temps = [i['main']['temp'] for i in items]
        min_t, max_t = min(temps), max(temps)
        desc = items[4]['weather'][0]['description'].capitalize() if len(items) > 4 else items[0]['weather'][0]['description'].capitalize()
        text += f"📆 <b>{day_ru}</b> ({date[-2:]}.{date[5:7]}): {min_t:.0f}°…{max_t:.0f}°C, {desc}\n"
    return text

# ==================== КЛАВИАТУРЫ ====================
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🌤 Погода сейчас"), KeyboardButton("🌙 Завтра")],
        [KeyboardButton("📅 На 5 дней"), KeyboardButton("📍 Указать город")],
        [KeyboardButton("⏰ Время рассылки"), KeyboardButton("⚙️ Настройки")],
        [KeyboardButton("❌ Отписаться"), KeyboardButton("ℹ️ Помощь")]
    ], resize_keyboard=True)

def settings_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🌡 °C / °F"), KeyboardButton("🌐 Язык")],
        [KeyboardButton("⬅️ Назад")]
    ], resize_keyboard=True)

# ==================== ОБРАБОТЧИКИ ====================
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    add_user(user.id, user.username)
    logger.info(f"Новый пользователь: {user.id} (@{user.username})")
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\nЯ бот прогноза погоды. Выбери действие:",
        reply_markup=main_menu()
    )

async def handle_text(update: Update, context: CallbackContext):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🌤 Погода сейчас":
        await cmd_now(update, context)
    elif text == "🌙 Завтра":
        await cmd_tomorrow(update, context)
    elif text == "📅 На 5 дней":
        await cmd_forecast(update, context)
    elif text == "📍 Указать город":
        await update.message.reply_text("Введи название города:")
        return SET_CITY
    elif text == "⏰ Время рассылки":
        await update.message.reply_text("Введи время ЧЧ:ММ (например, 08:00):")
        return SET_TIME
    elif text == "⚙️ Настройки":
        await update.message.reply_text("Настройки:", reply_markup=settings_menu())
    elif text == "⬅️ Назад":
        await update.message.reply_text("Главное меню:", reply_markup=main_menu())
    elif text == "❌ Отписаться":
        await cmd_unsubscribe(update, context)
    elif text == "ℹ️ Помощь":
        await cmd_help(update, context)
    elif text == "🌡 °C / °F":
        await update.message.reply_text("⚙️ В разработке 😊", reply_markup=settings_menu())
    elif text == "🌐 Язык":
        await update.message.reply_text("Пока доступен только русский 🇷🇺", reply_markup=settings_menu())
    else:
        city, lat, lon = get_coordinates(text)
        if city:
            update_city(user_id, city, lat, lon)
            await update.message.reply_text(
                f"✅ Город установлен: <b>{city}</b>",
                reply_markup=main_menu(), parse_mode='HTML'
            )
        else:
            await update.message.reply_text("❌ Город не найден. Попробуй еще раз.")
    return ConversationHandler.END

async def set_city_handler(update: Update, context: CallbackContext):
    city_name = update.message.text
    user_id = update.effective_user.id
    city, lat, lon = get_coordinates(city_name)
    if city:
        update_city(user_id, city, lat, lon)
        await update.message.reply_text(f"✅ Город сохранен: <b>{city}</b>", reply_markup=main_menu(), parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Город не найден.", reply_markup=main_menu())
    return ConversationHandler.END

async def set_time_handler(update: Update, context: CallbackContext):
    time_str = update.message.text.strip()
    user_id = update.effective_user.id
    try:
        datetime.strptime(time_str, "%H:%M")
        update_time(user_id, time_str)
        await update.message.reply_text(f"✅ Рассылка на <b>{time_str}</b>", reply_markup=main_menu(), parse_mode='HTML')
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Введи ЧЧ:ММ")
        return SET_TIME
    return ConversationHandler.END

async def cmd_now(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    row = get_user(user_id)
    if not row or not row[3]:
        await update.message.reply_text("❌ Сначала укажи город через 📍 Указать город", reply_markup=main_menu())
        return
    city, lat, lon = row[2], row[3], row[4]
    data = get_current_weather(lat, lon)
    if data.get('cod') != 200:
        await update.message.reply_text("⚠️ Ошибка получения погоды.")
        return
    forecast = get_forecast_safe(lat, lon)
    await update.message.reply_text(format_current(data, city, forecast), parse_mode='HTML')

async def cmd_tomorrow(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    row = get_user(user_id)
    if not row or not row[3]:
        await update.message.reply_text("❌ Сначала укажи город через 📍 Указать город", reply_markup=main_menu())
        return
    city, lat, lon = row[2], row[3], row[4]
    forecast = get_forecast_safe(lat, lon)
    text = format_tomorrow(city, forecast) if forecast else None
    if not text:
        await update.message.reply_text("⚠️ Не удалось получить прогноз на завтра.")
        return
    await update.message.reply_text(text, parse_mode='HTML')


async def cmd_forecast(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    row = get_user(user_id)
    if not row or not row[3]:
        await update.message.reply_text("❌ Сначала укажи город через 📍 Указать город", reply_markup=main_menu())
        return
    city, lat, lon = row[2], row[3], row[4]
    data = get_forecast_5days(lat, lon)
    if data.get('cod') not in (200, '200'):
        await update.message.reply_text("⚠️ Ошибка получения прогноза.")
        return
    await update.message.reply_text(format_forecast(data, city), parse_mode='HTML')

async def cmd_unsubscribe(update: Update, context: CallbackContext):
    toggle_subscription(update.effective_user.id, 0)
    await update.message.reply_text(
        "😢 Ты отписан. Чтобы вернуться, нажми /start",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
    )

async def cmd_help(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📖 <b>Справка:</b>\n\n"
        "• 📍 <b>Указать город</b> — введи название\n"
        "• 🌤 <b>Погода сейчас</b> — текущая погода, прогноз на день и рекомендации по одежде\n"
        "• 🌙 <b>Завтра</b> — предположительная погода на следующие сутки\n"
        "• 📅 <b>На 5 дней</b> — прогноз\n"
        "• ⏰ <b>Время рассылки</b> — ежедневная отправка (ЧЧ:ММ)\n"
        "• ❌ <b>Отписаться</b> — отключить уведомления\n\n"
        "💡 Можно просто написать название города — бот поймет!",
        parse_mode='HTML'
    )

# ==================== РАССЫЛКА ====================
async def send_daily_forecast(application):
    import pytz
    tz = pytz.timezone(os.getenv("TIMEZONE", "Europe/Moscow"))
    now = datetime.now(tz).strftime("%H:%M")
    users = get_all_subscribed_users()
    logger.info(f"[Рассылка] Время в TZ: {now}, подписчиков с временем: {len(users)}")
    
    for user_id, city, lat, lon, notify_time in users:
        logger.info(f"[Рассылка] user={user_id}, city={city}, notify={notify_time}, now={now}, match={notify_time == now}")
        if notify_time == now:
            try:
                data = get_current_weather(lat, lon)
                if data.get('cod') == 200:
                    forecast = get_forecast_safe(lat, lon)
                    text = format_current(data, city, forecast)
                    tomorrow = format_tomorrow(city, forecast) if forecast else None
                    if tomorrow:
                        text += "\n\n" + tomorrow
                    await application.bot.send_message(
                        chat_id=user_id, text=text, parse_mode='HTML')
                    logger.info(f"[Рассылка] Успешно отправлено: {user_id}")
                else:
                    logger.error(f"[Рассылка] API ошибка для {user_id}: {data}")
            except Exception as e:
                logger.error(f"[Рассылка] Ошибка отправки {user_id}: {e}")

def signal_handler(sig, frame):
    logger.info("Получен сигнал завершения, останавливаюсь...")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# ==================== MAIN ====================
def main():
    logger.info("Запуск бота...")
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)],
        states={
            SET_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_city_handler)],
            SET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_time_handler)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("tomorrow", cmd_tomorrow))
    application.add_handler(conv_handler)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_forecast, 'cron', minute='*', args=[application])
    scheduler.start()

    logger.info("Бот успешно запущен и ожидает сообщения")
    application.run_polling()

if __name__ == "__main__":
    main()
