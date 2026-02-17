# handlers/user.py (نسخه نهایی و اصلاح شده)
import uuid
import telebot
from telebot import types
from datetime import datetime, timedelta
from database.base import SessionLocal
from database.models import User, Plan, Server, Inbound, Purchase
from services.xui import XUIClient
from config import ADMIN_IDS
from handlers.payment_process import start_card_payment 

user_steps = {}

def get_db():
    return SessionLocal()

def register_user_handlers(bot: telebot.TeleBot):
    
    @bot.message_handler(commands=['start'])
    def cmd_start(message):
        telegram_id = message.from_user.id
        session = get_db()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            user = User(
                telegram_id=telegram_id,
                first_name=message.from_user.first_name,
                username=message.from_user.username
            )
            session.add(user)
            session.commit()
        session.close()
        show_main_menu(bot, message.chat.id, message.from_user.id)

    def show_main_menu(bot, chat_id, user_id):
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_buy = types.InlineKeyboardButton("🛒 خرید سرویس", callback_data="main_buy")
        btn_services = types.InlineKeyboardButton("👤 سرویس‌های من", callback_data="main_services")
        btn_wallet = types.InlineKeyboardButton("💰 کیف پول", callback_data="main_wallet")
        btn_support = types.InlineKeyboardButton("🎫 پشتیبانی", callback_data="main_support")
        markup.add(btn_buy, btn_services, btn_wallet, btn_support)
        
        if user_id in ADMIN_IDS:
            markup.add(types.InlineKeyboardButton("⚙️ پنل مدیریت", callback_data="main_admin_panel"))
        
        text = f"سلام دوست من 👋\nبه ربات هوشمند ما خوش آمدید.\n\nاز منوی زیر انتخاب کنید:"
        bot.send_message(chat_id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('main_'))
    def handle_main_menu(call):
        action = call.data
        if action == "main_buy":
            show_plans(bot, call.message)
        elif action == "main_services":
            show_user_services(bot, call.message)
        elif action == "main_wallet":
            bot.answer_callback_query(call.id, "به زودی...")
        elif action == "main_support":
            bot.answer_callback_query(call.id, "پیام خود را ارسال کنید.")
        elif action == "main_admin_panel":
            pass 

    # 1. نمایش پلن‌ها
    def show_plans(bot, message):
        session = get_db()
        plans = session.query(Plan).filter_by(is_active=True).all()
        session.close()

        if not plans:
            bot.edit_message_text("❌ در حال حاضر پلنی وجود ندارد.", message.chat.id, message.message_id)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in plans:
            # فرمت قیمت با کاما
            price_fmt = "{:,}".format(int(p.price))
            btn_text = f"💎 {p.name} | {p.volume_gb} GB | {p.duration_days} روز | {price_fmt} T"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"buy_plan_{p.id}"))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
        
        # استفاده از HTML به جای Markdown برای جلوگیری از ارور
        try:
            bot.edit_message_text("📋 <b>لطفاً تعرفه مورد نظر را انتخاب کنید:</b>", 
                                  message.chat.id, message.message_id, reply_markup=markup, parse_mode="HTML")
        except:
            bot.send_message(message.chat.id, "📋 <b>لطفاً تعرفه مورد نظر را انتخاب کنید:</b>", 
                             reply_markup=markup, parse_mode="HTML")

    # 2. دریافت پلن و نمایش فاکتور نهایی (حذف مرحله انتخاب سرور/اینباند)
    @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_plan_'))
    def step_confirm_plan(call):
        plan_id = int(call.data.split('_')[-1])
        user_steps[call.from_user.id] = {'plan_id': plan_id}

        session = get_db()
        plan = session.query(Plan).get(plan_id)
        
        # چک کنیم آیا پلن به سروری وصل هست؟
        if not plan.inbounds:
            bot.answer_callback_query(call.id, "این پلن موقتاً غیرفعال است (بدون سرور).")
            session.close()
            return

        price_fmt = "{:,}".format(int(plan.price))
        
        text = (
            f"🧾 <b>فاکتور نهایی</b>\n\n"
            f"📦 <b>پلن:</b> {plan.name}\n"
            f"⏳ <b>مدت:</b> {plan.duration_days} روز\n"
            f"💾 <b>حجم:</b> {plan.volume_gb} گیگ\n"
            f"💰 <b>مبلغ قابل پرداخت:</b> {price_fmt} تومان\n\n"
            "جهت دریافت آنی، پرداخت را انجام دهید 👇"
        )
        session.close()

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 پرداخت (کارت به کارت)", callback_data="pay_card"))
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="back_to_main"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")

    # 3. شروع پروسه پرداخت
    @bot.callback_query_handler(func=lambda call: call.data == "pay_card")
    def process_purchase_request(call):
        user_id = call.from_user.id
        if user_id not in user_steps: 
            bot.answer_callback_query(call.id, "لطفاً دوباره انتخاب کنید.")
            return
        
        plan_id = user_steps[user_id]['plan_id']
        start_card_payment(bot, call.message, plan_id)
        
        # پاک کردن استیت
        del user_steps[user_id]

    # دکمه بازگشت
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
    def back_to_main(call):
        show_main_menu(bot, call.message.chat.id, call.from_user.id)
        bot.delete_message(call.message.chat.id, call.message.message_id)

    # نمایش سرویس‌ها
    def show_user_services(bot, message):
        session = get_db()
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        
        if not user or not user.purchases:
            bot.edit_message_text("شما هنوز سرویسی ندارید.", message.chat.id, message.message_id)
            session.close()
            return

        bot.delete_message(message.chat.id, message.message_id)
        
        for p in user.purchases:
            if not p.is_active: continue
            days_left = (p.expire_date - datetime.now()).days
            
            # پیدا کردن اینباند اصلی (برای نمایش نام پروتکل)
            protocol_name = "V2Ray"
            if p.plan and p.plan.inbounds:
                protocol_name = p.plan.inbounds[0].protocol.upper()

            text = (
                f"🔰 <b>سرویس {protocol_name}</b>\n"
                f"📅 انقضا: {days_left} روز دیگر\n"
                f"🔗 <code>{p.sub_link}</code>"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⚙️ دریافت کانفیگ تکی", callback_data=f"get_configs_{p.id}"))
            markup.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main"))
            
            bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")
            
        session.close()

    # دریافت کانفیگ تکی (از تمپلیت)
    @bot.callback_query_handler(func=lambda call: call.data.startswith('get_configs_'))
    def send_single_configs(call):
        pid = int(call.data.split('_')[-1])
        session = get_db()
        purchase = session.query(Purchase).get(pid)
        
        if not purchase:
            bot.answer_callback_query(call.id, "سرویس یافت نشد.")
            session.close()
            return

        # بررسی اینکه آیا سرور تمپلیت دارد؟
        # ما باید سرور را از طریق پلن و اینباندها پیدا کنیم
        # فرض: همه اینباندهای این پلن روی یک سرور هستند (سناریوی ساده)
        if purchase.plan and purchase.plan.inbounds:
            server = purchase.plan.inbounds[0].server
            if server.config_template:
                email_part = f"u{purchase.uuid[:8]}"
                # پر کردن تمپلیت
                config = server.config_template.replace("UUID", purchase.uuid).replace("EMAIL", email_part)
                bot.send_message(call.message.chat.id, f"⚙️ <b>کانفیگ اختصاصی:</b>\n\n<code>{config}</code>", parse_mode="HTML")
            else:
                bot.answer_callback_query(call.id, "تمپلیت کانفیگ تنظیم نشده است.")
        else:
            bot.answer_callback_query(call.id, "اطلاعات سرور یافت نشد.")
        
        session.close()