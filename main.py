# main.py

import telebot
import logging
import os

from config import BOT_TOKEN, ADMIN_IDS, REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_LINK
from database.db_manager import DatabaseManager
from api_client.xui_api_client import XuiAPIClient
from handlers import admin_handlers, user_handlers
from utils import messages, helpers
from keyboards import inline_keyboards

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Instantiation ---
if not BOT_TOKEN:
    logger.critical("BOT_TOKEN is not set. Exiting.")
    exit()

bot = telebot.TeleBot(BOT_TOKEN)
db_manager = DatabaseManager()

# --- MODIFIED: /start command handler ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    logger.info(f"Received /start from user ID: {user_id} ({first_name})")

    # --- Channel Lock Logic (remains the same) ---
    required_channel_id_str = db_manager.get_setting('required_channel_id')
    if required_channel_id_str:
        try:
            required_channel_id = int(required_channel_id_str)
            if not helpers.is_admin(user_id) and not helpers.is_user_member_of_channel(bot, required_channel_id, user_id):
                channel_link = db_manager.get_setting('required_channel_link') or "https://t.me/Alamor_Network"
                markup = inline_keyboards.get_join_channel_keyboard(channel_link)
                bot.send_message(user_id, messages.REQUIRED_CHANNEL_PROMPT, reply_markup=markup)
                return
        except (ValueError, TypeError):
            logger.error(f"Invalid required_channel_id in database: {required_channel_id_str}")

    db_manager.add_or_update_user(
        telegram_id=user_id,
        first_name=first_name,
        last_name=message.from_user.last_name,
        username=message.from_user.username
    )

    # --- THE FIX IS HERE ---
    # We now fetch the support link from the database before creating the user menu.
    support_link = db_manager.get_setting('support_link')
    
    if helpers.is_admin(user_id):
        bot.send_message(user_id, messages.ADMIN_WELCOME, reply_markup=inline_keyboards.get_admin_main_inline_menu())
    else:
        welcome_text = messages.START_WELCOME.format(first_name=helpers.escape_markdown_v1(first_name))
        # And we pass the fetched link to the keyboard function.
        user_menu_markup = inline_keyboards.get_user_main_inline_menu(support_link)
        bot.send_message(user_id, welcome_text, parse_mode='Markdown', reply_markup=user_menu_markup)
@bot.message_handler(commands=['myid'])
def send_user_id(message):
    user_id = message.from_user.id
    bot.reply_to(message, f"Your numeric ID is:\n`{user_id}`", parse_mode='Markdown')

def main():
    bot.remove_webhook()
    logger.info("Bot is starting...")

    try:
        db_manager.create_tables()
        logger.info("Database tables checked/created successfully.")
    except Exception as e:
        logger.critical(f"FATAL: Could not create database tables. Error: {e}")
        return

    admin_handlers.register_admin_handlers(bot, db_manager, XuiAPIClient)
    logger.info("Admin handlers registered.")

    user_handlers.register_user_handlers(bot, db_manager, XuiAPIClient)
    logger.info("User handlers registered.")

    logger.info("Bot is now polling for updates...")
    bot.infinity_polling(logger_level=logging.WARNING)
    logger.info("Bot polling stopped.")

if __name__ == "__main__":
    main()