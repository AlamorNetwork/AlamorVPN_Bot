# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# اگر دیتابیس پستگرس باشد آدرس آن، اگر نباشد SQLite ساخته می‌شود
DB_URI = os.getenv("DATABASE_URL", "sqlite:///./vpn_bot.db")

XUI_PANEL_URL = os.getenv("XUI_PANEL_URL")
XUI_USERNAME = os.getenv("XUI_USERNAME")
XUI_PASSWORD = os.getenv("XUI_PASSWORD")

# بررسی مقداردهی (اختیاری ولی مفید)
if not XUI_PANEL_URL or not XUI_USERNAME or not XUI_PASSWORD:
    print("WARNING: X-UI credentials are missing in .env file!")