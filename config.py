# config.py (نسخه نهایی با عیب‌یابی پیشرفته)

import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

# =============================================================================
# SECTION: عیب‌یابی پیشرفته فایل .env
# =============================================================================
print("\n--- شروع عیب‌یابی فایل .env ---")
env_path = Path(__file__).parent.resolve() / '.env'
print(f"1. مسیر مطلق مورد انتظار برای فایل .env:\n   {env_path}")

# --- بررسی مرحله ۱: آیا فایل وجود دارد؟ ---
if not env_path.exists():
    print("\n2. ❌ نتیجه: ناموفق!")
    print("   علت: فایل .env در مسیر بالا وجود ندارد.")
    print("   راه‌حل: مطمئن شوید فایلی با نام دقیقاً '.env' (با نقطه در ابتدا) در پوشه اصلی پروژه قرار دارد.")
    sys.exit(1) # خروج از برنامه
print("2. ✅ نتیجه: فایل .env پیدا شد.")

# --- بررسی مرحله ۲: آیا یک فایل است (و نه پوشه)؟ ---
if not env_path.is_file():
    print("\n3. ❌ نتیجه: ناموفق!")
    print("   علت: مسیر پیدا شده یک فایل نیست، بلکه یک پوشه است.")
    sys.exit(1) # خروج از برنامه
print("3. ✅ نتیجه: مسیر یافت شده یک فایل است.")

# --- بررسی مرحله ۳: آیا فایل قابل خواندن و دارای محتوا است؟ ---
try:
    content = env_path.read_text(encoding='utf-8')
    if not content.strip():
        print("\n4. ❌ نتیجه: ناموفق!")
        print("   علت: فایل .env خالی است.")
        sys.exit(1) # خروج از برنامه
    print("4. ✅ نتیجه: فایل .env قابل خواندن و دارای محتوا است.")
    print("\n--- محتوای خوانده شده از فایل .env ---")
    print(content)
    print("--------------------------------------\n")
except Exception as e:
    print(f"\n4. ❌ نتیجه: ناموفق!")
    print(f"   علت: هنگام خواندن فایل خطایی رخ داد: {e}")
    print("   راه‌حل: دسترسی‌های فایل (Permissions) را بررسی کنید. همچنین مطمئن شوید فایل با انکودینگ UTF-8 ذخیره شده است.")
    sys.exit(1) # خروج از برنامه

# =============================================================================
# SECTION: بارگذاری و پردازش متغیرها
# =============================================================================
# حالا که از وجود فایل مطمئن هستیم، آن را بارگذاری می‌کنیم
load_dotenv(dotenv_path=env_path, override=True)


print("✅ متغیرها از فایل .env بارگذاری شدند. در حال پردازش...")

# تنظیمات ربات تلگرام
BOT_TOKEN = os.getenv("BOT_TOKEN_ALAMOR")

# کد هوشمند و مقاوم برای خواندن آیدی ادمین‌ها
admin_ids_str = os.getenv("ADMIN_IDS_ALAMOR", "")
try:
    ADMIN_IDS = [int(s) for s in re.findall(r'\d+', admin_ids_str)]
except:
    ADMIN_IDS = []

# تنظیمات دیتابیس
DATABASE_NAME = os.getenv("DATABASE_NAME_ALAMOR", "database/alamor_vpn.db")

# تنظیمات رمزنگاری
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY_ALAMOR")

# بررسی وجود متغیرهای حیاتی
if not BOT_TOKEN or not ADMIN_IDS or not ENCRYPTION_KEY:
    print("="*60)
    print("❌ خطای بحرانی: یک یا چند متغیر اصلی (BOT_TOKEN, ADMIN_IDS, ENCRYPTION_KEY) در فایل .env یافت نشد یا مقدار آن خالی است.")
    print("لطفاً محتوای فایل .env خود را که در بالا چاپ شد، بررسی کنید.")
    print("="*60)
    sys.exit(1)

print(f"✅ ادمین‌های شناسایی شده: {ADMIN_IDS}")

# --- تنظیمات اختیاری ---
SUPPORT_CHANNEL_LINK = os.getenv("SUPPORT_CHANNEL_LINK_ALAMOR", "https://t.me/YourSupportChannel")
REQUIRED_CHANNEL_ID_STR = os.getenv("REQUIRED_CHANNEL_ID_ALAMOR")
REQUIRED_CHANNEL_ID = int(REQUIRED_CHANNEL_ID_STR) if REQUIRED_CHANNEL_ID_STR and REQUIRED_CHANNEL_ID_STR.lstrip('-').isdigit() else None
REQUIRED_CHANNEL_LINK = os.getenv("REQUIRED_CHANNEL_LINK_ALAMOR", "https://t.me/YourChannelLink")
MAX_API_RETRIES = 3
# در فایل config.py
ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID")
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", "")



# در انتهای فایل config.py
ZARINPAL_SANDBOX = os.getenv("ZARINPAL_SANDBOX", "False").lower() in ['true', '1', 't']
ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID")