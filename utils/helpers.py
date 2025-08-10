# utils/helpers.py (نسخه کامل و اصلاح شده)

import telebot
import logging
import random
import string
import re
# --- ایمپورت‌های جدید در اینجا اضافه شده‌اند ---
from urllib.parse import urlparse, parse_qs
from database.db_manager import DatabaseManager
import utils.messages as messages_module
from config import ADMIN_IDS

logger = logging.getLogger(__name__)
_db_for_messages = DatabaseManager()


# --- تابع جدید در اینجا اضافه شده است ---
def parse_config_link(link: str) -> dict or None:
    """
    یک لینک کانفیگ vless را تجزیه کرده و به صورت یک دیکشنری ساختاریافته برمی‌گرداند.
    """
    try:
        if not link.startswith("vless://"):
            return None

        parsed_url = urlparse(link)
        
        # استخراج پارامترهای اصلی
        params = {
            "protocol": parsed_url.scheme,
            "uuid": parsed_url.username,
            "hostname": parsed_url.hostname,
            "port": parsed_url.port,
            "remark": parsed_url.fragment
        }
        
        # استخراج تمام پارامترهای کوئری
        query_params = parse_qs(parsed_url.query)
        for key, value in query_params.items():
            # parse_qs مقادیر را به صورت لیست برمی‌گرداند، ما اولین مقدار را می‌خواهیم
            params[key] = value[0]
            
        return params
    except Exception as e:
        logger.error(f"Failed to parse config link '{link}': {e}")
        return None


def is_admin(user_id: int) -> bool:
    """بررسی می‌کند که آیا کاربر ادمین است یا خیر."""
    return user_id in ADMIN_IDS


def is_user_member_of_channel(bot: telebot.TeleBot, channel_id: int, user_id: int) -> bool:
    """
    بررسی می‌کند که آیا کاربر در کانال مورد نظر عضو است یا خیر.
    """
    if channel_id is None:
        return True

    try:
        chat_member = bot.get_chat_member(channel_id, user_id)
        return chat_member.status in ['member', 'creator', 'administrator']
    except Exception as e:
        logger.error(f"Error checking user {user_id} membership in channel {channel_id}: {e}")
        return True


def is_float_or_int(value) -> bool:
    """
    بررسی می‌کند که آیا یک رشته می‌تواند به float یا int تبدیل شود یا خیر.
    """
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def escape_markdown_v1(text: str) -> str:
    """
    کاراکترهای خاص Markdown V1 را برای جلوگیری از خطا در پارس کردن، Escape می‌کند.
    """
    escape_chars = r'_*`[]()~>#+-=|{}!.'

    if not isinstance(text, str):
        text = str(text)

    return text.translate(str.maketrans({c: f'\\{c}' for c in escape_chars}))


def generate_random_string(length=10) -> str:
    """
    یک رشته تصادفی از حروف کوچک و اعداد به طول مشخص تولید می‌کند.
    """
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for i in range(length))


def normalize_panel_inbounds(panel_type, raw_inbounds):
    """
    اطلاعات خام اینباندها از پنل‌های مختلف را گرفته و به یک فرمت استاندارد و یکسان تبدیل می‌کند.
    """
    if not raw_inbounds:
        return []

    normalized_list = []
    
    if panel_type in ['x-ui', 'alireza']:
        for inbound in raw_inbounds:
            normalized_list.append({
                'id': inbound.get('id'),
                'remark': inbound.get('remark', ''),
                'port': inbound.get('port'),
                'protocol': inbound.get('protocol'),
                'settings': inbound.get('settings', '{}'),
                'streamSettings': inbound.get('streamSettings', '{}'),
            })

    return normalized_list


def update_env_file(key_to_update, new_value):
    """یک متغیر خاص را در فایل .env آپدیت یا اضافه می‌کند."""
    env_path = '.env'
    try:
        with open(env_path, 'r') as file:
            lines = file.readlines()

        key_found = False
        with open(env_path, 'w') as file:
            for line in lines:
                if line.strip().startswith(key_to_update + '='):
                    file.write(f'{key_to_update}="{new_value}"\n')
                    key_found = True
                else:
                    file.write(line)
            
            if not key_found:
                file.write(f'\n{key_to_update}="{new_value}"\n')
        return True
    except Exception as e:
        logger.error(f"Failed to update .env file: {e}")
        return False
    
    
def get_message(key: str, **kwargs):
    """
    پیام را از دیتابیس می‌خواند و در صورت نبود، از فایل messages.py استفاده می‌کند.
    """
    message_text = _db_for_messages.get_message_by_key(key)
    
    # اگر پیام در دیتابیس نبود (مثلاً در حین توسعه اضافه شده)، از فایل پیش‌فرض بخوان
    if message_text is None:
        message_text = getattr(messages_module, key, f"Message_Key_Not_Found: {key}")
            
    # فرمت کردن پیام با متغیرها (در صورت وجود)
    try:
        return message_text.format(**kwargs)
    except KeyError:
        # اگر متغیرهای فرمت مطابقت نداشتند، متن خام را برگردان
        return message_text