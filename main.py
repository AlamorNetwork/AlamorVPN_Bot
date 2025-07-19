# main.py

import telebot
import logging
import os

# --- تنظیمات لاگ (تغییر در این بخش) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # انکودینگ UTF-8 برای فایل لاگ مشخص شده است
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- ایمپورت ماژول‌های پروژه ---
from config import BOT_TOKEN, ADMIN_IDS, REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_LINK
from database.db_manager import DatabaseManager
from api_client.xui_api_client import XuiAPIClient
from handlers import admin_handlers, user_handlers
from utils import messages, helpers
from keyboards import inline_keyboards

# --- نمونه‌سازی (Instantiation) ---
if not BOT_TOKEN:
    logger.critical("BOT_TOKEN is not set in the environment variables. Exiting.")
    exit()

bot = telebot.TeleBot(BOT_TOKEN)
db_manager = DatabaseManager()
# نمونه‌سازی XuiAPIClient اینجا لازم نیست چون در هر فانکشن به صورت موقت ساخته می‌شود

# --- هندلر دستور /start ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    logger.info(f"Received /start from user ID: {user_id} ({first_name})")

    # ذخیره/به‌روزرسانی کاربر در دیتابیس
    db_manager.add_or_update_user(
        telegram_id=user_id,
        first_name=first_name,
        last_name=message.from_user.last_name,
        username=message.from_user.username
    )

    # بررسی عضویت در کانال
    if REQUIRED_CHANNEL_ID and not helpers.is_user_member_of_channel(bot, REQUIRED_CHANNEL_ID, user_id):
        bot.send_message(user_id, messages.REQUIRED_CHANNEL_PROMPT.format(channel_link=REQUIRED_CHANNEL_LINK))
        logger.info(f"User {user_id} is not a member of the required channel.")
        return

    # نمایش منوی مناسب
    if helpers.is_admin(user_id):
        bot.send_message(user_id, messages.ADMIN_WELCOME, reply_markup=inline_keyboards.get_admin_main_inline_menu())
    else:
        welcome_text = messages.START_WELCOME.format(first_name=helpers.escape_markdown_v1(first_name))
        bot.send_message(user_id, welcome_text, parse_mode='Markdown', reply_markup=inline_keyboards.get_user_main_inline_menu())

# --- تابع اصلی ---
def main():
    bot.remove_webhook()
    logger.info("Bot is starting...")

    # ایجاد جداول دیتابیس در صورت عدم وجود
    try:
        db_manager.create_tables()
        logger.info("Database tables checked/created successfully.")
    except Exception as e:
        logger.critical(f"FATAL: Could not create database tables. Error: {e}")
        return # خروج از برنامه اگر دیتابیس مشکل داشته باشد

    # ثبت هندلرها
    # XUI API Client به صورت موقت در هر تابع ساخته می‌شود، پس لازم نیست اینجا پاس داده شود
    admin_handlers.register_admin_handlers(bot, db_manager, XuiAPIClient)
    logger.info("Admin handlers registered.")

    user_handlers.register_user_handlers(bot, db_manager, XuiAPIClient)
    logger.info("User handlers registered.")

    logger.info("Bot is now polling for updates...")
    bot.infinity_polling(logger_level=logging.WARNING) # برای جلوگیری از لاگ‌های زیاد خود کتابخانه
    logger.info("Bot polling stopped.")

@bot.message_handler(commands=['myid'])
def send_user_id(message):
    user_id = message.from_user.id
    bot.reply_to(message, f"آیدی عددی شما:\n`{user_id}`", parse_mode='Markdown')


if __name__ == "__main__":
    main()
