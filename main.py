# main.py
import telebot
import time
from config import BOT_TOKEN
from database.base import init_db
from handlers import admin

# ساخت دیتابیس (اگر وجود نداشته باشد)
print("--- Initializing Database ---")
init_db()
print("✅ Database initialized.")

# راه‌اندازی ربات
bot = telebot.TeleBot(BOT_TOKEN)

# ثبت هندلرها
admin.register_admin_handlers(bot)
# user.register_user_handlers(bot) # بعداً اضافه می‌شود

print("🤖 Bot is running...")
try:
    bot.infinity_polling()
except Exception as e:
    print(f"❌ Error: {e}")
    time.sleep(5)