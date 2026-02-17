# handlers/payment_process.py
import telebot
from telebot import types
import uuid
from datetime import datetime, timedelta
from database.base import SessionLocal
from database.models import User, Plan, Payment, Purchase, Server, Inbound
from services.xui import XUIClient
from config import ADMIN_IDS

# تنظیمات کارت (بهتر است بعدا در دیتابیس باشد)
CARD_INFO = """
💳 **6037-9918-xxxx-xxxx**
👤 به نام: فلان فلانی
"""

RULES = """
⚠️ **قوانین:**
۱. ارسال فیش جعلی = مسدودی
۲. اسکرین‌شات باید واضح باشد.
۳. تحویل پس از تایید ادمین انجام می‌شود.
"""

def register_payment_handlers(bot: telebot.TeleBot):
    
    # این تابع از user.py صدا زده می‌شود، اما برای هندل کردن عکس فیش، 
    # باید یک هندلر سراسری داشته باشیم که وضعیت کاربر را چک کند؟
    # راه ساده‌تر: استفاده از register_next_step_handler در start_card_payment
    pass

# توابع کمکی که user.py از آن‌ها استفاده می‌کند

def start_card_payment(bot, message, plan_id):
    session = SessionLocal()
    plan = session.query(Plan).get(plan_id)
    session.close()
    
    if not plan:
        bot.send_message(message.chat.id, "❌ خطا: پلن یافت نشد.")
        return

    text = (
        f"💳 **پرداخت کارت به کارت**\n\n"
        f"📦 سرویس: {plan.name}\n"
        f"💰 مبلغ: **{int(plan.price):,} تومان**\n\n"
        f"{CARD_INFO}\n"
        f"{RULES}\n"
        "📎 **لطفاً عکس فیش واریزی را همینجا ارسال کنید.**"
    )
    
    markup = types.ForceReply(selective=True)
    msg = bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
    
    # رفتن به مرحله دریافت عکس
    bot.register_next_step_handler(msg, process_receipt, bot, plan_id)

def process_receipt(message, bot, plan_id):
    if message.content_type != 'photo':
        msg = bot.send_message(message.chat.id, "❌ لطفاً فقط **عکس** ارسال کنید. دوباره تلاش کنید:")
        bot.register_next_step_handler(msg, process_receipt, bot, plan_id)
        return

    file_id = message.photo[-1].file_id
    user_id = message.from_user.id
    
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        plan = session.query(Plan).get(plan_id)
        
        # ثبت پرداخت
        payment = Payment(
            user_id=user.id,
            plan_id=plan_id,
            amount=plan.price,
            status="pending",
            receipt_image_id=file_id,
            payment_method="card"
        )
        session.add(payment)
        session.commit()
        
        bot.reply_to(message, "✅ فیش شما دریافت شد. منتظر تایید ادمین باشید.")
        
        # اطلاع به ادمین
        notify_admins(bot, payment.id)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}")
    finally:
        session.close()

def notify_admins(bot, payment_id):
    session = SessionLocal()
    payment = session.query(Payment).get(payment_id)
    user = payment.user
    plan = payment.plan
    
    caption = (
        f"🔔 **تراکنش جدید**\n"
        f"👤 {user.first_name} (@{user.username})\n"
        f"📦 {plan.name} | {int(plan.price):,} T\n"
        f"📅 {datetime.now().strftime('%H:%M')}"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ تایید", callback_data=f"pay_approve_{payment.id}"))
    markup.add(types.InlineKeyboardButton("❌ رد", callback_data=f"pay_reject_{payment.id}"))
    
    for admin in ADMIN_IDS:
        try:
            bot.send_photo(admin, payment.receipt_image_id, caption=caption, reply_markup=markup)
        except: pass
    session.close()

# هندلر تایید/رد ادمین (این باید در فایل اصلی رجیستر شود)
def register_callback_handlers(bot: telebot.TeleBot):
    @bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))
    def handle_pay_decision(call):
        if call.from_user.id not in ADMIN_IDS: return
        
        action, pid = call.data.split('_')[1], int(call.data.split('_')[2])
        session = SessionLocal()
        payment = session.query(Payment).get(pid)
        
        if not payment or payment.status != "pending":
            bot.answer_callback_query(call.id, "قبلاً بررسی شده.")
            session.close()
            return

        if action == "approve":
            bot.edit_message_caption(call.message.caption + "\n\n✅ **تایید شد**", call.message.chat.id, call.message.message_id)
            
            # ساخت سرویس
            res = create_service(payment, session)
            if res['success']:
                payment.status = "approved"
                session.commit()
                
                # پیام به کاربر
                user_msg = (
                    "🎉 **پرداخت تایید شد!**\n"
                    f"✅ سرویس: {payment.plan.name}\n"
                    f"🔗 لینک: `{res['link']}`\n\n"
                    "👇 دریافت کانفیگ تکی:"
                )
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("⚙️ کانفیگ تکی", callback_data=f"get_configs_{res['purchase_id']}"))
                bot.send_message(payment.user.telegram_id, user_msg, parse_mode="Markdown", reply_markup=markup)
            else:
                bot.send_message(call.message.chat.id, f"❌ خطا در پنل: {res['error']}")
        
        elif action == "reject":
            payment.status = "rejected"
            session.commit()
            bot.edit_message_caption(call.message.caption + "\n\n❌ **رد شد**", call.message.chat.id, call.message.message_id)
            bot.send_message(payment.user.telegram_id, "❌ پرداخت شما رد شد.")

        session.close()

def create_service(payment, session):
    plan = payment.plan
    # انتخاب اولین اینباند متصل به پلن
    if not plan.inbounds:
        return {'success': False, 'error': "پلن به هیچ سروری وصل نیست"}
    
    inbound = plan.inbounds[0]
    server = inbound.server
    
    new_uuid = str(uuid.uuid4())
    email = f"u{new_uuid[:8]}"
    
    client = XUIClient(server.panel_url, server.username, server.password)
    if not client.login(): return {'success': False, 'error': "Login Failed"}
    
    expire = int((datetime.now() + timedelta(days=plan.duration_days)).timestamp() * 1000)
    
    ok = client.add_client(inbound.xui_id, email, new_uuid, plan.volume_gb, expire, True, 1, 
                           flow="xtls-rprx-vision" if "reality" in inbound.protocol.lower() else "")
    
    if ok:
        info = client.get_client_info(inbound.xui_id, new_uuid)
        sub_id = info.get('subId', new_uuid) if info else new_uuid
        link = f"{server.subscription_url.rstrip('/')}/{sub_id}"
        
        pur = Purchase(user_id=payment.user_id, plan_id=plan.id, uuid=new_uuid, sub_link=link, 
                       expire_date=datetime.now() + timedelta(days=plan.duration_days), is_active=True)
        session.add(pur)
        session.flush()
        return {'success': True, 'link': link, 'purchase_id': pur.id}
    
    return {'success': False, 'error': "API Error"}