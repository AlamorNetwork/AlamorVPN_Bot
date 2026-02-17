# handlers/user.py
import uuid
import telebot
from telebot import types
from datetime import datetime, timedelta
from database.base import SessionLocal
from database.models import User, Plan, Server, Inbound, Purchase, Payment
from services.xui import XUIClient

# دیکشنری برای ذخیره مراحل خرید کاربر
# {user_id: {'plan_id': 1, 'server_id': 2, 'inbound_id': 5}}
user_steps = {}

def get_db():
    return SessionLocal()

def register_user_handlers(bot: telebot.TeleBot):
    
    # ==========================
    # دستور استارت و منوی اصلی
    # ==========================
    @bot.message_handler(commands=['start'])
    def cmd_start(message):
        telegram_id = message.from_user.id
        
        # ذخیره یا آپدیت کاربر در دیتابیس
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

        # منوی اصلی
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🛒 خرید سرویس", "👤 سرویس‌های من")
        markup.add("🎫 پشتیبانی", "💰 کیف پول")
        
        bot.send_message(message.chat.id, f"سلام {message.from_user.first_name} عزیز 👋\nبه ربات خرید فیلترشکن خوش آمدید.", reply_markup=markup)

    # ==========================
    # هندلرهای منوی متنی
    # ==========================
    @bot.message_handler(func=lambda msg: msg.text == "🛒 خرید سرویس")
    def menu_buy(message):
        show_plans(bot, message)

    @bot.message_handler(func=lambda msg: msg.text == "👤 سرویس‌های من")
    def menu_my_services(message):
        show_user_services(bot, message)

    # ==========================
    # پروسه خرید (Flow)
    # ==========================
    
    # 1. نمایش پلن‌ها
    def show_plans(bot, message):
        session = get_db()
        plans = session.query(Plan).filter_by(is_active=True).all()
        session.close()

        if not plans:
            bot.send_message(message.chat.id, "❌ در حال حاضر پلنی برای فروش وجود ندارد.")
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in plans:
            btn_text = f"💎 {p.name} | {p.volume_gb} GB | {p.duration_days} روز | {int(p.price):,} تومان"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"buy_plan_{p.id}"))
        
        bot.send_message(message.chat.id, "📋 **لطفاً یکی از تعرفه‌های زیر را انتخاب کنید:**", reply_markup=markup, parse_mode="Markdown")

    # 2. دریافت پلن و نمایش سرورها
    @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_plan_'))
    def step_select_server(call):
        plan_id = int(call.data.split('_')[-1])
        user_steps[call.from_user.id] = {'plan_id': plan_id}

        session = get_db()
        servers = session.query(Server).filter_by(is_active=True).all()
        
        # فقط سرورهایی که اینباند دارند را نشان بده
        valid_servers = [s for s in servers if s.inbounds]
        session.close()

        if not valid_servers:
            bot.answer_callback_query(call.id, "هیچ سرور فعالی وجود ندارد.")
            return

        markup = types.InlineKeyboardMarkup()
        for s in valid_servers:
            markup.add(types.InlineKeyboardButton(f"🇩🇪 {s.name}", callback_data=f"buy_server_{s.id}"))
        
        bot.edit_message_text("🌍 **لطفاً لوکیشن (سرور) خود را انتخاب کنید:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # 3. دریافت سرور و نمایش اینباندها (پورت‌ها)
    @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_server_'))
    def step_select_inbound(call):
        server_id = int(call.data.split('_')[-1])
        if call.from_user.id not in user_steps:
            bot.answer_callback_query(call.id, "نشست منقضی شد. دوباره تلاش کنید.")
            return
        
        user_steps[call.from_user.id]['server_id'] = server_id

        session = get_db()
        inbounds = session.query(Inbound).filter_by(server_id=server_id, is_active=True).all()
        session.close()

        markup = types.InlineKeyboardMarkup()
        for i in inbounds:
            # نمایش نام اینباند و پروتکل (مثلاً: همراه اول - VLESS)
            markup.add(types.InlineKeyboardButton(f"⚡️ {i.remark} ({i.protocol})", callback_data=f"buy_inbound_{i.id}"))
            
        bot.edit_message_text("🔌 **لطفاً نوع اتصال (اپراتور) را انتخاب کنید:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # 4. تایید نهایی و پرداخت
    @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_inbound_'))
    def step_payment(call):
        inbound_id = int(call.data.split('_')[-1])
        user_id = call.from_user.id
        
        if user_id not in user_steps: return
        user_steps[user_id]['inbound_id'] = inbound_id
        
        # خواندن اطلاعات برای فاکتور
        data = user_steps[user_id]
        session = get_db()
        plan = session.query(Plan).get(data['plan_id'])
        server = session.query(Server).get(data['server_id'])
        session.close()

        text = (
            "🧾 **فاکتور نهایی**\n\n"
            f"📦 پلن: {plan.name}\n"
            f"🌍 سرور: {server.name}\n"
            f"💰 مبلغ قابل پرداخت: {int(plan.price):,} تومان\n\n"
            "💳 لطفاً جهت تکمیل خرید، پرداخت را انجام دهید."
        )

        markup = types.InlineKeyboardMarkup()
        # اینجا بعداً درگاه زرین‌پال یا کارت‌به‌کارت وصل می‌شود. فعلاً دکمه "پرداخت تستی" داریم.
        markup.add(types.InlineKeyboardButton("✅ پرداخت تستی (موجودی)", callback_data="pay_confirm"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # 5. تکمیل خرید و ساخت اکانت
    @bot.callback_query_handler(func=lambda call: call.data == "pay_confirm")
    def process_purchase(call):
        user_id = call.from_user.id
        if user_id not in user_steps: return
        
        data = user_steps[user_id]
        bot.edit_message_text("⏳ **در حال ساخت کانفیگ اختصاصی شما...**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        session = get_db()
        try:
            # 1. گرفتن اطلاعات از دیتابیس
            user_db = session.query(User).filter_by(telegram_id=user_id).first()
            plan = session.query(Plan).get(data['plan_id'])
            inbound = session.query(Inbound).get(data['inbound_id'])
            server = inbound.server # دسترسی به سرور از طریق رابطه

            # 2. تولید UUID و نام کاربری
            new_uuid = str(uuid.uuid4())
            email = f"user_{new_uuid[:8]}" # ایمیل رندوم برای پنل
            
            # 3. اتصال به پنل ثنایی و ساخت یوزر
            xui = XUIClient(server.panel_url, server.username, server.password)
            
            # لاگین
            if not xui.login():
                bot.send_message(call.message.chat.id, "❌ خطای فنی در اتصال به سرور. مبلغ به کیف پول برگشت خورد.")
                return

            # محاسبه زمان انقضا (Timestamp به میلی‌ثانیه)
            expire_time = int((datetime.now() + timedelta(days=plan.duration_days)).timestamp() * 1000)
            
            # ارسال درخواست ساخت به پنل
            # نکته: ما از xui_id که در دیتابیس ذخیره کردیم استفاده می‌کنیم
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
                # 4. دریافت ساب آیدی (برای لینک سابسکریپشن)
                # در پنل‌های جدید ساب آیدی خودکار ساخته می‌شود، باید کلاینت را دوباره بگیریم تا subId را بفهمیم
                client_info = xui.get_client_info(inbound.xui_id, new_uuid)
                sub_id = client_info.get('subId', new_uuid) # اگر ساب آیدی نداشت (پنل قدیمی)، از uuid استفاده کن
                
                # ساخت لینک نهایی
                final_link = f"{server.subscription_url.rstrip('/')}/{sub_id}"

                # 5. ثبت خرید در دیتابیس
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

                # 6. تحویل به کاربر
                msg = (
                    "✅ **خرید با موفقیت انجام شد!**\n\n"
                    f"🔗 **لینک اتصال شما:**\n`{final_link}`\n\n"
                    "⚠️ این لینک را در نرم‌افزار V2rayNG یا Streisand کپی کنید.\n"
                    "🔄 برای آپدیت حجم، همین لینک را در نرم‌افزار Update کنید."
                )
                bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
            else:
                bot.send_message(call.message.chat.id, "❌ خطا در ساخت کاربر در پنل. لطفاً با پشتیبانی تماس بگیرید.")

        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ خطای سیستمی: {e}")
            print(e)
        finally:
            session.close()
            del user_steps[user_id]

    # ==========================
    # نمایش سرویس‌های کاربر
    # ==========================
    def show_user_services(bot, message):
        telegram_id = message.from_user.id
        session = get_db()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user or not user.purchases:
            bot.send_message(message.chat.id, "شما هنوز سرویسی خریداری نکرده‌اید.")
            session.close()
            return

        for p in user.purchases:
            if not p.is_active: continue
            
            # محاسبه روزهای باقیمانده
            days_left = (p.expire_date - datetime.now()).days
            
            status = "🟢 فعال" if days_left > 0 else "🔴 منقضی"
            
            text = (
                f"🔰 **سرویس {p.inbound.protocol.upper()}**\n"
                f"📅 انقضا: {p.expire_date.strftime('%Y-%m-%d')} ({days_left} روز دیگر)\n"
                f" وضعیت: {status}\n\n"
                f"🔗 لینک: `{p.sub_link}`"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔄 دریافت QR Code", callback_data=f"qr_{p.id}"))
            
            bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
            
        session.close()

    # QR Code Handler
    @bot.callback_query_handler(func=lambda call: call.data.startswith('qr_'))
    def send_qr(call):
        # اینجا بعداً کد تولید QR را اضافه می‌کنیم
        bot.answer_callback_query(call.id, "این قابلیت به زودی اضافه می‌شود.")