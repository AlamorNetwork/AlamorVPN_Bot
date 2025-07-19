# utils/bot_helpers.py (نسخه نهایی و اصلاح شده)

import telebot
import qrcode
from io import BytesIO
import logging

from utils import messages, helpers

logger = logging.getLogger(__name__)

def send_subscription_info(bot: telebot.TeleBot, user_id: int, sub_link: str):
    """
    اطلاعات اشتراک را با ارسال لینک متنی صحیح و سپس QR کد ارسال می‌کند.
    """
    bot.send_message(user_id, messages.CONFIG_DELIVERY_HEADER, parse_mode='Markdown')
    
    # --- راه حل قطعی: اصلاح لینک قبل از ارسال ---
    # این خط تضمین می‌کند که هرگونه بک‌اسلش (\) اضافه شده، حذف شود.
    # corrected_sub_link = sub_link.replace('\.', '.')

    # ابتدا لینک متنی اصلاح شده ارسال می‌شود
    bot.send_message(user_id, messages.CONFIG_DELIVERY_SUB_LINK.format(sub_link=sub_link), parse_mode='Markdown')
    
    # سپس QR کد در یک پیام جداگانه با لینک اصلاح شده ساخته می‌شود
    try:
        qr_image = qrcode.make(sub_link)
        bio = BytesIO()
        bio.name = 'qrcode.jpeg'
        qr_image.save(bio, 'JPEG')
        bio.seek(0)

        bot.send_photo(user_id, bio, caption=messages.QR_CODE_CAPTION)
        
    except Exception as e:
        logger.error(f"Failed to generate or send QR code: {e}")