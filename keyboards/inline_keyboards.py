# keyboards/inline_keyboards.py

from telebot import types
import logging

logger = logging.getLogger(__name__)

# --- توابع کیبورد ادمین ---

def get_admin_main_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ مدیریت سرورها", callback_data="admin_server_management"),
        types.InlineKeyboardButton("💰 مدیریت پلن‌ها", callback_data="admin_plan_management"),
        types.InlineKeyboardButton("💳 مدیریت درگاه‌ها", callback_data="admin_payment_management"),
        types.InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_user_management"),
        types.InlineKeyboardButton("📊 داشبورد", callback_data="admin_dashboard"),
        types.InlineKeyboardButton("🗄 تهیه نسخه پشتیبان", callback_data="admin_create_backup")
    )
    return markup

def get_server_management_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ افزودن سرور", callback_data="admin_add_server"),
        types.InlineKeyboardButton("📝 لیست سرورها", callback_data="admin_list_servers"),
        types.InlineKeyboardButton("🔌 مدیریت Inboundها", callback_data="admin_manage_inbounds"),
        types.InlineKeyboardButton("🔄 تست اتصال سرورها", callback_data="admin_test_all_servers"),
        types.InlineKeyboardButton("❌ حذف سرور", callback_data="admin_delete_server"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_main_menu")
    )
    return markup
    
def get_plan_management_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ افزودن پلن", callback_data="admin_add_plan"),
        types.InlineKeyboardButton("📝 لیست پلن‌ها", callback_data="admin_list_plans"),
        types.InlineKeyboardButton("🔄 تغییر وضعیت پلن", callback_data="admin_toggle_plan_status"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_main_menu")
    )
    return markup

def get_payment_gateway_management_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ افزودن درگاه", callback_data="admin_add_gateway"),
        types.InlineKeyboardButton("📝 لیست درگاه‌ها", callback_data="admin_list_gateways"),
        types.InlineKeyboardButton("🔄 تغییر وضعیت درگاه", callback_data="admin_toggle_gateway_status"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_main_menu")
    )
    return markup
    
def get_user_management_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📋 لیست همه کاربران", callback_data="admin_list_users"),
        types.InlineKeyboardButton("🔎 جستجوی کاربر", callback_data="admin_search_user"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_main_menu")
    )
    return markup

def get_plan_type_selection_menu_admin():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("ماهانه (Fixed)", callback_data="plan_type_fixed_monthly"),
        types.InlineKeyboardButton("حجمی (Gigabyte)", callback_data="plan_type_gigabyte_based"),
        types.InlineKeyboardButton("🔙 انصراف", callback_data="admin_plan_management")
    )
    return markup
    
def get_gateway_type_selection_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 کارت به کارت", callback_data="gateway_type_card_to_card"),
        types.InlineKeyboardButton("🔙 انصراف", callback_data="admin_payment_management")
    )
    return markup
    
def get_inbound_selection_menu(server_id: int, panel_inbounds: list, active_inbound_ids: list):
    """
    منوی انتخاب اینباندها با ترفند ضد-کش (anti-cache) برای اطمینان از آپدیت شدن.
    """
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ انتخاب همه", callback_data=f"inbound_select_all_{server_id}"),
        types.InlineKeyboardButton("⬜️ لغو انتخاب همه", callback_data=f"inbound_deselect_all_{server_id}")
    )

    for inbound in panel_inbounds:
        inbound_id = inbound['id']
        is_active = inbound_id in active_inbound_ids
        emoji = "✅" if is_active else "⬜️"
        button_text = f"{emoji} {inbound.get('remark', f'Inbound {inbound_id}')}"
        
        # --- ترفند اصلی ---
        # یک پارامتر اضافی (is_active) به callback_data اضافه می‌کنیم
        # این باعث می‌شود callback_data در هر حالت (فعال/غیرفعال) متفاوت باشد
        callback_data = f"inbound_toggle_{server_id}_{inbound_id}_{1 if is_active else 0}"
        
        markup.add(types.InlineKeyboardButton(button_text, callback_data=callback_data))
        
    markup.add(
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_server_management"),
        types.InlineKeyboardButton("✔️ ثبت تغییرات", callback_data=f"inbound_save_{server_id}")
    )
    return markup

def get_confirmation_menu(confirm_callback: str, cancel_callback: str, confirm_text="✅ بله", cancel_text="❌ خیر"):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(confirm_text, callback_data=confirm_callback),
        types.InlineKeyboardButton(cancel_text, callback_data=cancel_callback)
    )
    return markup

# --- توابع کیبورد کاربر ---

def get_user_main_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛒 خرید سرویس", callback_data="user_buy_service"),
        types.InlineKeyboardButton("🎁 اکانت تست رایگان", callback_data="user_free_test"),
        types.InlineKeyboardButton("🗂️ سرویس‌های من", callback_data="user_my_services"),
        types.InlineKeyboardButton("📞 پشتیبانی", callback_data="user_support")
    )
    return markup
    
def get_back_button(callback_data: str, text: str = "🔙 بازگشت"):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(text, callback_data=callback_data))
    return markup

def get_server_selection_menu(servers: list):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for server in servers:
        markup.add(types.InlineKeyboardButton(server['name'], callback_data=f"buy_select_server_{server['id']}"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="user_main_menu"))
    return markup
    
def get_plan_type_selection_menu_user(server_id: int):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("ماهانه (Fixed)", callback_data="buy_plan_type_fixed_monthly"),
        types.InlineKeyboardButton("حجمی (Gigabyte)", callback_data="buy_plan_type_gigabyte_based")
    )
    markup.add(get_back_button(f"user_buy_service").keyboard[0][0]) # Add back button
    return markup

def get_fixed_plan_selection_menu(plans: list):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for plan in plans:
        button_text = f"{plan['name']} - {plan['volume_gb']:.1f}GB / {plan['duration_days']} روز - {plan['price']:,.0f} تومان"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"buy_select_plan_{plan['id']}"))
    markup.add(get_back_button("user_buy_service").keyboard[0][0]) # Back to server selection
    return markup
    
def get_order_confirmation_menu():
    return get_confirmation_menu(
        confirm_callback="confirm_and_pay",
        cancel_callback="cancel_order",
        confirm_text="✅ تأیید و پرداخت",
        cancel_text="❌ انصراف"
    )

def get_payment_gateway_selection_menu(gateways: list):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for gateway in gateways:
        markup.add(types.InlineKeyboardButton(gateway['name'], callback_data=f"select_gateway_{gateway['id']}"))
    markup.add(get_back_button("show_order_summary", "🔙 بازگشت به خلاصه سفارش").keyboard[0][0])
    return markup
    
def get_admin_payment_action_menu(payment_id: int):
    return get_confirmation_menu(
        confirm_callback=f"admin_approve_payment_{payment_id}",
        cancel_callback=f"admin_reject_payment_{payment_id}",
        confirm_text="✅ تأیید پرداخت",
        cancel_text="❌ رد کردن"
    )
    
def get_single_configs_button(purchase_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("📄 دریافت کانفیگ‌های تکی", callback_data=f"user_get_single_configs_{purchase_id}"))
    return markup

def get_my_services_menu(purchases: list):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for purchase in purchases:
        status = "فعال ✅" if purchase['is_active'] else "غیرفعال ❌"
        btn_text = f"سرویس {purchase['id']} ({purchase['server_name']}) - {status}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"user_service_details_{purchase['id']}"))
    markup.add(get_back_button("user_main_menu").keyboard[0][0])
    return markup



# در فایل keyboards/inline_keyboards.py

def get_my_services_menu(purchases: list):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not purchases:
        markup.add(types.InlineKeyboardButton("شما سرویس فعالی ندارید", callback_data="no_action"))
    else:
        for p in purchases:
            status_emoji = "✅" if p['is_active'] else "❌"
            expire_date_str = p['expire_date'][:10] if p['expire_date'] else "نامحدود"
            btn_text = f"{status_emoji} سرویس {p['id']} ({p['server_name']}) - انقضا: {expire_date_str}"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"user_service_details_{p['id']}"))
    
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو اصلی", callback_data="user_main_menu"))
    return markup



def get_gateway_type_selection_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💳 کارت به کارت", callback_data="gateway_type_card_to_card"),
        types.InlineKeyboardButton("🟢 زرین‌پال", callback_data="gateway_type_zarinpal")
    )
    markup.add(types.InlineKeyboardButton("🔙 انصراف", callback_data="admin_payment_management"))
    return markup