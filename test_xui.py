# test_full_features.py
import uuid
import time
import random
from services.xui import XUIClient
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD

def run_full_test():
    print("🚀 شروع تست جامع قابلیت‌های API پنل ثنایی...\n")
    
    # 1. تست اتصال
    client = XUIClient(XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD)
    if client.login():
        print("✅ [1/7] اتصال و لاگین موفقیت‌آمیز بود.")
    else:
        print("❌ [1/7] خطا در اتصال! اطلاعات را چک کنید.")
        return

    # 2. تست ساخت اینباند (یک پورت رندوم برای جلوگیری از تداخل)
    test_port = random.randint(11000, 12000)
    inbound_remark = f"Bot_Test_{test_port}"
    print(f"\n⏳ [2/7] در حال ساخت اینباند تستی (Port: {test_port})...")
    
    # تنظیمات ساده VLESS برای تست
    settings = {"clients": [], "decryption": "none", "fallbacks": []}
    stream_settings = {"network": "tcp", "security": "none", "tcpSettings": {}}
    
    if client.add_inbound(inbound_remark, test_port, "vless", settings, stream_settings):
        print(f"✅ اینباند '{inbound_remark}' ساخته شد.")
    else:
        print("❌ خطا در ساخت اینباند.")
        return

    # پیدا کردن ID اینباند جدید
    inbounds = client.get_inbounds()
    target_inbound = next((i for i in inbounds if i['port'] == test_port), None)
    if not target_inbound:
        print("❌ اینباند ساخته شده در لیست پیدا نشد!")
        return
    inbound_id = target_inbound['id']
    print(f"   🆔 شناسه اینباند جدید: {inbound_id}")

    # 3. تست افزودن کلاینت
    test_email = f"user_{random.randint(1000,9999)}"
    test_uuid = str(uuid.uuid4())
    print(f"\n⏳ [3/7] افزودن کلاینت تستی (Email: {test_email})...")
    
    if client.add_client(inbound_id, test_email, test_uuid, total_gb=10, enable=True): # 10 GB
        print("✅ کلاینت با موفقیت اضافه شد.")
    else:
        print("❌ خطا در افزودن کلاینت.")
    
    # 4. تست دریافت ترافیک کلاینت
    print("\n⏳ [4/7] دریافت اطلاعات ترافیک کلاینت...")
    traffic = client.get_client_traffic(test_uuid)
    if traffic:
        print(f"✅ اطلاعات ترافیک دریافت شد: {traffic}")
    else:
        print("⚠️ ترافیک دریافت نشد (ممکن است در لحظه اول خالی باشد).")

    # 5. تست آپدیت کلاینت (مثلاً غیرفعال کردن)
    print("\n⏳ [5/7] تست غیرفعال کردن کلاینت...")
    # برای آپدیت، باید کل آبجکت کلاینت با تغییرات ارسال شود
    # اینجا فقط بخش‌های مهم را می‌فرستیم
    new_settings = {
        "id": test_uuid,
        "email": test_email,
        "enable": False, # غیرفعال کردن
        "totalGB": 0,
        "expiryTime": 0
    }
    if client.update_client(test_uuid, new_settings):
        print("✅ کلاینت با موفقیت غیرفعال شد (Update API کار می‌کند).")
    else:
        print("❌ خطا در آپدیت کلاینت.")

    # 6. تست حذف کلاینت
    print("\n⏳ [6/7] حذف کلاینت تستی...")
    if client.delete_client(inbound_id, test_uuid):
        print("✅ کلاینت حذف شد.")
    else:
        print("❌ خطا در حذف کلاینت.")

    # 7. تست حذف اینباند
    print(f"\n⏳ [7/7] پاکسازی و حذف اینباند تستی {inbound_id}...")
    if client.delete_inbound(inbound_id):
        print("✅ اینباند تستی حذف شد. محیط تمیز شد.")
    else:
        print("❌ خطا در حذف اینباند! لطفاً دستی پاک کنید.")

    print("\n🎉 تست تمام قابلیت‌ها با موفقیت به پایان رسید.")

if __name__ == "__main__":
    run_full_test()