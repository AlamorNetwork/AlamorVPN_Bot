# handlers/payment_process.py
import telebot
from telebot import types
import uuid
from datetime import datetime, timedelta
from database.base import SessionLocal
from database.models import User, Plan, Payment, Purchase, Server
from services.xui import XUIClient
from config import ADMIN_IDS

# تنظیمات کارت (این‌ها را می‌توان بعداً از دیتابیس خواند)
CARD_NUMBER = "6037-9918-0000-0000"
CARD_HOLDER = "نام صاحب حساب"
RULES_TEXT = """
⚠️ **قوانین و مقررات خرید:**

1. ارسال فیش جعلی باعث مسدودی دائم می‌شود.
2. اسکرین‌شات باید واضح و حاوی شماره پیگیری باشد.
3. پس از واریز، سرویس شما پس از تایید ادمین (معمولاً زیر ۱۰ دقیقه) فعال می‌شود.
4. کانفیگ‌ها تک‌کاربره هستند.

✅ با پرداخت مبلغ، این قوانین را می‌پذیرم.
"""

def register_payment_handlers(bot: telebot.TeleBot):

    # ==========================
    # 1. سمت کاربر: نمایش اطلاعات پرداخت
    # ==========================
    def start_card_payment(message, plan_id):
        session = SessionLocal()
        plan = session.query(Plan).get(plan_id)
        session.close()
        
        if not plan:
            bot.send_message(message.chat.id, "خطا: پلن یافت نشد.")
            return

        text = (
            f"💳 **پرداخت کارت به کارت**\n\n"
            f"📦 سرویس: {plan.name}\n"
            f"💰 مبلغ قابل پرداخت: **{int(plan.price):,} تومان**\n\n"
            f"💳 شماره کارت:\n`{CARD_NUMBER}`\n"
            f"👤 به نام: {CARD_HOLDER}\n\n"
            f"{RULES_TEXT}\n"
            "📎 **لطفاً پس از واریز، عکس فیش یا اسکرین‌شات پرداخت را همینجا ارسال کنید.**"
        )
        
        # ذخیره وضعیت کاربر که منتظر فیش هستیم
        # (در اینجا ساده‌سازی کردیم، در پروژه واقعی از State Machine استفاده کنید)
        msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_receipt, bot, plan_id)

    def process_receipt(message, bot, plan_id):
        if message.content_type != 'photo':
            bot.send_message(message.chat.id, "❌ لطفاً فقط **عکس** فیش را ارسال کنید.")
            return

        # دریافت بزرگترین سایز عکس
        file_id = message.photo[-1].file_id
        
        session = SessionLocal()
        try:
            # ایجاد رکورد پرداخت در دیتابیس
            payment = Payment(
                user_id=session.query(User).filter_by(telegram_id=message.from_user.id).first().id,
                plan_id=plan_id,
                amount=0, # مبلغ را بعداً از پلن می‌خوانیم یا دستی
                status="pending",
                receipt_image_id=file_id,
                payment_method="card"
            )
            session.add(payment)
            session.commit()
            
            # ارسال پیام به کاربر
            bot.reply_to(message, "✅ فیش شما دریافت شد و در صف بررسی قرار گرفت.\nبه محض تایید، سرویس شما فعال و ارسال می‌شود.")
            
            # اطلاع‌رسانی به ادمین
            notify_admins(bot, payment.id)
            
        except Exception as e:
            bot.send_message(message.chat.id, f"خطا: {e}")
        finally:
            session.close()

    # ==========================
    # 2. سمت ادمین: بررسی و تایید
    # ==========================
    def notify_admins(bot, payment_id):
        session = SessionLocal()
        payment = session.query(Payment).get(payment_id)
        user = payment.user
        plan = payment.plan
        
        caption = (
            f"🔔 **تراکنش جدید (کارت به کارت)**\n\n"
            f"👤 کاربر: {user.first_name} (@{user.username})\n"
            f"📦 پلن: {plan.name}\n"
            f"💰 قیمت: {int(plan.price):,} تومان\n"
            f"📅 تاریخ: {datetime.now().strftime('%H:%M')}\n\n"
            "👇 عملیات مورد نظر را انتخاب کنید:"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تایید و تحویل", callback_data=f"pay_approve_{payment.id}"))
        markup.add(types.InlineKeyboardButton("❌ رد کردن", callback_data=f"pay_reject_{payment.id}"))
        
        for admin_id in ADMIN_IDS:
            try:
                bot.send_photo(admin_id, payment.receipt_image_id, caption=caption, reply_markup=markup, parse_mode="Markdown")
            except: pass
        
        session.close()

    # هندلر دکمه‌های تایید/رد ادمین
    @bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))
    def handle_payment_decision(call):
        if call.from_user.id not in ADMIN_IDS: return
        
        action, payment_id = call.data.split('_')[1], int(call.data.split('_')[2])
        session = SessionLocal()
        payment = session.query(Payment).get(payment_id)
        
        if not payment or payment.status != "pending":
            bot.answer_callback_query(call.id, "این تراکنش قبلاً تعیین وضعیت شده است.")
            session.close()
            return

        if action == "approve":
            bot.edit_message_caption("🔄 در حال ساخت سرویس...", call.message.chat.id, call.message.message_id)
            
            # --- شروع پروسه ساخت یوزر (مشابه user.py) ---
            try:
                result = create_service_for_payment(payment, session)
                if result['success']:
                    payment.status = "approved"
                    session.commit()
                    
                    # پیام به ادمین
                    bot.edit_message_caption(f"✅ تایید شد و سرویس ارسال گشت.\nUUID: `{result['uuid']}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
                    
                    # پیام به کاربر
                    user_msg = (
                        "🎉 **پرداخت شما تایید شد!**\n\n"
                        f"✅ سرویس: {payment.plan.name}\n"
                        f"🔗 **لینک اتصال شما:**\n`{result['link']}`\n\n"
                        "از دکمه‌های زیر برای دریافت کانفیگ تکی استفاده کنید."
                    )
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("⚙️ کانفیگ‌های تکی", callback_data=f"get_configs_{result['purchase_id']}"))
                    
                    bot.send_message(payment.user.telegram_id, user_msg, parse_mode="Markdown", reply_markup=markup)
                else:
                    bot.edit_message_caption(f"❌ خطا در ساخت سرویس در پنل:\n{result['error']}", call.message.chat.id, call.message.message_id)
            
            except Exception as e:
                bot.send_message(call.message.chat.id, f"Error: {e}")

        elif action == "reject":
            payment.status = "rejected"
            session.commit()
            bot.edit_message_caption("❌ تراکنش رد شد.", call.message.chat.id, call.message.message_id)
            bot.send_message(payment.user.telegram_id, "❌ متاسفانه پرداخت شما تایید نشد.\nجهت پیگیری با پشتیبانی تماس بگیرید.")

        session.close()

# تابع کمکی: ساخت سرویس بعد از تایید پرداخت
def create_service_for_payment(payment, session):
    plan = payment.plan
    # فرض می‌کنیم پلن به یک یا چند اینباند وصل است. 
    # برای سادگی، روی اولین اینباند متصل به پلن سرویس می‌سازیم (یا روی همه اگر مولتی است)
    if not plan.inbounds:
        return {'success': False, 'error': "این پلن به هیچ سروری متصل نیست!"}

    target_inbound = plan.inbounds[0] # فعلاً اولی را می‌گیریم
    server = target_inbound.server
    
    new_uuid = str(uuid.uuid4())
    email = f"u{new_uuid[:8]}"
    
    xui = XUIClient(server.panel_url, server.username, server.password)
    if not xui.login():
        return {'success': False, 'error': "عدم اتصال به پنل"}

    expire_time = int((datetime.now() + timedelta(days=plan.duration_days)).timestamp() * 1000)
    
    success = xui.add_client(
        inbound_id=target_inbound.xui_id,
        email=email,
        uuid=new_uuid,
        total_gb=plan.volume_gb,
        expiry_time=expire_time,
        enable=True,
        limit_ip=1,
        flow="xtls-rprx-vision" if "reality" in target_inbound.protocol.lower() else ""
    )
    
    if success:
        # لینک سابسکریپشن
        # اگر ساب آیدی نداشتیم از uuid استفاده می‌کنیم
        client_info = xui.get_client_info(target_inbound.xui_id, new_uuid)
        sub_id = client_info.get('subId', new_uuid) if client_info else new_uuid
        
        final_link = f"{server.subscription_url.rstrip('/')}/{sub_id}"
        
        # ثبت خرید
        purchase = Purchase(
            user_id=payment.user_id,
            plan_id=plan.id,
            uuid=new_uuid,
            sub_link=final_link,
            expire_date=datetime.now() + timedelta(days=plan.duration_days),
            is_active=True
        )
        session.add(purchase)
        session.flush() # برای گرفتن ID خرید
        
        return {'success': True, 'link': final_link, 'uuid': new_uuid, 'purchase_id': purchase.id}
    else:
        return {'success': False, 'error': "API پنل خطا داد"}

# نیاز است این تابع را از ماژول بیرون صدا بزنیم
def trigger_payment(bot, message, plan_id):
    # کدی که بالا نوشتیم (start_card_payment) را اینجا صدا می‌زنیم
    # ولی چون داخل تابع تو در تو بود، بهتر است ساختار را فلت کنیم.
    # برای جلوگیری از پیچیدگی کد در اینجا، فرض کنید start_card_payment در دسترس است.
    pass