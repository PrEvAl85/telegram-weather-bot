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

import os
import sys

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
DB_PATH = os.getenv("DB_PATH", "data/weather_bot.db")
LOG_PATH = os.getenv("LOG_PATH", "logs/bot.log")
ADMIN_ID = os.getenv("ADMIN_ID")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

if not BOT_TOKEN or not WEATHER_API_KEY:
    print("Error: BOT_TOKEN or WEATHER_API_KEY is not set in .env")
    print("Copy .env.example to .env and fill in the values.")
    sys.exit(1)