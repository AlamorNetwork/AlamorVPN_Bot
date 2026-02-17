# handlers/user.py
import uuid
import telebot
from telebot import types
from datetime import datetime, timedelta
from database.base import SessionLocal
from database.models import User, Plan, Server, Inbound, Purchase
from services.xui import XUIClient
from config import ADMIN_IDS

# دیکشنری مراحل خرید
user_steps = {}

def get_db():
    return SessionLocal()

def register_user_handlers(bot: telebot.TeleBot):
    
    # ==========================
    # دستور استارت و منوی شیشه‌ای
    # ==========================
    @bot.message_handler(commands=['start'])
    def cmd_start(message):
        telegram_id = message.from_user.id
        
        # ذخیره کاربر در دیتابیس
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
        # ساخت منوی شیشه‌ای اصلی
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        btn_buy = types.InlineKeyboardButton("🛒 خرید سرویس", callback_data="main_buy")
        btn_services = types.InlineKeyboardButton("👤 سرویس‌های من", callback_data="main_services")
        btn_wallet = types.InlineKeyboardButton("💰 کیف پول", callback_data="main_wallet")
        btn_support = types.InlineKeyboardButton("🎫 پشتیبانی", callback_data="main_support")
        
        markup.add(btn_buy, btn_services)
        markup.add(btn_wallet, btn_support)

        # 🔐 تشخیص هوشمند ادمین
        # اگر کاربر ادمین باشد، دکمه مدیریت را می‌بیند
        if user_id in ADMIN_IDS:
            markup.add(types.InlineKeyboardButton("⚙️ پنل مدیریت (Admin)", callback_data="main_admin_panel"))
        
        text = f"سلام دوست من 👋\nبه ربات هوشمند ما خوش آمدید.\n\nاز منوی زیر انتخاب کنید:"
        bot.send_message(chat_id, text, reply_markup=markup)

    # ==========================
    # هندلرهای منوی اصلی (کال‌بک)
    # ==========================
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('main_'))
    def handle_main_menu(call):
        action = call.data
        
        if action == "main_buy":
            show_plans(bot, call.message)
            
        elif action == "main_services":
            show_user_services(bot, call.message)
            
        elif action == "main_wallet":
            bot.answer_callback_query(call.id, "بخش کیف پول به زودی اضافه می‌شود 💰")
            
        elif action == "main_support":
            bot.answer_callback_query(call.id, "برای پشتیبانی به آیدی ادمین پیام دهید 🎫")

        elif action == "main_admin_panel":
            # این کال‌بک در فایل admin.py هندل می‌شود، اما محض اطمینان اینجا پاس می‌دهیم
            pass 

    # ==========================
    # پروسه خرید (Flow)
    # ==========================
    
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
            btn_text = f"💎 {p.name} | {p.volume_gb} GB | {p.duration_days} روز | {int(p.price):,} T"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"buy_plan_{p.id}"))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
        bot.edit_message_text("📋 **لطفاً تعرفه مورد نظر را انتخاب کنید:**", message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")

    # 2. دریافت پلن و نمایش سرورها
    @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_plan_'))
    def step_select_server(call):
        plan_id = int(call.data.split('_')[-1])
        user_steps[call.from_user.id] = {'plan_id': plan_id}

        session = get_db()
        servers = session.query(Server).filter_by(is_active=True).all()
        valid_servers = [s for s in servers if s.inbounds] # فقط سرورهای دارای اینباند
        session.close()

        if not valid_servers:
            bot.answer_callback_query(call.id, "هیچ سرور فعالی وجود ندارد.")
            return

        markup = types.InlineKeyboardMarkup()
        for s in valid_servers:
            markup.add(types.InlineKeyboardButton(f"🇩🇪 {s.name}", callback_data=f"buy_server_{s.id}"))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="main_buy"))
        bot.edit_message_text("🌍 **لوکیشن سرور را انتخاب کنید:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # 3. دریافت سرور و نمایش اینباندها
    @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_server_'))
    def step_select_inbound(call):
        server_id = int(call.data.split('_')[-1])
        user_steps[call.from_user.id]['server_id'] = server_id

        session = get_db()
        inbounds = session.query(Inbound).filter_by(server_id=server_id, is_active=True).all()
        session.close()

        markup = types.InlineKeyboardMarkup()
        for i in inbounds:
            markup.add(types.InlineKeyboardButton(f"⚡️ {i.remark} ({i.protocol})", callback_data=f"buy_inbound_{i.id}"))
            
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"buy_plan_{user_steps[call.from_user.id]['plan_id']}"))
        bot.edit_message_text("🔌 **نوع اتصال (اپراتور) را انتخاب کنید:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # 4. تایید نهایی و پرداخت
    @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_inbound_'))
    def step_payment(call):
        inbound_id = int(call.data.split('_')[-1])
        user_id = call.from_user.id
        user_steps[user_id]['inbound_id'] = inbound_id
        
        session = get_db()
        data = user_steps[user_id]
        plan = session.query(Plan).get(data['plan_id'])
        server = session.query(Server).get(data['server_id'])
        session.close()

        text = (
            "🧾 **فاکتور نهایی**\n\n"
            f"📦 پلن: {plan.name}\n"
            f"🌍 سرور: {server.name}\n"
            f"💰 مبلغ: {int(plan.price):,} تومان\n\n"
            "جهت دریافت آنی، پرداخت کنید 👇"
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 پرداخت (تستی)", callback_data="pay_confirm"))
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="back_to_main"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # 5. تکمیل خرید و ساخت اکانت
    @bot.callback_query_handler(func=lambda call: call.data == "pay_confirm")
    def process_purchase(call):
        user_id = call.from_user.id
        if user_id not in user_steps: return
        
        bot.edit_message_text("⏳ **در حال ساخت کانفیگ اختصاصی...**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        session = get_db()
        try:
            user_db = session.query(User).filter_by(telegram_id=user_id).first()
            data = user_steps[user_id]
            plan = session.query(Plan).get(data['plan_id'])
            inbound = session.query(Inbound).get(data['inbound_id'])
            server = inbound.server

            new_uuid = str(uuid.uuid4())
            email = f"u{new_uuid[:8]}" 
            
            # اتصال به سرور
            xui = XUIClient(server.panel_url, server.username, server.password)
            if not xui.login():
                bot.send_message(call.message.chat.id, "❌ خطا در اتصال به سرور.")
                return

            expire_time = int((datetime.now() + timedelta(days=plan.duration_days)).timestamp() * 1000)
            
            # ساخت کلاینت
            success = xui.add_client(
                inbound_id=inbound.xui_id,
                email=email,
                uuid=new_uuid,
                total_gb=plan.volume_gb,
                expiry_time=expire_time,
                enable=True,
                limit_ip=1,
                flow="xtls-rprx-vision" if "reality" in inbound.protocol.lower() else ""
            )

            if success:
                client_info = xui.get_client_info(inbound.xui_id, new_uuid)
                sub_id = client_info.get('subId', new_uuid)
                
                final_link = f"{server.subscription_url.rstrip('/')}/{sub_id}"

                new_purchase = Purchase(
                    user_id=user_db.id,
                    inbound_id=inbound.id,
                    uuid=new_uuid,
                    sub_link=final_link,
                    expire_date=datetime.now() + timedelta(days=plan.duration_days),
                    is_active=True
                )
                session.add(new_purchase)
                session.commit()

                msg = (
                    "✅ **خرید موفقیت‌آمیز بود!**\n\n"
                    f"🔗 **لینک اتصال:**\n`{final_link}`\n\n"
                    "روی لینک بزنید تا کپی شود، سپس در نرم‌افزار وارد کنید."
                )
                
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🏠 بازگشت به منو", callback_data="back_to_main"))
                
                bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            else:
                bot.send_message(call.message.chat.id, "❌ خطا در ساخت کاربر.")

        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")
        finally:
            session.close()
            if user_id in user_steps: del user_steps[user_id]

    # دکمه بازگشت به منوی اصلی
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
    def back_to_main(call):
        show_main_menu(bot, call.message.chat.id, call.from_user.id)
        # حذف پیام قبلی برای تمیزی
        bot.delete_message(call.message.chat.id, call.message.message_id)

    # نمایش سرویس‌ها
    def show_user_services(bot, message):
        session = get_db()
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        
        if not user or not user.purchases:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main"))
            bot.edit_message_text("شما هنوز سرویسی ندارید.", message.chat.id, message.message_id, reply_markup=markup)
            session.close()
            return

        bot.delete_message(message.chat.id, message.message_id) # پاک کردن منوی قبلی
        
        for p in user.purchases:
            if not p.is_active: continue
            days_left = (p.expire_date - datetime.now()).days
            status = "🟢 فعال" if days_left > 0 else "🔴 منقضی"
            
            text = (
                f"🔰 **{p.inbound.protocol.upper()}** | {p.inbound.server.name}\n"
                f"📅 انقضا: {days_left} روز دیگر\n"
                f"🔗 `{p.sub_link}`"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main"))
            bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
            
        session.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('get_configs_'))
    def send_single_configs(call):
        purchase_id = int(call.data.split('_')[-1])
        session = get_db()
        purchase = session.query(Purchase).get(purchase_id)
        
        if not purchase:
            bot.answer_callback_query(call.id, "سرویس یافت نشد.")
            session.close()
            return

        # پیدا کردن سرور و تمپلیت
        # چون خرید ما به پلن وصل است، باید سرور را پیدا کنیم
        # (در کد قبلی ساده‌سازی کردیم، فرض می‌کنیم خرید به یک اینباند اصلی وصل بوده یا از طریق پلن پیدا می‌کنیم)
        # راه حل بهتر: در جدول Purchase ستون server_id را نگه داریم یا از طریق رابطه پیدا کنیم.
        # بیایید فرض کنیم رابطه purchase.plan.inbounds[0].server برقرار است.
        
        target_server = purchase.plan.inbounds[0].server
        config_text = ""

        # 1. تلاش برای استفاده از تمپلیت (اولویت با تمپلیت ادمین است چون دقیق‌تر است)
        if target_server.config_template:
            # جایگزینی متغیرها
            # فرمت تمپلیت باید اینطور باشد: vless://UUID@domain:port...
            # ما فقط UUID و EMAIL را عوض می‌کنیم
            email_part = f"u{purchase.uuid[:8]}"
            config_text = target_server.config_template.replace("UUID", purchase.uuid).replace("EMAIL", email_part)
            
            bot.send_message(call.message.chat.id, f"⚙️ **کانفیگ اختصاصی شما:**\n\n`{config_text}`", parse_mode="Markdown")
            
        else:
            # 2. اگر تمپلیت نبود، فقط لینک ساب را می‌دهیم
            bot.send_message(call.message.chat.id, "⚠️ مدیر سرور تمپلیت کانفیگ را تنظیم نکرده است.\nلطفاً از لینک اشتراک استفاده کنید.")

        session.close()