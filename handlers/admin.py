# handlers/admin.py
import telebot
from telebot import types
from database.base import SessionLocal
from database.models import Server, User, Plan, Inbound, plan_inbound_association
from config import ADMIN_IDS
from services.xui import XUIClient

# وضعیت‌های موقت برای ویزاردها
admin_states = {}

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_db():
    return SessionLocal()

# --- تابع کمکی برای دکمه کنسل ---
def cancel_btn():
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("❌ لغو عملیات", callback_data="admin_cancel_state"))
    return m

def register_admin_handlers(bot: telebot.TeleBot):
    
    # اتصال دکمه منوی اصلی به پنل ادمین
    @bot.callback_query_handler(func=lambda call: call.data == 'main_admin_panel')
    def open_admin_panel(call):
        if not is_admin(call.from_user.id): return
        admin_panel_menu(bot, call.message)

    # دستور مستقیم /admin
    @bot.message_handler(commands=['admin'])
    def cmd_admin(message):
        if not is_admin(message.from_user.id): return
        admin_panel_menu(bot, message)

    def admin_panel_menu(bot, message):
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🖥 سرورها & اینباندها", callback_data="admin_servers_menu"),
            types.InlineKeyboardButton("💰 پلن‌ها", callback_data="admin_plans_menu"),
            types.InlineKeyboardButton("❌ بستن", callback_data="admin_close")
        )
        # چک میکنیم پیام قبلی متن بوده یا کال‌بک برای ویرایش صحیح
        if hasattr(message, 'message_id'):
             try:
                bot.edit_message_text("🛠 **پنل مدیریت پیشرفته**", message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")
             except:
                bot.send_message(message.chat.id, "🛠 **پنل مدیریت پیشرفته**", reply_markup=markup, parse_mode="Markdown")
        else:
             bot.send_message(message.chat.id, "🛠 **پنل مدیریت پیشرفته**", reply_markup=markup, parse_mode="Markdown")

    # ==========================
    # هندلر دکمه‌های ادمین
    # ==========================
    @bot.callback_query_handler(func=lambda call: call.data.startswith('admin_') or call.data.startswith('server_') or call.data.startswith('plan_'))
    def handle_admin_callbacks(call):
        if not is_admin(call.from_user.id): return
        action = call.data
        
        # هندل کردن ارور احتمالی کوری قدیمی
        try:
            bot.answer_callback_query(call.id)
        except:
            pass
        
        if action == "admin_close":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return

        elif action == "admin_cancel_state":
            if call.from_user.id in admin_states:
                del admin_states[call.from_user.id]
            bot.send_message(call.message.chat.id, "❌ عملیات لغو شد.")
            admin_panel_menu(bot, call.message)

        # --- بخش سرورها ---
        elif action == "admin_servers_menu":
            show_servers_menu(bot, call.message)
        elif action == "admin_add_server":
            start_add_server(bot, call.message)
        elif action == "admin_list_servers":
            list_servers(bot, call.message)
        
        elif action.startswith("server_info_"):
            sid = int(action.split("_")[-1])
            show_server_details(bot, call.message, sid)
            
        # FIX: اینجا به جای call.message، خود call را می‌فرستیم
        elif action.startswith("server_sync_"):
            sid = int(action.split("_")[-1])
            sync_server_inbounds(bot, call, sid)
            
        elif action.startswith("server_del_"):
            sid = int(action.split("_")[-1])
            delete_server(bot, call, sid)
            
        elif action.startswith("server_test_"):
            sid = int(action.split("_")[-1])
            test_server_connection(bot, call, sid)

        # --- بخش پلن‌ها ---
        elif action == "admin_plans_menu":
            show_plans_menu(bot, call.message)
        elif action == "admin_add_plan":
            start_add_plan(bot, call.message)
        elif action == "admin_list_plans":
            list_plans(bot, call.message)
        elif action.startswith("plan_del_"):
            pid = int(action.split("_")[-1])
            delete_plan(bot, call, pid)

        # --- بازگشت ---
        elif action == "admin_back_main":
            admin_panel_menu(bot, call.message)

    # ==========================
    # پردازش ورودی‌های متنی (ویزارد)
    # ==========================
    @bot.message_handler(func=lambda msg: is_admin(msg.from_user.id) and msg.from_user.id in admin_states)
    def handle_admin_inputs(message):
        uid = message.chat.id
        state = admin_states[uid]
        step = state['step']
        text = message.text.strip()
        
        # --- ویزارد سرور ---
        if step == 'server_name':
            state['data']['name'] = text
            state['step'] = 'server_url'
            bot.send_message(uid, "🔗 **آدرس پنل را وارد کنید:**\n(مثال: http://1.1.1.1:2053)", reply_markup=cancel_btn())
            
        elif step == 'server_url':
            state['data']['panel_url'] = text.rstrip('/')
            state['step'] = 'server_user'
            bot.send_message(uid, "👤 **نام کاربری پنل:**", reply_markup=cancel_btn())
            
        elif step == 'server_user':
            state['data']['username'] = text
            state['step'] = 'server_pass'
            bot.send_message(uid, "🔑 **رمز عبور پنل:**", reply_markup=cancel_btn())
            
        elif step == 'server_pass':
            state['data']['password'] = text
            state['step'] = 'server_sub'
            bot.send_message(uid, "🌐 **آدرس سابسکریپشن (لینک اتصال):**\n(مثال: https://sub.domain.com/sub)", reply_markup=cancel_btn())
            
        elif step == 'server_sub':
            state['data']['subscription_url'] = text.rstrip('/')
            state['step'] = 'server_template'
            msg = (
                "📝 **(اختیاری) تمپلیت کانفیگ:**\n\n"
                "یک نمونه کانفیگ Vless/Vmess وارد کنید و جای UUID کلمه `UUID` و جای نام کلاینت `EMAIL` را بنویسید.\n"
                "اگر نمی‌خواهید، کلمه `skip` را ارسال کنید.\n\n"
                "مثال:\n`vless://UUID@google.com:443?security=reality&...#EMAIL`"
            )
            bot.send_message(uid, msg, reply_markup=cancel_btn(), parse_mode="Markdown")

        elif step == 'server_template':
            if text.lower() == 'skip':
                state['data']['config_template'] = None
            else:
                state['data']['config_template'] = text
            
            save_server_to_db(bot, message, state['data'])
            del admin_states[uid]

        # --- ویزارد پلن ---
        elif step == 'plan_name':
            state['data']['name'] = text
            state['step'] = 'plan_gb'
            bot.send_message(uid, "📦 **حجم پلن (GB):**", reply_markup=cancel_btn())

        elif step == 'plan_gb':
            if not text.isdigit(): return bot.send_message(uid, "❌ عدد وارد کنید.")
            state['data']['volume_gb'] = float(text)
            state['step'] = 'plan_days'
            bot.send_message(uid, "⏳ **مدت زمان (روز):**", reply_markup=cancel_btn())

        elif step == 'plan_days':
            if not text.isdigit(): return bot.send_message(uid, "❌ عدد وارد کنید.")
            state['data']['duration_days'] = int(text)
            state['step'] = 'plan_price'
            bot.send_message(uid, "💰 **قیمت (تومان):**", reply_markup=cancel_btn())

        elif step == 'plan_price':
            if not text.isdigit(): return bot.send_message(uid, "❌ عدد وارد کنید.")
            state['data']['price'] = float(text)
            
            save_plan_to_db(bot, message, state['data'])
            del admin_states[uid]

# ==========================
# توابع منطقی (Logic Functions)
# ==========================

def show_servers_menu(bot, message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ افزودن سرور", callback_data="admin_add_server"))
    markup.add(types.InlineKeyboardButton("📋 لیست سرورها", callback_data="admin_list_servers"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main"))
    bot.edit_message_text("🖥 **مدیریت سرورها**", message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")

def list_servers(bot, message):
    session = get_db()
    servers = session.query(Server).all()
    session.close()
    
    if not servers:
        try: bot.answer_callback_query(message.id, "لیست خالی است.") # اینجا message.id درست نیست اگر از کال‌بک نیاید ولی چون list_servers از کال‌بک میاد مشکلی نیست
        except: pass
        bot.send_message(message.chat.id, "هیچ سروری ثبت نشده است.")
        return

    markup = types.InlineKeyboardMarkup()
    for s in servers:
        markup.add(types.InlineKeyboardButton(f"🖥 {s.name}", callback_data=f"server_info_{s.id}"))
    markup.add(types.InlineKeyboardButton("🔙", callback_data="admin_servers_menu"))
    bot.edit_message_text("یک سرور را انتخاب کنید:", message.chat.id, message.message_id, reply_markup=markup)

def show_server_details(bot, message, server_id):
    session = get_db()
    server = session.query(Server).get(server_id)
    if not server:
        session.close()
        return

    inbound_count = len(server.inbounds)
    status_icon = "✅" if server.is_active else "❌"
    
    text = (
        f"🖥 **سرور:** `{server.name}`\n"
        f"🔗 **آدرس:** `{server.panel_url}`\n"
        f"📡 **تعداد اینباندها:** {inbound_count}\n"
        f"وضعیت: {status_icon}\n\n"
        "برای فروش، باید اینباندهای سرور را همگام‌سازی کنید."
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📡 تست اتصال", callback_data=f"server_test_{server.id}"),
        types.InlineKeyboardButton("🔄 همگام‌سازی اینباندها", callback_data=f"server_sync_{server.id}")
    )
    markup.add(types.InlineKeyboardButton("🗑 حذف سرور", callback_data=f"server_del_{server.id}"))
    markup.add(types.InlineKeyboardButton("🔙", callback_data="admin_list_servers"))
    
    bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")
    session.close()

def start_add_server(bot, message):
    admin_states[message.chat.id] = {'step': 'server_name', 'data': {}}
    bot.edit_message_text("📝 **نام سرور را وارد کنید:**\n(مثال: Germany-1)", message.chat.id, message.message_id, reply_markup=cancel_btn(), parse_mode="Markdown")

def save_server_to_db(bot, message, data):
    session = get_db()
    try:
        s = Server(
            name=data['name'], 
            panel_url=data['panel_url'], 
            username=data['username'], 
            password=data['password'], 
            subscription_url=data['subscription_url'],
            config_template=data.get('config_template')
        )
        session.add(s)
        session.commit()
        bot.send_message(message.chat.id, "✅ سرور ذخیره شد. لطفاً **همگام‌سازی اینباند** را انجام دهید.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}")
    finally:
        session.close()

# FIX: دریافت 'call' به جای 'message'
def delete_server(bot, call, server_id):
    try: bot.answer_callback_query(call.id, "در حال حذف...") 
    except: pass

    session = get_db()
    server = session.query(Server).get(server_id)
    if server:
        session.delete(server)
        session.commit()
        list_servers(bot, call.message)
    session.close()

# FIX: دریافت 'call' به جای 'message'
def test_server_connection(bot, call, server_id):
    try: bot.answer_callback_query(call.id, "⏳ در حال تست اتصال...") 
    except: pass
    
    session = get_db()
    server = session.query(Server).get(server_id)
    session.close()

    client = XUIClient(server.panel_url, server.username, server.password)
    
    if client.login():
        stats = client.get_system_status()
        online_count = len(stats) if stats else 0
        bot.send_message(call.message.chat.id, f"✅ **اتصال موفق بود!**\nسرور: `{server.name}`\nکاربران آنلاین: {online_count}", parse_mode="Markdown")
    else:
        bot.send_message(call.message.chat.id, f"❌ **اتصال ناموفق!**\nاطلاعات سرور را چک کنید.")

# FIX: دریافت 'call' به جای 'message'
def sync_server_inbounds(bot, call, server_id):
    try: bot.answer_callback_query(call.id, "⏳ در حال دریافت لیست...") 
    except: pass

    session = get_db()
    server = session.query(Server).get(server_id)
    
    client = XUIClient(server.panel_url, server.username, server.password)
    
    if not client.login():
        bot.send_message(call.message.chat.id, "❌ خطا در اتصال به پنل.")
        session.close()
        return

    xui_inbounds = client.get_inbounds()
    if not xui_inbounds:
        bot.send_message(call.message.chat.id, "⚠️ هیچ اینباندی یافت نشد.")
        session.close()
        return

    added, updated = 0, 0
    for item in xui_inbounds:
        exists = session.query(Inbound).filter_by(server_id=server.id, xui_id=item['id']).first()
        if exists:
            exists.remark = item['remark']
            exists.port = item['port']
            exists.protocol = item['protocol']
            updated += 1
        else:
            new_inbound = Inbound(
                server_id=server.id,
                xui_id=item['id'],
                remark=item['remark'],
                port=item['port'],
                protocol=item['protocol']
            )
            session.add(new_inbound)
            added += 1
            
    session.commit()
    session.close()
    bot.send_message(call.message.chat.id, f"✅ عملیات موفق!\n➕ جدید: {added}\n🔄 آپدیت: {updated}")
    show_server_details(bot, call.message, server_id)

# --- توابع پلن ---
def show_plans_menu(bot, message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ افزودن پلن", callback_data="admin_add_plan"))
    markup.add(types.InlineKeyboardButton("📋 لیست پلن‌ها", callback_data="admin_list_plans"))
    markup.add(types.InlineKeyboardButton("🔙", callback_data="admin_back_main"))
    bot.edit_message_text("مدیریت پلن‌ها:", message.chat.id, message.message_id, reply_markup=markup)

def start_add_plan(bot, message):
    admin_states[message.chat.id] = {'step': 'plan_name', 'data': {}}
    bot.edit_message_text("📝 نام پلن:", message.chat.id, message.message_id, reply_markup=cancel_btn())

def save_plan_to_db(bot, message, data):
    session = get_db()
    try:
        new_plan = Plan(name=data['name'], price=data['price'], volume_gb=data['volume_gb'], duration_days=data['duration_days'])
        
        all_inbounds = session.query(Inbound).filter_by(is_active=True).all()
        for inbound in all_inbounds:
            new_plan.inbounds.append(inbound)
            
        session.add(new_plan)
        session.commit()
        bot.send_message(message.chat.id, f"✅ پلن **{data['name']}** ساخته شد.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}")
    finally:
        session.close()

def list_plans(bot, message):
    session = get_db()
    plans = session.query(Plan).all()
    session.close()
    if not plans: 
        try: bot.answer_callback_query(message.id, "خالی است.") 
        except: pass
        return
    
    text = "📋 لیست پلن‌ها:\n"
    markup = types.InlineKeyboardMarkup()
    for p in plans:
        text += f"🔹 {p.name} - {int(p.price):,} T\n"
        markup.add(types.InlineKeyboardButton(f"🗑 حذف {p.name}", callback_data=f"plan_del_{p.id}"))
    markup.add(types.InlineKeyboardButton("🔙", callback_data="admin_plans_menu"))
    bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=markup)

# FIX: دریافت 'call' به جای 'message'
def delete_plan(bot, call, pid):
    try: bot.answer_callback_query(call.id, "در حال حذف...")
    except: pass
    
    session = get_db()
    p = session.query(Plan).get(pid)
    if p:
        session.delete(p)
        session.commit()
        list_plans(bot, call.message)
    session.close()