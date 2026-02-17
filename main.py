# main.py
import telebot
import time
from config import BOT_TOKEN
from database.base import init_db
from handlers import admin, user

print("--- Initializing Database ---")
init_db()
print("✅ Database initialized.")

bot = telebot.TeleBot(BOT_TOKEN)

# ⚠️ این خط بسیار مهم است: حذف وب‌هوک‌های قدیمی
print("🔄 Clearing previous webhooks...")
try:
    bot.delete_webhook()
    print("✅ Webhook cleared.")
except Exception as e:
    print(f"⚠️ Warning deleting webhook: {e}")

# ثبت هندلرها
admin.register_admin_handlers(bot)
user.register_user_handlers(bot)

print("🤖 Bot is running...")
try:
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
except Exception as e:
    print(f"❌ Error: {e}")
    time.sleep(5)