# handlers/admin.py
import telebot
from telebot import types
from sqlalchemy.orm import Session
from database.base import SessionLocal
from database.models import Server, User, Plan
from config import ADMIN_IDS
from services.xui import XUIClient

# وضعیت‌های موقت برای ویزاردها (افزودن سرور و پلن)
admin_states = {}

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_db():
    return SessionLocal()

def register_admin_handlers(bot: telebot.TeleBot):
    
    # ==========================
    # منوی اصلی ادمین
    # ==========================
    @bot.message_handler(commands=['admin'])
    def admin_panel(message):
        if not is_admin(message.from_user.id): return

        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_servers = types.InlineKeyboardButton("🖥 مدیریت سرورها", callback_data="admin_servers_menu")
        btn_plans = types.InlineKeyboardButton("💰 مدیریت پلن‌ها", callback_data="admin_plans_menu")
        btn_users = types.InlineKeyboardButton("👥 آمار کاربران", callback_data="admin_users_stats")
        btn_close = types.InlineKeyboardButton("❌ بستن پنل", callback_data="admin_close")
        
        markup.add(btn_servers, btn_plans)
        markup.add(btn_users)
        markup.add(btn_close)

        text = "🛠 **پنل مدیریت ربات**\n\nلطفاً بخش مورد نظر را انتخاب کنید:"
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

    # ==========================
    # هندلر دکمه‌های منوی اصلی
    # ==========================
    @bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
    def handle_admin_callbacks(call):
        if not is_admin(call.from_user.id): return
        
        action = call.data
        
        if action == "admin_close":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return

        # --- بخش سرورها ---
        if action == "admin_servers_menu":
            show_servers_menu(bot, call.message)
            
        elif action == "admin_add_server":
            start_add_server(bot, call.message)
            
        elif action == "admin_list_servers":
            list_servers(bot, call.message)

        elif action.startswith("server_info_"):
            server_id = int(action.split("_")[-1])
            show_server_details(bot, call.message, server_id)

        elif action.startswith("server_test_"):
            server_id = int(action.split("_")[-1])
            test_server_connection(bot, call.message, server_id)

        elif action.startswith("server_delete_"):
            server_id = int(action.split("_")[-1])
            delete_server(bot, call.message, server_id)

        # --- بخش پلن‌ها ---
        elif action == "admin_plans_menu":
            show_plans_menu(bot, call.message)

        elif action == "admin_add_plan":
            start_add_plan(bot, call.message)

        elif action == "admin_list_plans":
            list_plans(bot, call.message)
            
        elif action.startswith("plan_delete_"):
            plan_id = int(action.split("_")[-1])
            delete_plan(bot, call.message, plan_id)

        # --- دکمه بازگشت ---
        elif action == "admin_back_main":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            admin_panel(call.message)

        elif action == "admin_cancel_state":
            if call.from_user.id in admin_states:
                del admin_states[call.from_user.id]
            bot.send_message(call.message.chat.id, "❌ عملیات لغو شد.")
            admin_panel(call.message)

    # ==========================
    # پردازش ورودی‌های متنی (ویزاردها)
    # ==========================
    @bot.message_handler(func=lambda msg: is_admin(msg.from_user.id) and msg.from_user.id in admin_states)
    def handle_admin_inputs(message):
        user_id = message.from_user.id
        state = admin_states[user_id]
        step = state['step']
        text = message.text.strip()
        
        # --- ویزارد افزودن سرور ---
        if step.startswith('server_'):
            process_server_wizard(bot, message, state, text)
            
        # --- ویزارد افزودن پلن ---
        elif step.startswith('plan_'):
            process_plan_wizard(bot, message, state, text)

# ==========================================================
#  بخش مدیریت سرورها (Logic)
# ==========================================================

def show_servers_menu(bot, message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ افزودن سرور جدید", callback_data="admin_add_server"))
    markup.add(types.InlineKeyboardButton("📋 لیست سرورها", callback_data="admin_list_servers"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main"))
    
    bot.edit_message_text("🖥 **مدیریت سرورها**\nیک گزینه را انتخاب کنید:", 
                          message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")

def list_servers(bot, message):
    session = get_db()
    servers = session.query(Server).all()
    session.close()

    if not servers:
        bot.answer_callback_query(message.id, "هیچ سروری ثبت نشده است.")
        return

    markup = types.InlineKeyboardMarkup()
    for s in servers:
        # دکمه برای هر سرور
        markup.add(types.InlineKeyboardButton(f"{s.name} ({s.panel_url})", callback_data=f"server_info_{s.id}"))
    
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_servers_menu"))
    
    bot.edit_message_text("📋 برای مدیریت روی نام سرور کلیک کنید:", 
                          message.chat.id, message.message_id, reply_markup=markup)

def show_server_details(bot, message, server_id):
    session = get_db()
    server = session.query(Server).get(server_id)
    session.close()

    if not server:
        bot.answer_callback_query(message.id, "سرور یافت نشد.")
        return

    text = (
        f"🖥 **جزئیات سرور:** `{server.name}`\n\n"
        f"🔗 **URL:** `{server.panel_url}`\n"
        f"👤 **User:** `{server.username}`\n"
        f"🌐 **Sub URL:** `{server.subscription_url}`\n"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📡 تست اتصال", callback_data=f"server_test_{server.id}"),
        types.InlineKeyboardButton("🗑 حذف", callback_data=f"server_delete_{server.id}")
    )
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_list_servers"))

    bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")

def test_server_connection(bot, message, server_id):
    session = get_db()
    server = session.query(Server).get(server_id)
    session.close()

    bot.answer_callback_query(message.id, "⏳ در حال تست اتصال...")
    
    client = XUIClient(server.panel_url, server.username, server.password)
    if client.login():
        stats = client.get_system_status()
        online_count = len(stats) if stats else 0
        bot.send_message(message.chat.id, f"✅ **اتصال موفق بود!**\nسرور: `{server.name}`\nکاربران آنلاین: {online_count}", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, f"❌ **اتصال ناموفق!**\nلطفاً آدرس، یوزرنیم و پسورد سرور `{server.name}` را بررسی کنید.", parse_mode="Markdown")

def delete_server(bot, message, server_id):
    session = get_db()
    server = session.query(Server).get(server_id)
    if server:
        session.delete(server)
        session.commit()
        bot.answer_callback_query(message.id, "سرور حذف شد ✅")
        list_servers(bot, message)
    else:
        bot.answer_callback_query(message.id, "خطا در حذف.")
    session.close()

# --- ویزارد افزودن سرور ---
def start_add_server(bot, message):
    admin_states[message.chat.id] = {'step': 'server_name', 'data': {}}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_cancel_state"))
    
    bot.edit_message_text("📝 **نام سرور را وارد کنید:**\n(مثال: Germany-1)", 
                          message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")

def process_server_wizard(bot, message, state, text):
    step = state['step']
    user_id = message.chat.id
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_cancel_state"))

    if step == 'server_name':
        state['data']['name'] = text
        state['step'] = 'server_url'
        bot.send_message(user_id, "🔗 **آدرس پنل را وارد کنید:**\n(مثال: http://1.1.1.1:2053)", reply_markup=markup)
        
    elif step == 'server_url':
        state['data']['panel_url'] = text.rstrip('/')
        state['step'] = 'server_user'
        bot.send_message(user_id, "👤 **نام کاربری پنل:**", reply_markup=markup)
        
    elif step == 'server_user':
        state['data']['username'] = text
        state['step'] = 'server_pass'
        bot.send_message(user_id, "🔑 **رمز عبور پنل:**", reply_markup=markup)
        
    elif step == 'server_pass':
        state['data']['password'] = text
        state['step'] = 'server_sub'
        bot.send_message(user_id, "🌐 **آدرس سابسکریپشن (لینک اتصال):**\n(مثال: https://sub.mydomain.com/sub)", reply_markup=markup)
        
    elif step == 'server_sub':
        state['data']['subscription_url'] = text.rstrip('/')
        
        # ذخیره در دیتابیس
        save_server(bot, message, state['data'])
        del admin_states[user_id]

def save_server(bot, message, data):
    session = get_db()
    try:
        new_server = Server(
            name=data['name'],
            panel_url=data['panel_url'],
            username=data['username'],
            password=data['password'],
            subscription_url=data['subscription_url']
        )
        session.add(new_server)
        session.commit()
        bot.send_message(message.chat.id, "✅ سرور با موفقیت ذخیره شد.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطا در ذخیره: {e}")
    finally:
        session.close()


# ==========================================================
#  بخش مدیریت پلن‌ها (Logic)
# ==========================================================

def show_plans_menu(bot, message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="admin_add_plan"))
    markup.add(types.InlineKeyboardButton("📋 لیست پلن‌ها", callback_data="admin_list_plans"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main"))
    
    bot.edit_message_text("💰 **مدیریت پلن‌های فروش**\nیک گزینه را انتخاب کنید:", 
                          message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")

def list_plans(bot, message):
    session = get_db()
    plans = session.query(Plan).all()
    session.close()

    if not plans:
        bot.answer_callback_query(message.id, "هیچ پلنی تعریف نشده است.")
        return

    text = "📋 **لیست تعرفه‌های فعال:**\n\n"
    markup = types.InlineKeyboardMarkup()
    
    for p in plans:
        text += f"🔹 **{p.name}**\n   💰 {p.price:,} تومان | ⏳ {p.duration_days} روزه | 📦 {p.volume_gb} گیگ\n\n"
        markup.add(types.InlineKeyboardButton(f"🗑 حذف {p.name}", callback_data=f"plan_delete_{p.id}"))
    
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_plans_menu"))
    bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")

def delete_plan(bot, message, plan_id):
    session = get_db()
    plan = session.query(Plan).get(plan_id)
    if plan:
        session.delete(plan)
        session.commit()
        bot.answer_callback_query(message.id, "پلن حذف شد ✅")
        list_plans(bot, message)
    else:
        bot.answer_callback_query(message.id, "خطا در حذف.")
    session.close()

# --- ویزارد افزودن پلن ---
def start_add_plan(bot, message):
    admin_states[message.chat.id] = {'step': 'plan_name', 'data': {}}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_cancel_state"))
    
    bot.edit_message_text("📝 **نام پلن را وارد کنید:**\n(مثال: یک ماهه ۲۰ گیگ)", 
                          message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")

def process_plan_wizard(bot, message, state, text):
    step = state['step']
    user_id = message.chat.id
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_cancel_state"))

    if step == 'plan_name':
        state['data']['name'] = text
        state['step'] = 'plan_volume'
        bot.send_message(user_id, "📦 **حجم پلن (گیگابایت):**\n(فقط عدد، مثلا: 20)", reply_markup=markup)

    elif step == 'plan_volume':
        if not text.isdigit():
            bot.send_message(user_id, "❌ لطفاً فقط عدد وارد کنید.")
            return
        state['data']['volume_gb'] = float(text)
        state['step'] = 'plan_days'
        bot.send_message(user_id, "⏳ **مدت زمان (روز):**\n(فقط عدد، مثلا: 30)", reply_markup=markup)

    elif step == 'plan_days':
        if not text.isdigit():
            bot.send_message(user_id, "❌ لطفاً فقط عدد وارد کنید.")
            return
        state['data']['duration_days'] = int(text)
        state['step'] = 'plan_price'
        bot.send_message(user_id, "💰 **قیمت (تومان):**\n(فقط عدد، مثلا: 50000)", reply_markup=markup)

    elif step == 'plan_price':
        if not text.isdigit():
            bot.send_message(user_id, "❌ لطفاً فقط عدد وارد کنید.")
            return
        state['data']['price'] = float(text)
        
        # ذخیره پلن
        save_plan(bot, message, state['data'])
        del admin_states[user_id]

def save_plan(bot, message, data):
    session = get_db()
    try:
        new_plan = Plan(
            name=data['name'],
            price=data['price'],
            volume_gb=data['volume_gb'],
            duration_days=data['duration_days']
        )
        session.add(new_plan)
        session.commit()
        bot.send_message(message.chat.id, f"✅ پلن **{data['name']}** با موفقیت ایجاد شد.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطا در ذخیره: {e}")
    finally:
        session.close()