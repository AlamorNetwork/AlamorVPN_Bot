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
            # پیام راهنما آپدیت شد 👇
            bot.send_message(uid, "📦 **حجم پلن (GB):**\n(عدد `0` به معنای حجم نامحدود است)", reply_markup=cancel_btn(), parse_mode="Markdown")

        elif step == 'plan_gb':
            if not text.isdigit(): return bot.send_message(uid, "❌ عدد وارد کنید.")
            state['data']['volume_gb'] = float(text)
            state['step'] = 'plan_days'
            # پیام راهنما آپدیت شد 👇
            bot.send_message(uid, "⏳ **مدت زمان (روز):**\n(عدد `0` به معنای زمان نامحدود/لایف‌تایم است)", reply_markup=cancel_btn(), parse_mode="Markdown")

        elif step == 'plan_days':
            if not text.isdigit(): return bot.send_message(uid, "❌ عدد وارد کنید.")
            state['data']['duration_days'] = int(text)
            state['step'] = 'plan_limit_ip' # مرحله جدید
            bot.send_message(uid, "👥 **تعداد کاربر (Limit IP):**\n(مثلاً 1 برای تک‌کاربره، 0 برای نامحدود)", reply_markup=cancel_btn(), parse_mode="Markdown")

        elif step == 'plan_limit_ip':
            if not text.isdigit(): return bot.send_message(uid, "❌ عدد وارد کنید.")
            state['data']['limit_ip'] = int(text)
            state['step'] = 'plan_price'
            bot.send_message(uid, "💰 **قیمت (تومان):**", reply_markup=cancel_btn())

        elif step == 'plan_price':
            if not text.isdigit(): return bot.send_message(uid, "❌ عدد وارد کنید.")
            state['data']['price'] = float(text)
            
            # --- تغییر جدید: به جای ذخیره، لیست سرورها را نشان بده ---
            # پاک کردن استیت متنی چون وارد مرحله دکمه‌ای می‌شویم
            # اما دیتا را نگه می‌داریم
            show_server_selection_for_plan(bot, message)
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
        new_plan = Plan(
            name=data['name'], 
            price=data['price'], 
            volume_gb=data['volume_gb'], 
            duration_days=data['duration_days'],
            limit_ip=data['limit_ip'] # <--- اضافه شد
        )
        
        # اتصال به تمام اینباندهای فعال (برای حل مشکل ساخته نشدن روی همه پورت‌ها)
        # مطمئن شوید که اینباند فعال در دیتابیس دارید!
        all_inbounds = session.query(Inbound).filter_by(is_active=True).all()
        
        if not all_inbounds:
             bot.send_message(message.chat.id, "⚠️ هشدار: هیچ اینباندی در دیتابیس نیست! پلن ساخته شد اما به سروری وصل نیست.")
        else:
            for inbound in all_inbounds:
                new_plan.inbounds.append(inbound)
            
        session.add(new_plan)
        session.commit()
        bot.send_message(message.chat.id, f"✅ پلن **{data['name']}** ساخته شد.\n(متصل به {len(all_inbounds)} اینباند)")
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


    @bot.callback_query_handler(func=lambda call: call.data.startswith('plan_srv_'))
    def select_server_for_plan(call):
        if not is_admin(call.from_user.id): return
        
        server_id = int(call.data.split('_')[-1])
        # ذخیره سرور انتخاب شده در حافظه موقت
        if call.from_user.id in admin_states:
            admin_states[call.from_user.id]['data']['selected_server_id'] = server_id
            # آماده‌سازی لیست خالی برای اینباندها
            admin_states[call.from_user.id]['data']['selected_inbounds'] = []
            
            show_inbound_selection_for_plan(bot, call.message, server_id)

    # هندلر تاگل کردن (انتخاب/حذف) اینباندها
    @bot.callback_query_handler(func=lambda call: call.data.startswith('plan_inb_'))
    def toggle_inbound_for_plan(call):
        if not is_admin(call.from_user.id): return
        user_id = call.from_user.id
        
        if user_id not in admin_states:
            bot.answer_callback_query(call.id, "نشست منقضی شده. دوباره تلاش کنید.")
            return

        inbound_id = int(call.data.split('_')[-1])
        selected_list = admin_states[user_id]['data']['selected_inbounds']
        
        # اگر بود حذف کن، اگر نبود اضافه کن (Toggle)
        if inbound_id in selected_list:
            selected_list.remove(inbound_id)
            msg = "❌ حذف شد"
        else:
            selected_list.append(inbound_id)
            msg = "✅ انتخاب شد"
            
        admin_states[user_id]['data']['selected_inbounds'] = selected_list
        
        # رفرش کردن لیست برای آپدیت شدن تیک‌ها
        server_id = admin_states[user_id]['data']['selected_server_id']
        show_inbound_selection_for_plan(bot, call.message, server_id, refresh=True)
        bot.answer_callback_query(call.id, msg)

    # هندلر نهایی کردن ساخت پلن
    @bot.callback_query_handler(func=lambda call: call.data == "plan_save_final")
    def save_plan_final(call):
        if not is_admin(call.from_user.id): return
        user_id = call.from_user.id
        
        if user_id not in admin_states: return
        
        data = admin_states[user_id]['data']
        if not data.get('selected_inbounds'):
            bot.answer_callback_query(call.id, "⚠️ حداقل یک اینباند انتخاب کنید!", show_alert=True)
            return
            
        save_plan_to_db(bot, call.message, data)
        del admin_states[user_id]


# در انتهای فایل handlers/admin.py

def show_server_selection_for_plan(bot, message):
    session = get_db()
    servers = session.query(Server).filter_by(is_active=True).all()
    session.close()
    
    markup = types.InlineKeyboardMarkup()
    for s in servers:
        # چک میکنیم سرور اینباند داشته باشد
        if s.inbounds:
            markup.add(types.InlineKeyboardButton(f"🖥 {s.name}", callback_data=f"plan_srv_{s.id}"))
            
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_cancel_state"))
    
    bot.send_message(message.chat.id, "🌍 **سرور مورد نظر را انتخاب کنید:**\n(این پلن روی کدام سرور فعال باشد؟)", reply_markup=markup, parse_mode="Markdown")

def show_inbound_selection_for_plan(bot, message, server_id, refresh=False):
    session = get_db()
    server = session.query(Server).get(server_id)
    inbounds = server.inbounds
    session.close()
    
    user_id = message.chat.id if not refresh else message.chat.id # در حالت رفرش message همان call.message است
    
    # گرفتن لیست انتخاب شده‌های فعلی
    selected_ids = []
    if user_id in admin_states:
        selected_ids = admin_states[user_id]['data'].get('selected_inbounds', [])

    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for inbound in inbounds:
        # اگر انتخاب شده بود تیک بزن، اگر نه ضربدر
        status = "✅" if inbound.id in selected_ids else "⬜️"
        text = f"{status} {inbound.remark} | {inbound.protocol} ({inbound.port})"
        markup.add(types.InlineKeyboardButton(text, callback_data=f"plan_inb_{inbound.id}"))
    
    # دکمه تایید نهایی
    btn_text = f"💾 ذخیره نهایی ({len(selected_ids)} انتخاب)"
    markup.add(types.InlineKeyboardButton(btn_text, callback_data="plan_save_final"))
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_cancel_state"))

    text = f"🔌 **اینباندهای سرور {server.name} را انتخاب کنید:**\nبا کلیک روی هر گزینه، آن را فعال/غیرفعال کنید."
    
    if refresh:
        bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=markup, parse_mode="Markdown")

# اصلاح تابع ذخیره نهایی برای استفاده از اینباندهای انتخاب شده
def save_plan_to_db(bot, message, data):
    session = get_db()
    try:
        new_plan = Plan(
            name=data['name'], 
            price=data['price'], 
            volume_gb=data['volume_gb'], 
            duration_days=data['duration_days'],
            limit_ip=data['limit_ip']
        )
        
        # --- تغییر مهم: اتصال فقط به اینباندهای انتخاب شده ---
        selected_ids = data['selected_inbounds']
        selected_inbounds = session.query(Inbound).filter(Inbound.id.in_(selected_ids)).all()
        
        for inbound in selected_inbounds:
            new_plan.inbounds.append(inbound)
            
        session.add(new_plan)
        session.commit()
        
        # حذف پیام منوی انتخاب برای تمیزی
        bot.delete_message(message.chat.id, message.message_id)
        
        msg = (
            f"✅ **پلن با موفقیت ساخته شد!**\n\n"
            f"🏷 نام: {new_plan.name}\n"
            f"🔌 متصل به: {len(selected_inbounds)} اینباند\n"
            f"💰 قیمت: {int(new_plan.price):,} تومان"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}")
    finally:
        session.close()