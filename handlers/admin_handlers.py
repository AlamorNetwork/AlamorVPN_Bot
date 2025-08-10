# handlers/admin_handlers.py (نسخه نهایی، کامل و حرفه‌ای)

import telebot
from telebot import types
import logging
import datetime
import json
import os
import zipfile
from config import ADMIN_IDS, SUPPORT_CHANNEL_LINK
from database.db_manager import DatabaseManager
from api_client.xui_api_client import XuiAPIClient
from utils import messages, helpers
from keyboards import inline_keyboards
from utils.config_generator import ConfigGenerator
from utils.bot_helpers import send_subscription_info # این ایمپورت جدید است
from handlers.user_handlers import _user_states
from config import REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_LINK # This should already be there
from api_client.factory import get_api_client
from utils.helpers import normalize_panel_inbounds
from utils.bot_helpers import finalize_profile_purchase
from handlers.domain_handlers import register_domain_handlers # <-- ایمپورت جدید
from utils.system_helpers import remove_domain_nginx_files
from utils.system_helpers import run_shell_command
from utils import helpers
from utils.helpers import update_env_file
from utils.system_helpers import run_shell_command
from .domain_handlers import register_domain_handlers, start_webhook_setup_flow # <-- تابع جدید را اضافه کنید
from utils.helpers import normalize_panel_inbounds, parse_config_link

logger = logging.getLogger(__name__)

# ماژول‌های سراسری
_bot: telebot.TeleBot = None
_db_manager: DatabaseManager = None
_xui_api: XuiAPIClient = None
_config_generator: ConfigGenerator = None
_admin_states = {}

def register_admin_handlers(bot_instance, db_manager_instance, xui_api_instance):
    global _bot, _db_manager, _xui_api, _config_generator , _admin_states
    _bot = bot_instance
    _db_manager = db_manager_instance
    _xui_api = xui_api_instance
    _config_generator = ConfigGenerator(db_manager_instance)

    # =============================================================================
    # SECTION: Helper and Menu Functions
    # =============================================================================
    register_domain_handlers(bot=_bot, db_manager=_db_manager, admin_states=_admin_states)


    def _clear_admin_state(admin_id):
        """وضعیت ادمین را فقط از دیکشنری پاک می‌کند."""
        if admin_id in _admin_states:
            del _admin_states[admin_id]

    def _show_menu(user_id, text, markup, message=None, parse_mode='Markdown'):
        """
        --- FINAL & ROBUST VERSION ---
        This function intelligently handles Markdown parsing errors.
        It first tries to send the message with Markdown. If Telegram rejects it
        due to a formatting error, it automatically retries sending it as plain text.
        """
        try:
            # First attempt: Send with specified parse_mode (usually Markdown)
            if message:
                return _bot.edit_message_text(text, user_id, message.message_id, reply_markup=markup, parse_mode=parse_mode)
            else:
                return _bot.send_message(user_id, text, reply_markup=markup, parse_mode=parse_mode)

        except telebot.apihelper.ApiTelegramException as e:
            # If the error is specifically a Markdown parsing error...
            if "can't parse entities" in str(e):
                logger.warning(f"Markdown parse error for user {user_id}. Retrying with plain text.")
                try:
                    # Second attempt: Send as plain text
                    if message:
                        return _bot.edit_message_text(text, user_id, message.message_id, reply_markup=markup, parse_mode=None)
                    else:
                        return _bot.send_message(user_id, text, reply_markup=markup, parse_mode=None)
                except telebot.apihelper.ApiTelegramException as retry_e:
                    logger.error(f"Failed to send menu even as plain text for user {user_id}: {retry_e}")

            # Handle other common errors
            elif 'message to edit not found' in str(e):
                return _bot.send_message(user_id, text, reply_markup=markup, parse_mode=parse_mode)
            elif 'message is not modified' not in str(e):
                logger.warning(f"Menu error for {user_id}: {e}")
                
        return message

    def _show_admin_main_menu(admin_id, message=None): _show_menu(admin_id, messages.ADMIN_WELCOME, inline_keyboards.get_admin_main_inline_menu(), message)
    def _show_server_management_menu(admin_id, message=None): _show_menu(admin_id, messages.SERVER_MGMT_MENU_TEXT, inline_keyboards.get_server_management_inline_menu(), message)
    def _show_plan_management_menu(admin_id, message=None): _show_menu(admin_id, messages.PLAN_MGMT_MENU_TEXT, inline_keyboards.get_plan_management_inline_menu(), message)
    def _show_payment_gateway_management_menu(admin_id, message=None): _show_menu(admin_id, messages.PAYMENT_GATEWAY_MGMT_MENU_TEXT, inline_keyboards.get_payment_gateway_management_inline_menu(), message)
    def _show_user_management_menu(admin_id, message=None): _show_menu(admin_id, messages.USER_MGMT_MENU_TEXT, inline_keyboards.get_user_management_inline_menu(), message)
    def _show_profile_management_menu(admin_id, message=None):
        _show_menu(admin_id, "🗂️ گزینه‌های مدیریت پروفایل:", inline_keyboards.get_profile_management_inline_menu(), message)

    # =============================================================================
    # SECTION: Single-Action Functions (Listing, Testing)
    # =============================================================================

    def list_all_servers(admin_id, message):
        _bot.edit_message_text(_generate_server_list_text(), admin_id, message.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_server_management"))

    # در فایل handlers/admin_handlers.py

    def list_all_plans(admin_id, message, return_text=False):
        plans = _db_manager.get_all_plans()
        if not plans: 
            text = messages.NO_PLANS_FOUND
        else:
            text = messages.LIST_PLANS_HEADER
            for p in plans:
                status = "✅ فعال" if p['is_active'] else "❌ غیرفعال"
                if p['plan_type'] == 'fixed_monthly':
                    details = f"حجم: {p['volume_gb']}GB | مدت: {p['duration_days']} روز | قیمت: {p['price']:,.0f} تومان"
                else:
                    # --- بخش اصلاح شده ---
                    duration_days = p.get('duration_days') # مقدار ممکن است None باشد
                    if duration_days and duration_days > 0:
                        duration_text = f"{duration_days} روز"
                    else:
                        duration_text = "نامحدود"
                    # --- پایان بخش اصلاح شده ---
                    details = f"قیمت هر گیگ: {p['per_gb_price']:,.0f} تومان | مدت: {duration_text}"
                text += f"**ID: `{p['id']}`** - {helpers.escape_markdown_v1(p['name'])}\n_({details})_ - {status}\n---\n"
        
        if return_text:
            return text
        _bot.edit_message_text(text, admin_id, message.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_plan_management"))
    def list_all_gateways(admin_id, message, return_text=False):
        gateways = _db_manager.get_all_payment_gateways()
        if not gateways:
            text = messages.NO_GATEWAYS_FOUND
        else:
            text = messages.LIST_GATEWAYS_HEADER
            for g in gateways:
                status = "✅ فعال" if g['is_active'] else "❌ غیرفعال"
                text += f"**ID: `{g['id']}`** - {helpers.escape_markdown_v1(g['name'])}\n`{g.get('card_number', 'N/A')}` - {status}\n---\n"
        
        if return_text:
            return text
        _bot.edit_message_text(text, admin_id, message.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_payment_management"))


    def list_all_users(admin_id, message):
        users = _db_manager.get_all_users()
        if not users:
            text = messages.NO_USERS_FOUND
        else:
            text = messages.LIST_USERS_HEADER
            for user in users:
                # --- بخش اصلاح شده ---
                # نام کاربری نیز escape می‌شود تا از خطا جلوگیری شود
                username = helpers.escape_markdown_v1(user.get('username', 'N/A'))
                first_name = helpers.escape_markdown_v1(user.get('first_name', ''))
                text += f"👤 `ID: {user['id']}` - **{first_name}** (@{username})\n"
                # --- پایان بخش اصلاح شده ---
        
        _show_menu(admin_id, text, inline_keyboards.get_back_button("admin_user_management"), message)

    def test_all_servers(admin_id, message):
        _bot.edit_message_text(messages.TESTING_ALL_SERVERS, admin_id, message.message_id, reply_markup=None)
        servers = _db_manager.get_all_servers(only_active=False) # همه سرورها را تست می‌کنیم
        if not servers:
            _bot.send_message(admin_id, messages.NO_SERVERS_FOUND)
            _show_server_management_menu(admin_id)
            return
            
        results = []
        for s in servers:
            # --- اصلاح اصلی اینجاست ---
            # استفاده از factory برای انتخاب کلاینت مناسب
            api_client = get_api_client(s)
            is_online = False
            if api_client:
                # تابع check_login لاگین را نیز انجام می‌دهد
                is_online = api_client.check_login()
            # --- پایان بخش اصلاح شده ---

            _db_manager.update_server_status(s['id'], is_online, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            status_emoji = "✅" if is_online else "❌"
            results.append(f"{status_emoji} {helpers.escape_markdown_v1(s['name'])} (Type: {s['panel_type']})")

        _bot.send_message(admin_id, messages.TEST_RESULTS_HEADER + "\n".join(results), parse_mode='Markdown')
        _show_server_management_menu(admin_id)
    # =============================================================================
    # SECTION: Stateful Process Handlers
    # =============================================================================
    def get_plan_details_from_callback(admin_id, message, plan_type):
        """نوع پلن انتخاب شده را پردازش کرده و سوال بعدی را می‌پرسد."""
        state_info = _admin_states.get(admin_id, {})
        if state_info.get('state') != 'waiting_for_plan_type': return

        state_info['data']['plan_type'] = plan_type
        
        if plan_type == 'fixed_monthly':
            # برای پلن ثابت، سوال بعدی حجم است
            state_info['state'] = 'waiting_for_plan_volume'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_VOLUME, admin_id, message.message_id)
        elif plan_type == 'gigabyte_based':
            # برای پلن حجمی، سوال بعدی قیمت هر گیگ است
            state_info['state'] = 'waiting_for_per_gb_price'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_PER_GB_PRICE, admin_id, message.message_id)
        
        state_info['prompt_message_id'] = message.message_id
    def _handle_stateful_message(admin_id, message):
        state_info = _admin_states.get(admin_id, {})
        state = state_info.get("state")
        prompt_id = state_info.get("prompt_message_id")
        data = state_info.get("data", {})
        text = message.text.strip()

        # --- منطق جدید برای دریافت کانفیگ نمونه ---
        if state == 'waiting_for_sample_config':
            process_sample_config_input(admin_id, message)
            return

        # --- Server Flows ---
        if state == 'waiting_for_server_name':
            data['name'] = text
            state_info['state'] = 'waiting_for_panel_type_selection'
            prompt_text = "لطفاً نوع پنل سرور جدید را انتخاب کنید:"
            _bot.edit_message_text(prompt_text, admin_id, prompt_id, reply_markup=inline_keyboards.get_panel_type_selection_menu())
            return

        elif state == 'waiting_for_server_url':
            data['url'] = text
            state_info['state'] = 'waiting_for_server_username'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_USERNAME, admin_id, prompt_id)
        elif state == 'waiting_for_server_username':
            data['username'] = text
            state_info['state'] = 'waiting_for_server_password'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_PASSWORD, admin_id, prompt_id)
        elif state == 'waiting_for_server_password':
            data['password'] = text
            state_info['state'] = 'waiting_for_sub_base_url'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_SUB_BASE_URL, admin_id, prompt_id)
        elif state == 'waiting_for_sub_base_url':
            data['sub_base_url'] = text
            state_info['state'] = 'waiting_for_sub_path_prefix'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_SUB_PATH_PREFIX, admin_id, prompt_id)
        elif state == 'waiting_for_sub_path_prefix':
            data['sub_path_prefix'] = text
            execute_add_server(admin_id, data)
        elif state == 'waiting_for_server_id_to_delete':
            process_delete_server_id(admin_id, message)

        # --- Plan Flows ---
        elif state == 'waiting_for_plan_name':
            data['name'] = text
            state_info['state'] = 'waiting_for_plan_type'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_TYPE, admin_id, prompt_id, reply_markup=inline_keyboards.get_plan_type_selection_menu_admin())
        elif state == 'waiting_for_plan_volume':
            if not helpers.is_float_or_int(text) or float(text) <= 0:
                _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_VOLUME}", admin_id, prompt_id); return
            data['volume_gb'] = float(text)
            state_info['state'] = 'waiting_for_plan_duration'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_DURATION, admin_id, prompt_id)
        elif state == 'waiting_for_plan_duration':
            if not text.isdigit() or int(text) < 0:
                _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_DURATION}", admin_id, prompt_id); return
            data['duration_days'] = int(text)
            state_info['state'] = 'waiting_for_plan_price'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_PRICE, admin_id, prompt_id)
        elif state == 'waiting_for_plan_price':
            if not helpers.is_float_or_int(text) or float(text) < 0:
                _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_PRICE}", admin_id, prompt_id); return
            data['price'] = float(text)
            execute_add_plan(admin_id, data)
        elif state == 'waiting_for_per_gb_price':
            if not helpers.is_float_or_int(text) or float(text) <= 0:
                _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_PER_GB_PRICE}", admin_id, prompt_id); return
            data['per_gb_price'] = float(text)
            state_info['state'] = 'waiting_for_gb_plan_duration'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_DURATION_GB, admin_id, prompt_id)
        elif state == 'waiting_for_gb_plan_duration':
            if not text.isdigit() or int(text) < 0:
                _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_DURATION_GB}", admin_id, prompt_id); return
            data['duration_days'] = int(text)
            execute_add_plan(admin_id, data)
        elif state == 'waiting_for_plan_id_to_toggle':
            execute_toggle_plan_status(admin_id, text)
        elif state == 'waiting_for_plan_id_to_delete':
            process_delete_plan_id(admin_id, message)
        elif state == 'waiting_for_plan_id_to_edit':
            process_edit_plan_id(admin_id, message)
        elif state == 'waiting_for_new_plan_name':
            process_edit_plan_name(admin_id, message)
        elif state == 'waiting_for_new_plan_price':
            process_edit_plan_price(admin_id, message)

        # --- Profile Flows ---
        elif state == 'waiting_for_profile_name':
            data['name'] = text
            state_info['state'] = 'waiting_for_profile_per_gb_price'
            _bot.edit_message_text(messages.ADD_PROFILE_PROMPT_PER_GB_PRICE, admin_id, prompt_id)
        elif state == 'waiting_for_profile_per_gb_price':
            if not helpers.is_float_or_int(text) or float(text) <= 0:
                _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PROFILE_PROMPT_PER_GB_PRICE}", admin_id, prompt_id); return
            data['per_gb_price'] = float(text)
            state_info['state'] = 'waiting_for_profile_duration'
            _bot.edit_message_text(messages.ADD_PROFILE_PROMPT_DURATION, admin_id, prompt_id)
        elif state == 'waiting_for_profile_duration':
            if not text.isdigit() or int(text) <= 0:
                _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PROFILE_PROMPT_DURATION}", admin_id, prompt_id); return
            data['duration_days'] = int(text)
            state_info['state'] = 'waiting_for_profile_description'
            _bot.edit_message_text(messages.ADD_PROFILE_PROMPT_DESCRIPTION, admin_id, prompt_id)
        elif state == 'waiting_for_profile_description':
            data['description'] = None if text.lower() == 'skip' else text
            execute_add_profile(admin_id, data)

        # --- Gateway Flows ---
        elif state == 'waiting_for_gateway_name':
            data['name'] = text
            state_info['state'] = 'waiting_for_gateway_type'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_TYPE, admin_id, prompt_id, reply_markup=inline_keyboards.get_gateway_type_selection_menu())
        elif state == 'waiting_for_merchant_id':
            data['merchant_id'] = text
            state_info['state'] = 'waiting_for_gateway_description'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_DESCRIPTION, admin_id, prompt_id)
        elif state == 'waiting_for_card_number':
            if not text.isdigit() or len(text) != 16:
                _bot.edit_message_text(f"شماره کارت نامعتبر است.\n\n{messages.ADD_GATEWAY_PROMPT_CARD_NUMBER}", admin_id, prompt_id); return
            data['card_number'] = text
            state_info['state'] = 'waiting_for_card_holder_name'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_CARD_HOLDER_NAME, admin_id, prompt_id)
        elif state == 'waiting_for_card_holder_name':
            data['card_holder_name'] = text
            state_info['state'] = 'waiting_for_gateway_description'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_DESCRIPTION, admin_id, prompt_id)
        elif state == 'waiting_for_gateway_description':
            data['description'] = None if text.lower() == 'skip' else text
            execute_add_gateway(admin_id, data)
        elif state == 'waiting_for_gateway_id_to_toggle':
            execute_toggle_gateway_status(admin_id, text)
            
        # --- Admin Management Flows ---
        elif state == 'waiting_for_admin_id_to_add':
            if not text.isdigit():
                _bot.send_message(admin_id, "آیدی نامعتبر است. لطفاً یک عدد وارد کنید.")
                return
            target_user_id = int(text)
            if _db_manager.set_user_admin_status(target_user_id, True):
                _bot.send_message(admin_id, f"✅ کاربر با آیدی `{target_user_id}` با موفقیت به لیست ادمین‌ها اضافه شد.")
            else:
                _bot.send_message(admin_id, "❌ کاربر یافت نشد یا در افزودن ادمین خطایی رخ داد.")
            _clear_admin_state(admin_id)
            _show_admin_management_menu(admin_id, message)

        elif state == 'waiting_for_admin_id_to_remove':
            if not text.isdigit():
                _bot.send_message(admin_id, "آیدی نامعتبر است. لطفاً یک عدد وارد کنید.")
                return
            target_user_id = int(text)
            if target_user_id == admin_id:
                _bot.send_message(admin_id, "❌ شما نمی‌توانید خودتان را از لیست ادمین‌ها حذف کنید.")
                return
            if _db_manager.set_user_admin_status(target_user_id, False):
                _bot.send_message(admin_id, f"✅ کاربر با آیدی `{target_user_id}` با موفقیت از لیست ادمین‌ها حذف شد.")
            else:
                _bot.send_message(admin_id, "❌ کاربر یافت نشد یا در حذف ادمین خطایی رخ داد.")
            _clear_admin_state(admin_id)
            _show_admin_management_menu(admin_id, message)
        # --- Branding Settings Flows ---
        elif state == 'waiting_for_brand_name':
            new_brand_name = message.text.strip()
            # یک اعتبارسنجی ساده برای اطمینان از اینکه نام مناسب است
            if not new_brand_name.isalnum():
                _bot.send_message(admin_id, "نام برند نامعتبر است. لطفاً فقط از حروف و اعداد انگلیسی بدون فاصله استفاده کنید.")
                return
            
            _db_manager.update_setting('brand_name', new_brand_name)
            _bot.edit_message_text(f"✅ نام برند با موفقیت به **{new_brand_name}** تغییر کرد.", admin_id, state_info['prompt_message_id'])
            _clear_admin_state(admin_id)
            # نمایش مجدد منو با نام جدید
            show_branding_settings_menu(admin_id, message)
        # --- Other Flows ---
        elif state == 'waiting_for_server_id_for_inbounds':
            process_manage_inbounds_flow(admin_id, message)
        elif state == 'waiting_for_tutorial_platform':
            process_tutorial_platform(admin_id, message)
        elif state == 'waiting_for_tutorial_app_name':
            process_tutorial_app_name(admin_id, message)
        elif state == 'waiting_for_tutorial_forward':
            process_tutorial_forward(admin_id, message)
        elif state == 'waiting_for_user_id_to_search':
            process_user_search(admin_id, message)
        elif state == 'waiting_for_channel_id':
            process_set_channel_id(admin_id, message)
        elif state == 'waiting_for_channel_link':
            process_set_channel_link(admin_id, message)
        elif state == 'waiting_for_support_link':
            process_support_link(admin_id, message)
    # =============================================================================
    # SECTION: Process Starters and Callback Handlers
    # =============================================================================
    def start_add_server_flow(admin_id, message):
        """فرآیند افزودن سرور را با پرسیدن نوع پنل شروع می‌کند."""
        _clear_admin_state(admin_id) # پاک کردن وضعیت قبلی
        prompt = _show_menu(admin_id, "لطفاً نوع پنل سرور جدید را انتخاب کنید:", inline_keyboards.get_panel_type_selection_menu(), message)
        # The next step is handled by the callback handler below


    def start_delete_server_flow(admin_id, message):
        _clear_admin_state(admin_id)
        list_text = _generate_server_list_text()
        if list_text == messages.NO_SERVERS_FOUND:
            _bot.edit_message_text(list_text, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management")); return
        _admin_states[admin_id] = {'state': 'waiting_for_server_id_to_delete', 'prompt_message_id': message.message_id}
        prompt_text = f"{list_text}\n\n{messages.DELETE_SERVER_PROMPT}"
        _bot.edit_message_text(prompt_text, admin_id, message.message_id, parse_mode='Markdown')

    def start_add_plan_flow(admin_id, message):
        """فرآیند افزودن یک پلن جدید سراسری را شروع می‌کند."""
        _clear_admin_state(admin_id)
        # در ابتدا نام پلن را می‌پرسیم
        prompt = _show_menu(admin_id, messages.ADD_PLAN_PROMPT_NAME, inline_keyboards.get_back_button("admin_plan_management"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_plan_name', 'data': {}, 'prompt_message_id': prompt.message_id}
    def start_toggle_plan_status_flow(admin_id, message):
        _clear_admin_state(admin_id)
        # --- بخش اصلاح شده ---
        # اکنون پارامترهای لازم به تابع پاس داده می‌شوند
        plans_text = list_all_plans(admin_id, message, return_text=True)
        _bot.edit_message_text(f"{plans_text}\n\n{messages.TOGGLE_PLAN_STATUS_PROMPT}", admin_id, message.message_id, parse_mode='Markdown')
        _admin_states[admin_id] = {'state': 'waiting_for_plan_id_to_toggle', 'prompt_message_id': message.message_id}
        
    def start_add_gateway_flow(admin_id, message):
        _clear_admin_state(admin_id)
        _admin_states[admin_id] = {'state': 'waiting_for_gateway_name', 'data': {}, 'prompt_message_id': message.message_id}
        _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_NAME, admin_id, message.message_id)
        
    def start_toggle_gateway_status_flow(admin_id, message):
        _clear_admin_state(admin_id)
        # --- بخش اصلاح شده ---
        # اکنون پارامترهای لازم به تابع پاس داده می‌شوند
        gateways_text = list_all_gateways(admin_id, message, return_text=True)
        _bot.edit_message_text(f"{gateways_text}\n\n{messages.TOGGLE_GATEWAY_STATUS_PROMPT}", admin_id, message.message_id, parse_mode='Markdown')
        _admin_states[admin_id] = {'state': 'waiting_for_gateway_id_to_toggle', 'prompt_message_id': message.message_id}



    # =============================================================================
    # SECTION: Main Bot Handlers
    # =============================================================================

    @_bot.message_handler(commands=['admin'])
    def handle_admin_command(message):
        if not helpers.is_admin(message.from_user.id):
            _bot.reply_to(message, messages.NOT_ADMIN_ACCESS); return
        try: _bot.delete_message(message.chat.id, message.message_id)
        except Exception: pass
        _clear_admin_state(message.from_user.id)
        _show_admin_main_menu(message.from_user.id)
    
    @_bot.callback_query_handler(func=lambda call: helpers.is_admin(call.from_user.id))
    def handle_admin_callbacks(call):
        """این هندلر تمام کلیک‌های ادمین را به صورت یکپارچه مدیریت می‌کند."""
        _bot.answer_callback_query(call.id)
        admin_id, message, data = call.from_user.id, call.message, call.data
        state_info = _admin_states.get(admin_id, {})

        actions = {
            "admin_main_menu": lambda a_id, msg: (_clear_admin_state(a_id), _show_admin_main_menu(a_id, msg)),
            "admin_server_management": _show_server_management_menu,
            "admin_plan_management": lambda a_id, msg: (_clear_admin_state(a_id), _show_plan_management_menu(a_id, msg)),
            "admin_profile_management": _show_profile_management_menu,
            "admin_payment_management": _show_payment_gateway_management_menu,
            "admin_user_management": _show_user_management_menu,
            "admin_add_server": start_add_server_flow,
            "admin_list_servers": list_all_servers,
            "admin_delete_server": start_delete_server_flow,
            "admin_test_all_servers": test_all_servers,
            "admin_manage_inbounds": start_manage_inbounds_flow,
            "admin_add_plan": start_add_plan_flow,
            "admin_list_plans": list_all_plans,
            "admin_delete_plan": start_delete_plan_flow,
            "admin_edit_plan": start_edit_plan_flow,
            "admin_toggle_plan_status": start_toggle_plan_status_flow,
            "admin_add_gateway": start_add_gateway_flow,
            "admin_list_gateways": list_all_gateways,
            "admin_toggle_gateway_status": start_toggle_gateway_status_flow,
            "admin_list_users": list_all_users,
            "admin_search_user": start_search_user_flow,
            "admin_channel_lock_management": show_channel_lock_menu,
            "admin_set_channel_lock": start_set_channel_lock_flow,
            "admin_remove_channel_lock": execute_remove_channel_lock,
            "admin_tutorial_management": show_tutorial_management_menu,
            "admin_add_tutorial": start_add_tutorial_flow,
            "admin_list_tutorials": list_tutorials,
            "admin_support_management": show_support_management_menu,
            "admin_edit_support_link": start_edit_support_link_flow,
            "admin_add_profile": start_add_profile_flow,
            "admin_list_profiles": list_all_profiles,
            "admin_manage_profile_inbounds": start_manage_profile_inbounds_flow,
            "admin_manage_admins": _show_admin_management_menu,
            "admin_add_admin": start_add_admin_flow,
            "admin_remove_admin": start_remove_admin_flow,
            "admin_check_nginx": check_nginx_status,
            "admin_health_check": run_system_health_check,
            "admin_webhook_setup": start_webhook_setup_flow,
            "admin_create_backup": create_backup,
        }

        if data in actions:
            actions[data](admin_id, message)
            return

        # --- مدیریت الگوهای سرور ---
        if data == "admin_manage_templates":
            show_template_management_menu(admin_id, message)
            return
        elif data.startswith("admin_edit_template_"):
            parts = data.split('_')
            server_id = int(parts[3])
            inbound_id = int(parts[4])
            server_data = _db_manager.get_server_by_id(server_id)
            inbound_info_db = _db_manager.get_server_inbound_details(server_id, inbound_id)
            inbound_info = {'id': inbound_id, 'remark': inbound_info_db.get('remark', '') if inbound_info_db else ''}
            context = {'type': 'server', 'server_id': server_id, 'server_name': server_data['name']}
            start_sample_config_flow(admin_id, message, [inbound_info], context)
            return
        # --- مدیریت برندینگ ---
        elif data == "admin_branding_settings":
            show_branding_settings_menu(admin_id, message)
            return
        # --- مدیریت پیام ها ---
        elif data == "admin_message_management":
            show_message_management_menu(admin_id, message)
            return
        elif data == "admin_change_brand_name":
            start_change_brand_name_flow(admin_id, message)
            return
        # --- مدیریت الگوهای پروفایل ---
        elif data == "admin_manage_profile_templates":
            show_profile_template_management_menu(admin_id, message)
            return
        elif data.startswith("admin_edit_profile_template_"):
            parts = data.split('_')
            profile_id, server_id, inbound_id = int(parts[4]), int(parts[5]), int(parts[6])
            server_data = _db_manager.get_server_by_id(server_id)
            profile_data = _db_manager.get_profile_by_id(profile_id)
            inbound_info_db = _db_manager.get_server_inbound_details(server_id, inbound_id)
            inbound_info = {'id': inbound_id, 'remark': inbound_info_db.get('remark', '') if inbound_info_db else ''}
            context = {
                'type': 'profile', 'profile_id': profile_id, 'profile_name': profile_data['name'],
                'server_id': server_id, 'server_name': server_data['name']
            }
            start_sample_config_flow(admin_id, message, [inbound_info], context)
            return
        elif data == "admin_view_profile_db":
            show_profile_inbounds_db_status(admin_id, message)
            return
        # --- مدیریت پرداخت‌ها ---
        elif data.startswith("admin_approve_payment_"):
            process_payment_approval(admin_id, int(data.split('_')[-1]), message)
            return
        elif data.startswith("admin_reject_payment_"):
            process_payment_rejection(admin_id, int(data.split('_')[-1]), message)
            return

        # --- مدیریت اینباندها (ذخیره و تایید) ---
        elif data.startswith("inbound_save_"):
            server_id = int(data.split('_')[-1])
            execute_save_inbounds(admin_id, message, server_id)
            return
        elif data.startswith("admin_pi_save_"):
            parts = data.split('_')
            profile_id, server_id = int(parts[3]), int(parts[4])
            execute_save_profile_inbounds(admin_id, message, profile_id, server_id)
            return

        # --- مدیریت انتخاب اینباندها (تیک زدن) ---
        elif data.startswith("inbound_toggle_"):
            handle_inbound_selection(admin_id, call)
            return
        elif data.startswith("admin_pi_toggle_"):
            parts = data.split('_')
            profile_id, server_id, inbound_id = int(parts[3]), int(parts[4]), int(parts[5])
            handle_profile_inbound_toggle(admin_id, message, profile_id, server_id, inbound_id)
            return
        
        # --- مدیریت انتخاب پروفایل و سرور برای پروفایل ---
        elif data.startswith("admin_select_profile_"):
            profile_id = int(data.split('_')[-1])
            handle_profile_selection(admin_id, message, profile_id)
            return
        elif data.startswith("admin_ps_"): # Profile Server Selection
            parts = data.split('_')
            profile_id, server_id = int(parts[2]), int(parts[3])
            handle_server_selection_for_profile(admin_id, message, profile_id, server_id)
            return

        # --- مدیریت حذف‌ها با تاییدیه ---
        elif data.startswith("confirm_delete_server_"):
            execute_delete_server(admin_id, message, int(data.split('_')[-1]))
            return
        elif data.startswith("confirm_delete_plan_"):
            execute_delete_plan(admin_id, message, int(data.split('_')[-1]))
            return
        elif data.startswith("admin_delete_purchase_"):
            parts = data.split('_')
            purchase_id, user_telegram_id = int(parts[3]), int(parts[4])
            execute_delete_purchase(admin_id, message, purchase_id, user_telegram_id)
            return
        elif data.startswith("admin_delete_tutorial_"):
            execute_delete_tutorial(admin_id, message, int(data.split('_')[-1]))
            return
        elif data.startswith("confirm_delete_domain_"):
            execute_delete_domain(admin_id, message, int(data.split('_')[-1]))
            return

        # --- مدیریت انتخاب نوع پلن و درگاه ---
        elif data.startswith("plan_type_"):
            get_plan_details_from_callback(admin_id, message, data.replace("plan_type_", ""))
            return
        elif data.startswith("gateway_type_"):
            handle_gateway_type_selection(admin_id, message, data.replace('gateway_type_', ''))
            return
        elif data.startswith("panel_type_"):
            handle_panel_type_selection(call)
            return

        # اگر هیچکدام از موارد بالا نبود
        else:
            _bot.edit_message_text(messages.UNDER_CONSTRUCTION, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_main_menu"))
    @_bot.message_handler(
    content_types=['text'],
    func=lambda msg: helpers.is_admin(msg.from_user.id) and _admin_states.get(msg.from_user.id, {}).get('state')
            )
    def handle_admin_stateful_messages(message):
        admin_id = message.from_user.id
    
        # حذف پیام ورودی ادمین برای تمیز ماندن چت
        try:
            if message.content_type == 'text':
                _bot.delete_message(admin_id, message.message_id)
        except Exception:
            pass

        # فراخوانی تابع اصلی که منطق را پردازش می‌کند
        _handle_stateful_message(admin_id, message)
        
        


    # =============================================================================
# SECTION: Final Execution Functions
# =============================================================================

    def execute_add_server(admin_id, data):
        _clear_admin_state(admin_id)
        msg = _bot.send_message(admin_id, messages.ADD_SERVER_TESTING)
        temp_xui_client = _xui_api(panel_url=data['url'], username=data['username'], password=data['password'])
        if temp_xui_client.login():
            server_id = _db_manager.add_server(data['name'], data['url'], data['username'], data['password'], data['sub_base_url'], data['sub_path_prefix'])
            if server_id:
                _db_manager.update_server_status(server_id, True, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                _bot.edit_message_text(messages.ADD_SERVER_SUCCESS.format(server_name=data['name']), admin_id, msg.message_id)
            else:
                _bot.edit_message_text(messages.ADD_SERVER_DB_ERROR.format(server_name=data['name']), admin_id, msg.message_id)
        else:
            _bot.edit_message_text(messages.ADD_SERVER_LOGIN_FAILED.format(server_name=data['name']), admin_id, msg.message_id)
        _show_server_management_menu(admin_id)

    def execute_delete_server(admin_id, message, server_id):
        # پاک کردن وضعیت در ابتدای اجرای عملیات نهایی
        _clear_admin_state(admin_id)
        
        server = _db_manager.get_server_by_id(server_id)
        if server and _db_manager.delete_server(server_id):
            _bot.edit_message_text(messages.SERVER_DELETED_SUCCESS.format(server_name=server['name']), admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
        else:
            _bot.edit_message_text(messages.SERVER_DELETED_ERROR, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))

    def execute_add_plan(admin_id, data):
        _clear_admin_state(admin_id)
        plan_id = _db_manager.add_plan(
            name=data.get('name'), plan_type=data.get('plan_type'),
            volume_gb=data.get('volume_gb'), duration_days=data.get('duration_days'),
            price=data.get('price'), per_gb_price=data.get('per_gb_price')
        )
        msg_to_send = messages.ADD_PLAN_SUCCESS if plan_id else messages.ADD_PLAN_DB_ERROR
        _bot.send_message(admin_id, msg_to_send.format(plan_name=data['name']))
        _show_plan_management_menu(admin_id)
        
    def execute_add_gateway(admin_id, data):
        _clear_admin_state(admin_id)
        gateway_id = _db_manager.add_payment_gateway(
            name=data.get('name'),
            gateway_type=data.get('gateway_type'),  # <-- اصلاح شد
            card_number=data.get('card_number'),
            card_holder_name=data.get('card_holder_name'),
            merchant_id=data.get('merchant_id'),    # <-- اضافه شد
            description=data.get('description'),
            priority=0
        )
        
        msg_to_send = messages.ADD_GATEWAY_SUCCESS if gateway_id else messages.ADD_GATEWAY_DB_ERROR
        _bot.send_message(admin_id, msg_to_send.format(gateway_name=data['name']))
        _show_payment_gateway_management_menu(admin_id)

    def execute_toggle_plan_status(admin_id, plan_id_str: str): # ورودی به text تغییر کرد
        _clear_admin_state(admin_id)
        if not plan_id_str.isdigit() or not (plan := _db_manager.get_plan_by_id(int(plan_id_str))):
            _bot.send_message(admin_id, messages.PLAN_NOT_FOUND)
            _show_plan_management_menu(admin_id)
            return
        new_status = not plan['is_active']
        if _db_manager.update_plan_status(plan['id'], new_status):
            _bot.send_message(admin_id, messages.PLAN_STATUS_TOGGLED_SUCCESS.format(plan_name=plan['name'], new_status="فعال" if new_status else "غیرفعال"))
        else:
            _bot.send_message(admin_id, messages.PLAN_STATUS_TOGGLED_ERROR.format(plan_name=plan['name']))
        _show_plan_management_menu(admin_id)
        
    def execute_toggle_gateway_status(admin_id, gateway_id_str: str): # ورودی به text تغییر کرد
        _clear_admin_state(admin_id)
        if not gateway_id_str.isdigit() or not (gateway := _db_manager.get_payment_gateway_by_id(int(gateway_id_str))):
            _bot.send_message(admin_id, messages.GATEWAY_NOT_FOUND)
            _show_payment_gateway_management_menu(admin_id)
            return
        new_status = not gateway['is_active']
        if _db_manager.update_payment_gateway_status(gateway['id'], new_status):
            _bot.send_message(admin_id, messages.GATEWAY_STATUS_TOGGLED_SUCCESS.format(gateway_name=gateway['name'], new_status="فعال" if new_status else "غیرفعال"))
        else:
            _bot.send_message(admin_id, messages.GATEWAY_STATUS_TOGGLED_ERROR.format(gateway_name=gateway['name']))
        _show_payment_gateway_management_menu(admin_id)
        # =============================================================================
    # SECTION: Process-Specific Helper Functions
    # =============================================================================

    def _generate_server_list_text():
        servers = _db_manager.get_all_servers()
        if not servers: return messages.NO_SERVERS_FOUND
        response_text = messages.LIST_SERVERS_HEADER
        for s in servers:
            status = "✅ آنلاین" if s['is_online'] else "❌ آفلاین"
            is_active_emoji = "✅" if s['is_active'] else "❌"
            sub_link = f"{s['subscription_base_url'].rstrip('/')}/{s['subscription_path_prefix'].strip('/')}/<SUB_ID>"
            response_text += messages.SERVER_DETAIL_TEMPLATE.format(
                name=helpers.escape_markdown_v1(s['name']), id=s['id'], status=status, is_active_emoji=is_active_emoji, sub_link=helpers.escape_markdown_v1(sub_link)
            )
        return response_text

    
    def handle_inbound_selection(admin_id, call):
        """کلیک روی دکمه‌های کیبورد انتخاب اینباند را به درستی مدیریت می‌کند."""
        data = call.data
        parts = data.split('_')
        action = parts[1]

        state_info = _admin_states.get(admin_id)
        if not state_info: return

        server_id = None
        
        # استخراج server_id بر اساس نوع اکشن
        if action == 'toggle':
            # فرمت: inbound_toggle_{server_id}_{inbound_id}
            if len(parts) == 4:
                server_id = int(parts[2])
        else: # برای select, deselect, save
            # فرمت: inbound_select_all_{server_id}
            server_id = int(parts[-1])

        if server_id is None or state_info.get('state') != f'selecting_inbounds_for_{server_id}':
            return

        # دریافت اطلاعات لازم از state
        selected_ids = state_info['data'].get('selected_inbound_ids', [])
        panel_inbounds = state_info['data'].get('panel_inbounds', [])

        # انجام عملیات بر اساس اکشن
        if action == 'toggle':
            inbound_id_to_toggle = int(parts[3])
            if inbound_id_to_toggle in selected_ids:
                selected_ids.remove(inbound_id_to_toggle)
            else:
                selected_ids.append(inbound_id_to_toggle)
        
        elif action == 'select' and parts[2] == 'all':
            panel_ids = {p['id'] for p in panel_inbounds}
            selected_ids.extend([pid for pid in panel_ids if pid not in selected_ids])
            selected_ids = list(set(selected_ids)) # حذف موارد تکراری
        
        elif action == 'deselect' and parts[2] == 'all':
            selected_ids.clear()
            
        elif action == 'save':
            save_inbound_changes(admin_id, call.message, server_id, selected_ids)
            return
        
        # به‌روزرسانی state و کیبورد
        state_info['data']['selected_inbound_ids'] = selected_ids
        markup = inline_keyboards.get_inbound_selection_menu(server_id, panel_inbounds, selected_ids)
        
        try:
            _bot.edit_message_reply_markup(chat_id=admin_id, message_id=call.message.message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is not modified' not in e.description:
                logger.warning(f"Error updating inbound selection keyboard: {e}")

    def process_payment_approval(admin_id, payment_id, message):
        """
        پرداخت دستی را تایید کرده و بر اساس نوع خرید (عادی یا پروفایل)،
        فرآیند تحویل سرویس را آغاز می‌کند. (نسخه نهایی)
        """
        payment = _db_manager.get_payment_by_id(payment_id)
        
        if not payment or payment['is_confirmed']:
            try:
                # message.id در اینجا شناسه پیام است، نه کلیک. برای سادگی خطا را نادیده می‌گیریم.
                _bot.answer_callback_query(message.id, "این پرداخت قبلاً پردازش شده است.", show_alert=True)
            except Exception:
                pass
            return

        order_details = json.loads(payment['order_details_json'])
        user_telegram_id = order_details['user_telegram_id']
        user_db_id = order_details['user_db_id']
        # به‌روزرسانی وضعیت پرداخت در دیتابیس و ویرایش پیام ادمین
        _db_manager.update_payment_status(payment_id, True, admin_id)
        try:
            admin_user = _bot.get_chat_member(admin_id, admin_id).user
            admin_username = f"@{admin_user.username}" if admin_user.username else admin_user.first_name
            new_caption = (message.caption or "") + "\n\n" + messages.ADMIN_PAYMENT_CONFIRMED_DISPLAY.format(admin_username=admin_username)
            _bot.edit_message_caption(new_caption, message.chat.id, message.message_id, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"امکان ویرایش کپشن پیام ادمین برای پرداخت {payment_id} وجود نداشت: {e}")

        # --- منطق اصلی: تفکیک نوع خرید ---
        if order_details.get('purchase_type') == 'profile':
            # اگر خرید پروفایل بود، تابع مرکزی و خودکار را فراخوانی کن
            finalize_profile_purchase(_bot, _db_manager, user_telegram_id, order_details)
        elif order_details.get('purchase_type') == 'wallet_charge':
            amount = order_details['total_price']
            if _db_manager.add_to_user_balance(user_db_id, amount):
                _bot.send_message(user_telegram_id, f"✅ کیف پول شما با موفقیت به مبلغ {amount:,.0f} تومان شارژ شد.")
            else:
                _bot.send_message(user_telegram_id, "❌ خطایی در شارژ کیف پول شما رخ داد. لطفاً با پشتیبانی تماس بگیرید.")
        else:
            # اگر خرید عادی بود، از کاربر نام دلخواه کانفیگ را بپرس
            prompt = _bot.send_message(user_telegram_id, messages.ASK_FOR_CUSTOM_CONFIG_NAME)
            _user_states[user_telegram_id] = {
                'state': 'waiting_for_custom_config_name',
                'data': order_details,
                'prompt_message_id': prompt.message_id
            }

    def process_payment_rejection(admin_id, payment_id, message):
        payment = _db_manager.get_payment_by_id(payment_id)
        if not payment or payment['is_confirmed']:
            _bot.answer_callback_query(message.id, "این پرداخت قبلاً پردازش شده است.", show_alert=True); return
        _db_manager.update_payment_status(payment_id, False, admin_id)
        admin_user = _bot.get_chat_member(admin_id, admin_id).user
        new_caption = message.caption + "\n\n" + messages.ADMIN_PAYMENT_REJECTED_DISPLAY.format(admin_username=f"@{admin_user.username}" if admin_user.username else admin_user.first_name)
        _bot.edit_message_caption(new_caption, message.chat.id, message.message_id, parse_mode='Markdown')
        order_details = json.loads(payment['order_details_json'])
        _bot.send_message(order_details['user_telegram_id'], messages.PAYMENT_REJECTED_USER.format(support_link=SUPPORT_CHANNEL_LINK))
        
        
    def save_inbound_changes(admin_id, message, server_id, selected_ids):
        """تغییرات انتخاب اینباندها را در دیتابیس ذخیره کرده و به کاربر بازخورد می‌دهد."""
        server_data = _db_manager.get_server_by_id(server_id)
        panel_inbounds = _admin_states.get(admin_id, {}).get('data', {}).get('panel_inbounds', [])
        
        inbounds_to_save = [
            {'id': p_in['id'], 'remark': p_in.get('remark', '')}
            for p_in in panel_inbounds if p_in['id'] in selected_ids
        ]
        
        # ابتدا اطلاعات در دیتابیس ذخیره می‌شود
        if _db_manager.update_server_inbounds(server_id, inbounds_to_save):
            msg = messages.INBOUND_CONFIG_SUCCESS
        else:
            msg = messages.INBOUND_CONFIG_FAILED

        # سپس پیام فعلی ویرایش شده و دکمه بازگشت نمایش داده می‌شود
        _bot.edit_message_text(
            msg.format(server_name=server_data['name']),
            admin_id,
            message.message_id,
            reply_markup=inline_keyboards.get_back_button("admin_server_management")
        )
        
        # در نهایت، وضعیت ادمین پاک می‌شود
        _clear_admin_state(admin_id)
    def start_manage_inbounds_flow(admin_id, message):
        _clear_admin_state(admin_id)
        servers = _db_manager.get_all_servers(only_active=False) 
        if not servers:
            _bot.edit_message_text(messages.NO_SERVERS_FOUND, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
            return
        
        server_list_text = "\n".join([f"ID: `{s['id']}` - {helpers.escape_markdown_v1(s['name'])}" for s in servers])
        prompt_text = f"**لیست سرورها:**\n{server_list_text}\n\n{messages.SELECT_SERVER_FOR_INBOUNDS_PROMPT}"
        
        prompt = _show_menu(admin_id, prompt_text, inline_keyboards.get_back_button("admin_server_management"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_server_id_for_inbounds', 'prompt_message_id': prompt.message_id}

    def process_manage_inbounds_flow(admin_id, message):
        """
        پس از دریافت ID سرور از ادمین، لیست اینباندهای آن را از پنل گرفته و نمایش می‌دهد.
        (نسخه اصلاح شده با استفاده از API Factory)
        """
        state_info = _admin_states.get(admin_id, {})
        if state_info.get('state') != 'waiting_for_server_id_for_inbounds': return

        server_id_str = message.text.strip()
        prompt_id = state_info.get('prompt_message_id')
        try: _bot.delete_message(admin_id, message.message_id)
        except Exception: pass
        
        if not server_id_str.isdigit() or not (server_data := _db_manager.get_server_by_id(int(server_id_str))):
            _bot.edit_message_text(f"{messages.SERVER_NOT_FOUND}\n\n{messages.SELECT_SERVER_FOR_INBOUNDS_PROMPT}", admin_id, prompt_id, parse_mode='Markdown')
            return

        server_id = int(server_id_str)
        _bot.edit_message_text(messages.FETCHING_INBOUNDS, admin_id, prompt_id)
        
        # --- اصلاح اصلی اینجاست ---
        # به جای ساخت مستقیم XuiAPIClient، از factory استفاده می‌کنیم
        api_client = get_api_client(server_data)
        if not api_client:
            logger.error(f"Could not create API client for server {server_id}. Data: {server_data}")
            _bot.edit_message_text("خطا در ایجاد کلاینت API برای این سرور.", admin_id, prompt_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
            _clear_admin_state(admin_id)
            return

        panel_inbounds = api_client.list_inbounds()
        # --- پایان بخش اصلاح شده ---

        if not panel_inbounds:
            _bot.edit_message_text(messages.NO_INBOUNDS_FOUND_ON_PANEL, admin_id, prompt_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
            _clear_admin_state(admin_id)
            return

        active_db_inbound_ids = [i['inbound_id'] for i in _db_manager.get_server_inbounds(server_id, only_active=True)]
        
        state_info['state'] = f'selecting_inbounds_for_{server_id}'
        state_info['data'] = {'panel_inbounds': panel_inbounds, 'selected_inbound_ids': active_db_inbound_ids}
        
        markup = inline_keyboards.get_inbound_selection_menu(server_id, panel_inbounds, active_db_inbound_ids)
        _bot.edit_message_text(messages.SELECT_INBOUNDS_TO_ACTIVATE.format(server_name=server_data['name']), admin_id, prompt_id, reply_markup=markup, parse_mode='Markdown')

    def save_inbound_changes(admin_id, message, server_id, selected_ids):
        """تغییرات انتخاب اینباندها را در دیتابیس ذخیره می‌کند."""
        server_data = _db_manager.get_server_by_id(server_id)
        panel_inbounds = _admin_states.get(admin_id, {}).get('data', {}).get('panel_inbounds', [])
        inbounds_to_save = [{'id': p_in['id'], 'remark': p_in.get('remark', '')} for p_in in panel_inbounds if p_in['id'] in selected_ids]
        
        msg = messages.INBOUND_CONFIG_SUCCESS if _db_manager.update_server_inbounds(server_id, inbounds_to_save) else messages.INBOUND_CONFIG_FAILED
        _bot.edit_message_text(msg.format(server_name=server_data['name']), admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
            
        _clear_admin_state(admin_id)

    def handle_inbound_selection(admin_id, call):
        """با منطق جدید برای خواندن callback_data اصلاح شده است."""
        data = call.data
        parts = data.split('_')
        action = parts[1]

        state_info = _admin_states.get(admin_id)
        if not state_info: return

        # استخراج server_id با روشی که برای همه اکشن‌ها کار کند
        server_id = int(parts[2]) if action == 'toggle' else int(parts[-1])
            
        if state_info.get('state') != f'selecting_inbounds_for_{server_id}': return

        selected_ids = state_info['data'].get('selected_inbound_ids', [])
        panel_inbounds = state_info['data'].get('panel_inbounds', [])

        if action == 'toggle':
            inbound_id_to_toggle = int(parts[3]) # آیدی اینباند همیشه پارامتر چهارم است
            if inbound_id_to_toggle in selected_ids:
                selected_ids.remove(inbound_id_to_toggle)
            else:
                selected_ids.append(inbound_id_to_toggle)
        
        elif action == 'select' and parts[2] == 'all':
            panel_ids = {p['id'] for p in panel_inbounds}
            selected_ids.extend([pid for pid in panel_ids if pid not in selected_ids])
        
        elif action == 'deselect' and parts[2] == 'all':
            selected_ids.clear()
            
        elif action == 'save':
            save_inbound_changes(admin_id, call.message, server_id, selected_ids)
            return
        
        state_info['data']['selected_inbound_ids'] = list(set(selected_ids))
        markup = inline_keyboards.get_inbound_selection_menu(server_id, panel_inbounds, selected_ids)
        
        try:
            _bot.edit_message_reply_markup(chat_id=admin_id, message_id=call.message.message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is not modified' not in e.description:
                logger.warning(f"Error updating inbound selection keyboard: {e}")
                
                
    def create_backup(admin_id, message):
        """از فایل‌های حیاتی ربات (دیتابیس و .env) بکاپ گرفته و برای ادمین ارسال می‌کند."""
        _bot.edit_message_text("⏳ در حال ساخت فایل پشتیبان...", admin_id, message.message_id)
        
        backup_filename = f"alamor_backup_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.zip"
        
        files_to_backup = [
            os.path.join(os.getcwd(), '.env'),
            _db_manager.db_path
        ]
        
        try:
            with zipfile.ZipFile(backup_filename, 'w') as zipf:
                for file_path in files_to_backup:
                    if os.path.exists(file_path):
                        zipf.write(file_path, os.path.basename(file_path))
                    else:
                        logger.warning(f"فایل بکاپ یافت نشد: {file_path}")

            with open(backup_filename, 'rb') as backup_file:
                _bot.send_document(admin_id, backup_file, caption="✅ فایل پشتیبان شما آماده است.")
            
            _bot.delete_message(admin_id, message.message_id)
            _show_admin_main_menu(admin_id)

        except Exception as e:
            logger.error(f"خطا در ساخت بکاپ: {e}")
            _bot.edit_message_text("❌ در ساخت فایل پشتیبان خطایی رخ داد.", admin_id, message.message_id)
        finally:
            # پاک کردن فایل زیپ پس از ارسال
            if os.path.exists(backup_filename):
                os.remove(backup_filename)
                
                
    def handle_gateway_type_selection(admin_id, message, gateway_type):
        state_info = _admin_states.get(admin_id)
        if not state_info or state_info.get('state') != 'waiting_for_gateway_type': return
        
        state_info['data']['gateway_type'] = gateway_type
        
        if gateway_type == 'zarinpal':
            state_info['state'] = 'waiting_for_merchant_id'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_MERCHANT_ID, admin_id, message.message_id)
        elif gateway_type == 'card_to_card':
            state_info['state'] = 'waiting_for_card_number'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_CARD_NUMBER, admin_id, message.message_id)
            
            
            
            
    def start_delete_plan_flow(admin_id, message):
        _clear_admin_state(admin_id)
        prompt = _show_menu(admin_id, messages.DELETE_PLAN_PROMPT, inline_keyboards.get_back_button("admin_plan_management"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_plan_id_to_delete', 'prompt_message_id': prompt.message_id}
        
    def process_delete_plan_id(admin_id, message):
        state_info = _admin_states[admin_id]
        if not message.text.isdigit() or not (plan := _db_manager.get_plan_by_id(int(message.text))):
            _bot.send_message(admin_id, messages.PLAN_NOT_FOUND); return

        plan_id = int(message.text)
        confirm_text = messages.DELETE_PLAN_CONFIRM.format(
            plan_name=helpers.escape_markdown_v1(plan['name']), 
            plan_id=plan_id
        )
        markup = inline_keyboards.get_confirmation_menu(f"confirm_delete_plan_{plan_id}", "admin_plan_management")
        _bot.edit_message_text(confirm_text, admin_id, state_info['prompt_message_id'], reply_markup=markup, parse_mode='Markdown')
        _clear_admin_state(admin_id) # State is cleared, waiting for callback

    def execute_delete_plan(admin_id, message, plan_id):
        plan = _db_manager.get_plan_by_id(plan_id)
        if plan and _db_manager.delete_plan(plan_id):
            _bot.edit_message_text(messages.PLAN_DELETED_SUCCESS.format(plan_name=plan['name']), admin_id, message.message_id)
        else:
            _bot.edit_message_text(messages.OPERATION_FAILED, admin_id, message.message_id)
        _show_plan_management_menu(admin_id)

    # --- EDIT PLAN ---
    def start_edit_plan_flow(admin_id, message):
        _clear_admin_state(admin_id)
        prompt = _show_menu(admin_id, messages.EDIT_PLAN_PROMPT_ID, inline_keyboards.get_back_button("admin_plan_management"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_plan_id_to_edit', 'data': {}, 'prompt_message_id': prompt.message_id}

    def process_edit_plan_id(admin_id, message):
        state_info = _admin_states[admin_id]
        if not message.text.isdigit() or not (plan := _db_manager.get_plan_by_id(int(message.text))):
            _bot.send_message(admin_id, messages.PLAN_NOT_FOUND); return
        
        state_info['data']['plan_id'] = int(message.text)
        state_info['data']['original_plan'] = plan
        state_info['state'] = 'waiting_for_new_plan_name'
        _bot.edit_message_text(messages.EDIT_PLAN_NEW_NAME, admin_id, state_info['prompt_message_id'])

    def process_edit_plan_name(admin_id, message):
        state_info = _admin_states[admin_id]
        state_info['data']['new_name'] = message.text
        state_info['state'] = 'waiting_for_new_plan_price'
        _bot.edit_message_text(messages.EDIT_PLAN_NEW_PRICE, admin_id, state_info['prompt_message_id'])

    def process_edit_plan_price(admin_id, message):
        state_info = _admin_states[admin_id]
        if not helpers.is_float_or_int(message.text) or float(message.text) < 0:
            _bot.send_message(admin_id, "قیمت نامعتبر است."); return
        
        data = state_info['data']
        original_plan = data['original_plan']
        
        _db_manager.update_plan(
            plan_id=data['plan_id'],
            name=data['new_name'],
            price=float(message.text),
            volume_gb=original_plan['volume_gb'],
            duration_days=original_plan['duration_days']
        )
        _bot.edit_message_text(messages.EDIT_PLAN_SUCCESS.format(plan_name=data['new_name']), admin_id, state_info['prompt_message_id'])
        _clear_admin_state(admin_id)
        _show_plan_management_menu(admin_id)
        
        
    def start_search_user_flow(admin_id, message):
        """Starts the flow for searching a user by their Telegram ID."""
        _clear_admin_state(admin_id)
        prompt = _show_menu(admin_id, "لطفاً آیدی عددی کاربر مورد نظر را وارد کنید:", inline_keyboards.get_back_button("admin_user_management"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_user_id_to_search', 'prompt_message_id': prompt.message_id}

    def process_user_search(admin_id, message):
        """Processes the user ID, finds the user, and shows their subscriptions."""
        state_info = _admin_states.get(admin_id, {})
        user_id_str = message.text.strip()

        if not user_id_str.isdigit():
            _bot.send_message(admin_id, "آیدی وارد شده نامعتبر است. لطفاً یک عدد وارد کنید.")
            return

        user_telegram_id = int(user_id_str)
        purchases = _db_manager.get_user_purchases_by_telegram_id(user_telegram_id)
        user_info = _db_manager.get_user_by_telegram_id(user_telegram_id)
        user_display = user_info['first_name'] if user_info else f"کاربر {user_telegram_id}"

        # --- THE FIX IS HERE: Pass _db_manager to the keyboard function ---
        markup = inline_keyboards.get_user_subscriptions_management_menu(_db_manager, purchases, user_telegram_id)
        
        _bot.edit_message_text(
            f"اشتراک‌های یافت شده برای **{user_display}**:",
            admin_id,
            state_info['prompt_message_id'],
            reply_markup=markup,
            parse_mode='Markdown'
        )
        _clear_admin_state(admin_id)
        
        
        
    def execute_delete_purchase(admin_id, message, purchase_id, user_telegram_id):
        """
        Deletes a purchase from the local database and the corresponding client
        from the X-UI panel.
        """
        # First, get purchase details to find the client UUID and server ID
        purchase = _db_manager.get_purchase_by_id(purchase_id)
        if not purchase:
            _bot.answer_callback_query(message.id, "این اشتراک یافت نشد.", show_alert=True)
            return

        # Step 1: Delete the purchase from the local database
        if not _db_manager.delete_purchase(purchase_id):
            _bot.answer_callback_query(message.id, "خطا در حذف اشتراک از دیتابیس.", show_alert=True)
            return

        # Step 2: Delete the client from the X-UI panel
        try:
            server = _db_manager.get_server_by_id(purchase['server_id'])
            if server and purchase['xui_client_uuid']:
                api_client = _xui_api(
                    panel_url=server['panel_url'],
                    username=server['username'],
                    password=server['password']
                )
                # We need the inbound_id to delete the client. This is a limitation.
                # A better approach for the future is to store inbound_id in the purchase record.
                # For now, we assume we need to iterate or have a default.
                # This part of the logic might need enhancement based on your X-UI panel version.
                # We will try to delete by UUID, which is supported by some panel forks.
                
                # Note: The default X-UI API requires inbound_id to delete a client.
                # If your panel supports deleting by UUID directly, this will work.
                # Otherwise, this part needs to be adapted.
                # For now, we log the action. A full implementation would require a proper API call.
                logger.info(f"Admin {admin_id} deleted purchase {purchase_id}. Corresponding X-UI client UUID to be deleted is {purchase['xui_client_uuid']} on server {server['name']}.")
                # api_client.delete_client(inbound_id, purchase['xui_client_uuid']) # This line would be needed
        except Exception as e:
            logger.error(f"Could not delete client from X-UI for purchase {purchase_id}: {e}")
            _bot.answer_callback_query(message.id, "اشتراک از دیتابیس حذف شد، اما در حذف از پنل خطایی رخ داد.", show_alert=True)

        _bot.answer_callback_query(message.id, f"✅ اشتراک {purchase_id} با موفقیت حذف شد.")

        # Step 3: Refresh the user's subscription list for the admin
        # We create a mock message object to pass to the search function
        mock_message = types.Message(
            message_id=message.message_id,
            chat=message.chat,
            date=None,
            content_type='text',
            options={},
            json_string=""
        )
        mock_message.text = str(user_telegram_id)
        
        # Put the admin back into the search state to show the updated list
        _admin_states[admin_id] = {'state': 'waiting_for_user_id_to_search', 'prompt_message_id': message.message_id}
        process_user_search(admin_id, mock_message)



    def show_channel_lock_menu(admin_id, message):
        """Displays the channel lock management menu."""
        channel_id = _db_manager.get_setting('required_channel_id')
        status = f"فعال روی کانال `{channel_id}`" if channel_id else "غیرفعال"
        text = messages.CHANNEL_LOCK_MENU_TEXT.format(status=status)
        markup = inline_keyboards.get_channel_lock_management_menu(channel_set=bool(channel_id))
        _show_menu(admin_id, text, markup, message)

    def start_set_channel_lock_flow(admin_id, message):
        _clear_admin_state(admin_id)
        prompt = _show_menu(admin_id, messages.CHANNEL_LOCK_SET_PROMPT, inline_keyboards.get_back_button("admin_channel_lock_management"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_channel_id', 'prompt_message_id': prompt.message_id}

    def process_set_channel_id(admin_id, message):
        state_info = _admin_states.get(admin_id, {})
        channel_id_str = message.text.strip()
        # ... (code for cancel and validation remains the same)

        if not (channel_id_str.startswith('-') and channel_id_str[1:].isdigit()):
            _bot.send_message(admin_id, messages.CHANNEL_LOCK_INVALID_ID)
            return

        # Save the ID in the state and ask for the link
        state_info['data'] = {'channel_id': channel_id_str}
        state_info['state'] = 'waiting_for_channel_link' # <-- Move to next state
        
        _bot.edit_message_text(
            "عالی. حالا لطفاً لینک عمومی کانال را وارد کنید (مثلاً: https://t.me/Alamor_Network):",
            admin_id,
            state_info['prompt_message_id']
        )

    def process_set_channel_link(admin_id, message):
        """ --- NEW FUNCTION --- """
        state_info = _admin_states.get(admin_id, {})
        channel_link = message.text.strip()
        
        if not channel_link.lower().startswith(('http://', 'https://')):
            _bot.send_message(admin_id, "لینک وارد شده نامعتبر است. لطفاً لینک کامل را وارد کنید.")
            return
            
        channel_id = state_info['data']['channel_id']

        # Now, save both ID and Link to the database
        _db_manager.update_setting('required_channel_id', channel_id)
        _db_manager.update_setting('required_channel_link', channel_link)
        
        _bot.edit_message_text(messages.CHANNEL_LOCK_SUCCESS.format(channel_id=channel_id), admin_id, state_info['prompt_message_id'])
        _clear_admin_state(admin_id)
        show_channel_lock_menu(admin_id) # Show the updated menu
    def execute_remove_channel_lock(admin_id, message):
        _db_manager.update_setting('required_channel_id', '') # Set to empty string
        _db_manager.update_setting('required_channel_link', '')
        _bot.answer_callback_query(message.id, messages.CHANNEL_LOCK_REMOVED)
        show_channel_lock_menu(admin_id, message)
        
    def show_tutorial_management_menu(admin_id, message):
        """Displays the main menu for tutorial management."""
        _show_menu(admin_id, "💡 مدیریت آموزش‌ها", inline_keyboards.get_tutorial_management_menu(), message)

    def list_tutorials(admin_id, message):
        """Lists all saved tutorials with delete buttons."""
        all_tutorials = _db_manager.get_all_tutorials()
        markup = inline_keyboards.get_tutorials_list_menu(all_tutorials)
        _show_menu(admin_id, "برای حذف یک آموزش، روی آن کلیک کنید:", markup, message)

    def execute_delete_tutorial(admin_id, message, tutorial_id):
        """Deletes a tutorial and refreshes the list."""
        if _db_manager.delete_tutorial(tutorial_id):
            _bot.answer_callback_query(message.id, "✅ آموزش با موفقیت حذف شد.")
            list_tutorials(admin_id, message) # Refresh the list
        else:
            _bot.answer_callback_query(message.id, "❌ در حذف آموزش خطایی رخ داد.", show_alert=True)

    def start_add_tutorial_flow(admin_id, message):
        """Starts the multi-step process for adding a new tutorial."""
        _clear_admin_state(admin_id)
        prompt = _show_menu(admin_id, "لطفاً پلتفرم آموزش را وارد کنید (مثلا: اندروید، ویندوز، آیفون):", inline_keyboards.get_back_button("admin_tutorial_management"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_tutorial_platform', 'data': {}, 'prompt_message_id': prompt.message_id}

    def process_tutorial_platform(admin_id, message):
        state_info = _admin_states[admin_id]
        state_info['data']['platform'] = message.text.strip()
        state_info['state'] = 'waiting_for_tutorial_app_name'
        _bot.edit_message_text("نام اپلیکیشن را وارد کنید (مثلا: V2RayNG):", admin_id, state_info['prompt_message_id'])

    def process_tutorial_app_name(admin_id, message):
        state_info = _admin_states[admin_id]
        state_info['data']['app_name'] = message.text.strip()
        state_info['state'] = 'waiting_for_tutorial_forward'
        _bot.edit_message_text("عالی. حالا پست آموزش را از کانال مورد نظر اینجا فوروارد کنید.", admin_id, state_info['prompt_message_id'])

    def process_tutorial_forward(admin_id, message):
        state_info = _admin_states.get(admin_id, {})
        # Check if the message is forwarded
        if not message.forward_from_chat:
            _bot.send_message(admin_id, "پیام ارسال شده فورواردی نیست. لطفاً یک پست را فوروارد کنید.")
            return

        data = state_info['data']
        platform = data['platform']
        app_name = data['app_name']
        forward_chat_id = message.forward_from_chat.id
        forward_message_id = message.forward_from_message_id

        if _db_manager.add_tutorial(platform, app_name, forward_chat_id, forward_message_id):
            _bot.edit_message_text("✅ آموزش با موفقیت ثبت شد.", admin_id, state_info['prompt_message_id'])
        else:
            _bot.edit_message_text("❌ خطایی در ثبت آموزش رخ داد.", admin_id, state_info['prompt_message_id'])
        
        _clear_admin_state(admin_id)
        show_tutorial_management_menu(admin_id)
        
        
    def show_support_management_menu(admin_id, message):
        """
        منوی مدیریت پشتیبانی را با ایمن‌سازی لینک برای جلوگیری از خطای Markdown نمایش می‌دهد.
        (نسخه نهایی و اصلاح شده)
        """
        support_link = _db_manager.get_setting('support_link') or "تنظیم نشده"
        
        # --- اصلاح اصلی اینجاست ---
        # لینک را قبل از استفاده در متن، ایمن‌سازی می‌کنیم
        escaped_link = helpers.escape_markdown_v1(support_link)
        
        text = messages.SUPPORT_MANAGEMENT_MENU_TEXT.format(link=escaped_link)
        markup = inline_keyboards.get_support_management_menu()
        
        # حالا _show_menu می‌تواند با خیال راحت از Markdown استفاده کند
        _show_menu(admin_id, text, markup, message, parse_mode='Markdown')

    def set_support_type(admin_id, call, support_type):
        """Sets the support type (admin chat or link)."""
        _db_manager.update_setting('support_type', support_type)
        
        # --- THE FIX IS HERE ---
        # Use call.id to answer the query, and call.message to edit the message
        _bot.answer_callback_query(call.id, messages.SUPPORT_TYPE_SET_SUCCESS)
        show_support_management_menu(admin_id, call.message)

    def start_edit_support_link_flow(admin_id, message):
        """Starts the process for setting/editing the support link."""
        _clear_admin_state(admin_id)
        prompt = _show_menu(admin_id, messages.SET_SUPPORT_LINK_PROMPT, inline_keyboards.get_back_button("admin_support_management"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_support_link', 'prompt_message_id': prompt.message_id}
    def process_support_link(admin_id, message):
        """Saves the support link and updates the menu directly. (Final Version)"""
        state_info = _admin_states.get(admin_id, {})
        support_link = message.text.strip()
        prompt_message_id = state_info.get('prompt_message_id')

        if not support_link.lower().startswith(('http://', 'https://', 't.me/')):
            _bot.send_message(admin_id, "لینک وارد شده نامعتبر است. لطفاً لینک کامل را وارد کنید.")
            return
            
        # Save the new link to the database
        _db_manager.update_setting('support_link', support_link)

        # --- اصلاح اصلی و نهایی ---
        # Get the text and keyboard for the updated menu
        new_support_link_text = _db_manager.get_setting('support_link') or "تنظیم نشده"
        menu_text = messages.SUPPORT_MANAGEMENT_MENU_TEXT.format(link=new_support_link_text)
        menu_markup = inline_keyboards.get_support_management_menu()

        # Directly edit the original prompt message to show the new menu
        try:
            if prompt_message_id:
                _bot.edit_message_text(
                    text=menu_text,
                    chat_id=admin_id,
                    message_id=prompt_message_id,
                    reply_markup=menu_markup,
                    parse_mode=None  # Use plain text to be safe
                )
        except Exception as e:
            logger.error(f"Failed to edit message into support menu: {e}")
            # If editing fails for any reason, send a new message with the menu
            _bot.send_message(admin_id, menu_text, reply_markup=menu_markup, parse_mode=None)

        # Clean up the admin state
        _clear_admin_state(admin_id)
        
    
        
    def execute_save_inbounds(admin_id, message, server_id):
        state_info = _admin_states.get(admin_id, {})
        if not state_info or state_info.get('state') != f'selecting_inbounds_for_{server_id}': return

        selected_ids = state_info['data'].get('selected_inbound_ids', [])
        panel_inbounds = state_info['data'].get('panel_inbounds', [])
        inbounds_to_save = [{'id': p_in['id'], 'remark': p_in.get('remark', '')} for p_in in panel_inbounds if p_in['id'] in selected_ids]
        
        server_data = _db_manager.get_server_by_id(server_id)
        if _db_manager.update_server_inbounds(server_id, inbounds_to_save):
            _bot.edit_message_text(messages.INBOUND_CONFIG_SUCCESS.format(server_name=server_data['name']), admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
        else:
            _bot.edit_message_text(messages.INBOUND_CONFIG_FAILED.format(server_name=server_data['name']), admin_id, message.message_id)
        _clear_admin_state(admin_id)

    @_bot.callback_query_handler(func=lambda call: helpers.is_admin(call.from_user.id) and call.data.startswith('panel_type_'))
    def handle_panel_type_selection(call):
        """نوع پنل انتخاب شده توسط ادمین را پردازش می‌کند."""
        admin_id = call.from_user.id
        panel_type = call.data.replace("panel_type_", "")
        
        server_data = {'panel_type': panel_type}
        
        prompt = _bot.edit_message_text("نام دلخواه سرور را وارد کنید:", admin_id, call.message.message_id)
        _bot.register_next_step_handler(prompt, process_add_server_name, server_data)

    def process_add_server_name(message, server_data):
        """نام سرور را پردازش کرده و آدرس پنل را می‌پرسد."""
        admin_id = message.from_user.id
        server_data['name'] = message.text.strip()
        
        prompt = _bot.send_message(admin_id, "آدرس کامل پنل را وارد کنید (مثال: http://1.2.3.4:54321):")
        _bot.register_next_step_handler(prompt, process_add_server_url, server_data)

    def process_add_server_url(message, server_data):
        """آدرس پنل را پردازش کرده و نام کاربری را می‌پرسد."""
        admin_id = message.from_user.id
        server_data['panel_url'] = message.text.strip()
        
        # برای هیدیفای، به جای یوزرنیم، UUID ادمین را می‌پرسیم
        prompt_text = "نام کاربری پنل را وارد کنید:"
        if server_data['panel_type'] == 'hiddify':
            prompt_text = "UUID ادمین پنل هیدیفای را وارد کنید:"
            
        prompt = _bot.send_message(admin_id, prompt_text)
        _bot.register_next_step_handler(prompt, process_add_server_username, server_data)

    def process_add_server_username(message, server_data):
        """نام کاربری را پردازش کرده و رمز عبور را می‌پرسد."""
        admin_id = message.from_user.id
        server_data['username'] = message.text.strip()
        
        # برای هیدیفay، رمز عبور لازم نیست
        if server_data['panel_type'] == 'hiddify':
            # مستقیم به مرحله ذخیره می‌رویم
            execute_add_server(admin_id, server_data)
            return

        prompt = _bot.send_message(admin_id, "رمز عبور پنل را وارد کنید:")
        _bot.register_next_step_handler(prompt, process_add_server_password, server_data)

    def process_add_server_password(message, server_data):
        """رمز عبور را پردازش کرده و آدرس سابسکریپشن را می‌پرسد."""
        admin_id = message.from_user.id
        server_data['password'] = message.text.strip()
        
        prompt = _bot.send_message(admin_id, "آدرس پایه سابسکریپشن را وارد کنید (مثال: https://yourdomain.com:2096):")
        _bot.register_next_step_handler(prompt, process_add_server_sub_base_url, server_data)

    def process_add_server_sub_base_url(message, server_data):
        """آدرس سابسکریپشن را پردازش کرده و پیشوند مسیر را می‌پرسد."""
        admin_id = message.from_user.id
        server_data['sub_base_url'] = message.text.strip()

        prompt = _bot.send_message(admin_id, "پیشوند مسیر سابسکریپشن را وارد کنید (مثال: sub):")
        _bot.register_next_step_handler(prompt, process_add_server_sub_path, server_data)

    def process_add_server_sub_path(message, server_data):
        """پیشوند مسیر را پردازش کرده و سرور را ذخیره می‌کند."""
        admin_id = message.from_user.id
        server_data['sub_path_prefix'] = message.text.strip()
        execute_add_server(admin_id, server_data)

    def execute_add_server(admin_id, server_data):
        """اطلاعات نهایی را در دیتابیس ذخیره می‌کند."""
        # برای هیدیفای مقادیر خالی را تنظیم می‌کنیم
        password = server_data.get('password', '')
        sub_base_url = server_data.get('sub_base_url', '')
        sub_path_prefix = server_data.get('sub_path_prefix', '')

        new_server_id = _db_manager.add_server(
            name=server_data['name'],
            panel_type=server_data['panel_type'],
            panel_url=server_data['panel_url'],
            username=server_data['username'],
            password=password,
            sub_base_url=sub_base_url,
            sub_path_prefix=sub_path_prefix
        )

        if new_server_id:
            _bot.send_message(admin_id, f"✅ سرور '{server_data['name']}' با موفقیت اضافه شد.")
        else:
            _bot.send_message(admin_id, f"❌ خطایی در افزودن سرور رخ داد. ممکن است نام سرور تکراری باشد.")
            
            
            
            
    def start_add_profile_flow(admin_id, message):
        """فرآیند افزودن پروفایل جدید را شروع می‌کند."""
        _clear_admin_state(admin_id)
        prompt = _show_menu(admin_id, messages.ADD_PROFILE_PROMPT_NAME, inline_keyboards.get_back_button("admin_profile_management"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_profile_name', 'data': {}, 'prompt_message_id': prompt.message_id}

    # ... (در بخش Final Execution Functions)

    def execute_add_profile(admin_id, data):
        _clear_admin_state(admin_id)
        profile_id = _db_manager.add_profile(
            name=data['name'],
            per_gb_price=data['per_gb_price'],
            duration_days=data['duration_days'],
            description=data['description']
        )
        if profile_id:
            msg = messages.ADD_PROFILE_SUCCESS.format(profile_name=data['name'])
        elif profile_id is None:
            msg = messages.ADD_PROFILE_DUPLICATE_ERROR.format(profile_name=data['name'])
        else:
            msg = messages.ADD_PROFILE_GENERAL_ERROR
        _bot.send_message(admin_id, msg)
        _show_profile_management_menu(admin_id)

            
        
    def list_all_profiles(admin_id, message):
        profiles = _db_manager.get_all_profiles()
        if not profiles:
            text = "هیچ پروفایلی تاکنون ثبت نشده است."
        else:
            text = "📄 **لیست پروفایل‌های ثبت شده:**\n\n"
            for p in profiles:
                status = "✅ فعال" if p['is_active'] else "❌ غیرفعال"
                description = p['description'] or "ندارد"
                details = (
                    f"**ID: `{p['id']}` - {helpers.escape_markdown_v1(p['name'])}**\n"
                    f"▫️ قیمت هر گیگ: `{p['per_gb_price']:,.0f}` تومان\n"
                    f"▫️ مدت: `{p['duration_days']}` روز\n"
                    f"▫️ توضیحات: {helpers.escape_markdown_v1(description)}\n"
                    f"▫️ وضعیت: {status}\n"
                    "-----------------------------------\n"
                )
                text += details
        _show_menu(admin_id, text, inline_keyboards.get_back_button("admin_profile_management"), message)

    def start_manage_profile_inbounds_flow(admin_id, message):
        """فرآیند مدیریت اینباندهای یک پروفایل را با نمایش لیست پروفایل‌ها شروع می‌کند."""
        profiles = _db_manager.get_all_profiles()
        if not profiles:
            _bot.answer_callback_query(message.id, "ابتدا باید حداقل یک پروفایل بسازید.", show_alert=True)
            return
            
        markup = inline_keyboards.get_profile_selection_menu(profiles)
        _show_menu(admin_id, "لطفاً پروفایلی که می‌خواهید اینباندهای آن را مدیریت کنید، انتخاب نمایید:", markup, message)

    
    def handle_profile_selection(admin_id, message, profile_id):
        """
        پس از انتخاب پروفایل، لیست سرورها را برای انتخاب نمایش می‌دهد.
        """
        _clear_admin_state(admin_id)
        servers = _db_manager.get_all_servers(only_active=False)
        if not servers:
            _bot.answer_callback_query(message.id, "هیچ سروری ثبت نشده است. ابتدا یک سرور اضافه کنید.", show_alert=True)
            return

        # ذخیره کردن پروفایل انتخاب شده در وضعیت ادمین برای مراحل بعدی
        _admin_states[admin_id] = {'state': 'selecting_server_for_profile', 'data': {'profile_id': profile_id}}
        
        markup = inline_keyboards.get_server_selection_menu_for_profile(servers, profile_id)
        _show_menu(admin_id, "بسیار خب. حالا سروری که می‌خواهید از آن اینباند اضافه کنید را انتخاب نمایید:", markup, message)
        
        
        
        
        
    def handle_server_selection_for_profile(admin_id, message, profile_id, server_id):
        """
        پس از انتخاب سرور، به پنل وصل شده و لیست اینباندها را به صورت چک‌لیست نمایش می‌دهد.
        """
        _bot.edit_message_text(messages.FETCHING_INBOUNDS, admin_id, message.message_id)
        
        server_data = _db_manager.get_server_by_id(server_id)
        if not server_data:
            _bot.answer_callback_query(message.id, "سرور یافت نشد.", show_alert=True); return

        api_client = get_api_client(server_data)
        if not api_client or not api_client.check_login():
            _bot.edit_message_text("❌ اتصال به پنل سرور ناموفق بود.", admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button(f"admin_select_profile_{profile_id}")); return

        panel_inbounds = api_client.list_inbounds()
        if not panel_inbounds:
            _bot.edit_message_text(messages.NO_INBOUNDS_FOUND_ON_PANEL, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button(f"admin_select_profile_{profile_id}")); return
            
        # فقط اینباندهایی که برای این پروفایل و همین سرور انتخاب شده‌اند را می‌خوانیم
        selected_inbound_ids = _db_manager.get_inbounds_for_profile(profile_id, server_id=server_id)
        
        _admin_states[admin_id] = {
            'state': 'selecting_inbounds_for_profile',
            'data': {
                'profile_id': profile_id,
                'server_id': server_id,
                'panel_inbounds': panel_inbounds,
                'selected_inbound_ids': selected_inbound_ids
            }
        }
        
        markup = inline_keyboards.get_inbound_selection_menu_for_profile(profile_id, server_id, panel_inbounds, selected_inbound_ids)
        profile = _db_manager.get_profile_by_id(profile_id)
        _show_menu(admin_id, f"اینباندها را برای پروفایل '{profile['name']}' از سرور '{server_data['name']}' انتخاب کنید:", markup, message)
    def handle_profile_inbound_toggle(admin_id, message, profile_id, server_id, inbound_id):
        """تیک زدن یا برداشتن تیک یک اینباند در چک‌لیست را مدیریت می‌کند."""
        state_info = _admin_states.get(admin_id)
        if not state_info or state_info.get('state') != 'selecting_inbounds_for_profile': return
        
        data = state_info['data']
        if data['profile_id'] != profile_id or data['server_id'] != server_id: return

        selected_ids = data['selected_inbound_ids']
        if inbound_id in selected_ids:
            selected_ids.remove(inbound_id)
        else:
            selected_ids.append(inbound_id)
            
        markup = inline_keyboards.get_inbound_selection_menu_for_profile(
            profile_id, server_id, data['panel_inbounds'], selected_ids
        )
        try:
            _bot.edit_message_reply_markup(chat_id=admin_id, message_id=message.message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is not modified' not in str(e):
                logger.warning(f"Error updating profile inbound checklist: {e}")

    def execute_save_profile_inbounds(admin_id, message, profile_id, server_id):
        state_info = _admin_states.get(admin_id)
        if not state_info or state_info.get('state') != 'selecting_inbounds_for_profile': return

        try:
            _bot.answer_callback_query(message.id, "⏳ در حال ذخیره تغییرات...")
        except Exception: pass

        selected_ids = state_info['data']['selected_inbound_ids']
        
        # --- لاگ جدید و مهم ---
        logger.info(f"ADMIN DEBUG: Saving to DB for profile_id={profile_id}, server_id={server_id}. Selected inbound_ids: {selected_ids}")
        
        if _db_manager.update_inbounds_for_profile(profile_id, server_id, selected_ids):
            pass # موفقیت آمیز بود
        else:
            _bot.send_message(admin_id, "❌ خطایی در ذخیره تغییرات در دیتابیس رخ داد.")

        _clear_admin_state(admin_id)
        _show_profile_management_menu(admin_id, message)
    def start_sync_configs_flow(admin_id, message):
        """
        فرآیند همگام‌سازی را با دریافت جزئیات کامل هر اینباند به صورت جداگانه اجرا می‌کند. (نسخه نهایی)
        """
        try:
            _bot.edit_message_text("⏳ شروع فرآیند همگام‌سازی... این عملیات ممکن است کمی طول بکشد.", admin_id, message.message_id)
        except Exception:
            pass

        servers = _db_manager.get_all_servers(only_active=False)
        if not servers:
            _bot.send_message(admin_id, "هیچ سروری برای همگام‌سازی یافت نشد.")
            _show_admin_main_menu(admin_id)
            return

        report = "📊 **گزارش همگام‌سازی کانفیگ‌ها:**\n\n"
        total_synced = 0
        
        for server in servers:
            server_name = server['name']
            panel_type = server['panel_type']
            
            api_client = get_api_client(server)
            if not api_client or not api_client.check_login():
                report += f"❌ **{helpers.escape_markdown_v1(server_name)}**: اتصال ناموفق بود.\n"
                continue
                
            # ۱. ابتدا لیست خلاصه را برای گرفتن ID ها دریافت می‌کنیم
            panel_inbounds_summary = api_client.list_inbounds()
            if not panel_inbounds_summary:
                report += f"⚠️ **{helpers.escape_markdown_v1(server_name)}**: هیچ اینباندی در پنل یافت نشد.\n"
                continue

            # ۲. حالا برای هر اینباند، جزئیات کامل آن را جداگانه می‌گیریم
            full_inbounds_details = []
            for inbound_summary in panel_inbounds_summary:
                inbound_id = inbound_summary.get('id')
                if not inbound_id:
                    continue
                
                # فراخوانی get_inbound برای دریافت دیتای کامل
                detailed_inbound = api_client.get_inbound(inbound_id)
                if detailed_inbound:
                    full_inbounds_details.append(detailed_inbound)
                else:
                    logger.warning(f"Could not fetch details for inbound {inbound_id} on server {server_name}")

            # ۳. داده‌های کامل و نرمالایز شده را در دیتابیس ذخیره می‌کنیم
            normalized_configs = normalize_panel_inbounds(panel_type, full_inbounds_details)
            sync_result = _db_manager.sync_configs_for_server(server['id'], normalized_configs)
            
            if sync_result > 0:
                report += f"✅ **{helpers.escape_markdown_v1(server_name)}**: {sync_result} کانفیگ با موفقیت همگام‌سازی شد.\n"
                total_synced += sync_result
            elif sync_result == 0:
                report += f"⚠️ **{helpers.escape_markdown_v1(server_name)}**: هیچ کانفیگ کاملی برای همگام‌سازی یافت نشد.\n"
            else:
                report += f"❌ **{helpers.escape_markdown_v1(server_name)}**: خطایی در پردازش دیتابیس رخ داد.\n"

        report += f"\n---\n**مجموع:** {total_synced} کانفیگ در دیتابیس محلی ذخیره شد."
        _bot.send_message(admin_id, report, parse_mode='Markdown')
        _show_admin_main_menu(admin_id)
        
        
    
    def process_delete_server_id(admin_id, message):
        """ID سرور وارد شده برای حذف را پردازش کرده و پیام تایید را نمایش می‌دهد."""
        state_info = _admin_states.get(admin_id, {})
        prompt_id = state_info.get("prompt_message_id")
        server_id_str = message.text.strip()

        if not server_id_str.isdigit() or not (server := _db_manager.get_server_by_id(int(server_id_str))):
            _bot.edit_message_text(f"{messages.SERVER_NOT_FOUND}\n\n{messages.DELETE_SERVER_PROMPT}", admin_id, prompt_id)
            return
            
        server_id = int(server_id_str)
        confirm_text = messages.DELETE_SERVER_CONFIRM.format(server_name=server['name'], server_id=server_id)
        markup = inline_keyboards.get_confirmation_menu(f"confirm_delete_server_{server_id}", "admin_server_management")
        _bot.edit_message_text(confirm_text, admin_id, prompt_id, reply_markup=markup, parse_mode='Markdown')
        _clear_admin_state(admin_id)
        
        
    def execute_delete_domain(admin_id, message, domain_id):
        """منطق اصلی حذف دامنه از سیستم و دیتابیس را اجرا می‌کند."""
        domain = next((d for d in _db_manager.get_all_subscription_domains() if d['id'] == domain_id), None)
        if not domain:
            _bot.answer_callback_query(message.id, "دامنه یافت نشد.", show_alert=True)
            return

        domain_name = domain['domain_name']
        
        # حذف فایل‌های سیستمی
        remove_domain_nginx_files(domain_name)
        
        # حذف از دیتابیس
        if _db_manager.delete_subscription_domain(domain_id):
            _bot.answer_callback_query(message.id, f"دامنه {domain_name} با موفقیت حذف شد.")
        else:
            _bot.answer_callback_query(message.id, "خطا در حذف دامنه از دیتابیس.", show_alert=True)
            
        # نمایش مجدد منوی مدیریت دامنه‌ها
        from .domain_handlers import show_domain_management_menu # ایمپورت محلی برای جلوگیری از خطا
        show_domain_management_menu(admin_id, message)
        
        
    def _show_admin_management_menu(admin_id, message):
        admins = _db_manager.get_all_admins()
        admin_list = "\n".join([f"- `{admin['telegram_id']}` ({admin['first_name']})" for admin in admins])
        text = f"🔑 **مدیریت ادمین‌ها**\n\n**لیست ادمین‌های فعلی:**\n{admin_list}"
        _show_menu(admin_id, text, inline_keyboards.get_admin_management_menu(), message)

    def start_add_admin_flow(admin_id, message):
        _clear_admin_state(admin_id)
        prompt = _show_menu(admin_id, "لطفاً آیدی عددی کاربری که می‌خواهید به ادمین تبدیل شود را وارد کنید:", inline_keyboards.get_back_button("admin_manage_admins"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_admin_id_to_add', 'prompt_message_id': prompt.message_id}

    def start_remove_admin_flow(admin_id, message):
        _clear_admin_state(admin_id)
        prompt = _show_menu(admin_id, "لطفاً آیدی عددی ادمینی که می‌خواهید از لیست حذف شود را وارد کنید:", inline_keyboards.get_back_button("admin_manage_admins"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_admin_id_to_remove', 'prompt_message_id': prompt.message_id}
        
        
        
    def check_nginx_status(admin_id, message):
        """وضعیت و کانفیگ Nginx را بررسی کرده و نتیجه را به ادمین ارسال می‌کند."""
        _bot.edit_message_text("⏳ در حال بررسی وضعیت وب‌سرور Nginx... لطفاً صبر کنید.", admin_id, message.message_id)
        
        # اجرای دستور status
        status_success, status_output = run_shell_command(['systemctl', 'status', 'nginx.service'])
        
        # اجرای دستور تست کانفیگ
        config_success, config_output = run_shell_command(['nginx', '-t'])
        
        # آماده‌سازی گزارش نهایی
        report = "📊 **گزارش وضعیت Nginx**\n\n"
        report += "--- **وضعیت سرویس (`systemctl status`)** ---\n"
        report += f"```\n{status_output}\n```\n\n"
        report += "--- **تست فایل‌های کانفیگ (`nginx -t`)** ---\n"
        report += f"```\n{config_output}\n```\n\n"
        
        if status_success and config_success:
            report += "✅ به نظر می‌رسد سرویس Nginx فعال و کانفیگ آن بدون مشکل است."
        else:
            report += "❌ مشکلی در سرویس یا کانفیگ Nginx وجود دارد. لطفاً خروجی‌های بالا را بررسی کنید."
            
        _bot.send_message(admin_id, report, parse_mode='Markdown')
        _show_admin_main_menu(admin_id) # نمایش مجدد منوی اصلی
        
        
    def run_system_health_check(admin_id, message):
        """یک بررسی کامل روی وضعیت سیستم انجام داده و تلاش می‌کند مشکلات رایج را حل کند."""
        msg = _bot.edit_message_text("🩺 **شروع چکاپ کامل سیستم...**\n\nلطفاً چند لحظه صبر کنید، نتایج به تدریج نمایش داده می‌شوند.", admin_id, message.message_id, parse_mode='Markdown')
        
        report_parts = ["📊 **گزارش وضعیت کامل سیستم**\n"]
        errors_found = False

        # ۱. بررسی سرویس‌ها
        report_parts.append("\n--- **۱. وضعیت سرویس‌ها** ---")
        services_to_check = ['alamorbot.service', 'alamor_webhook.service', 'nginx.service']
        for service in services_to_check:
            is_active, _ = run_shell_command(['systemctl', 'is-active', service])
            if is_active:
                report_parts.append(f"✅ سرویس `{service}`: **فعال**")
            else:
                errors_found = True
                report_parts.append(f"❌ سرویس `{service}`: **غیرفعال**")
                report_parts.append(f"   - در حال تلاش برای روشن کردن...")
                start_success, start_output = run_shell_command(['systemctl', 'start', service])
                if start_success:
                    report_parts.append("   - ✅ سرویس با موفقیت روشن شد!")
                else:
                    report_parts.append(f"   - ❌ روشن کردن ناموفق بود.")
        
        # ۲. بررسی اتصال به دیتابیس
        report_parts.append("\n--- **۲. اتصال به دیتابیس** ---")
        if _db_manager.check_connection():
            report_parts.append("✅ اتصال به دیتابیس PostgreSQL: **موفق**")
        else:
            errors_found = True
            report_parts.append("❌ اتصال به دیتابیس PostgreSQL: **ناموفق**\n   - لطفاً اطلاعات `DB_` در فایل `.env` را بررسی کنید.")

        # ۳. بررسی اتصال به پنل‌های X-UI
        report_parts.append("\n--- **۳. اتصال به پنل‌های X-UI** ---")
        servers = _db_manager.get_all_servers(only_active=False)
        if not servers:
            report_parts.append("⚠️ هیچ سروری در ربات تعریف نشده است.")
        else:
            for server in servers:
                api_client = get_api_client(server)
                if api_client and api_client.check_login():
                    report_parts.append(f"✅ اتصال به سرور '{helpers.escape_markdown_v1(server['name'])}': **موفق**")
                else:
                    errors_found = True
                    report_parts.append(f"❌ اتصال به سرور '{helpers.escape_markdown_v1(server['name'])}': **ناموفق**")

        # ۴. بررسی تنظیمات کلیدی
        report_parts.append("\n--- **۴. بررسی تنظیمات فروش** ---")
        if not _db_manager.get_active_subscription_domain():
            errors_found = True
            report_parts.append("⚠️ **هشدار:** هیچ دامنه اشتراک فعالی تنظیم نشده است. کاربران نمی‌توانند لینک دریافت کنند.")
        if not _db_manager.get_all_plans(only_active=True):
            errors_found = True
            report_parts.append("⚠️ **هشدار:** هیچ پلن فروش فعالی وجود ندارد. کاربران نمی‌توانند خرید کنند.")
        if not _db_manager.get_all_payment_gateways(only_active=True):
            errors_found = True
            report_parts.append("⚠️ **هشدار:** هیچ درگاه پرداخت فعالی وجود ندارد. کاربران نمی‌توانند پرداخت کنند.")
        
        if not errors_found:
            report_parts.append("\n✅ **نتیجه:** تمام بخش‌های کلیدی سیستم به درستی کار می‌کنند.")
        else:
            report_parts.append("\n❌ **نتیجه:** برخی مشکلات شناسایی شد. لطفاً گزارش بالا را بررسی کنید.")
            
        final_report = "\n".join(report_parts)
        _bot.edit_message_text(final_report, admin_id, msg.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_main_menu"))
        
        
        
        
    def start_sample_config_flow(admin_id, message, target_inbounds, context):
        """
        فرآیند دریافت کانفیگ نمونه را برای لیستی از اینباندها شروع می‌کند.
        """
        if not target_inbounds:
            _bot.send_message(admin_id, "✅ تمام تنظیمات با موفقیت ذخیره شد.")
            _clear_admin_state(admin_id)
            
            # --- اصلاح اصلی و نهایی اینجاست ---
            # حالا ربات به منوی صحیح برمی‌گردد
            if context.get('type') == 'profile':
                # به جای رفتن به بخش اختصاص اینباند، به منوی مدیریت الگوهای پروفایل برمی‌گردیم
                show_profile_template_management_menu(admin_id, message)
            else:
                # برای حالت عادی هم به منوی مدیریت الگوهای سرور برمی‌گردیم
                show_template_management_menu(admin_id, message)
            return

        current_inbound = target_inbounds[0]
        remaining_inbounds = target_inbounds[1:]

        _admin_states[admin_id] = {
            'state': 'waiting_for_sample_config',
            'data': {
                'current_inbound': current_inbound,
                'remaining_inbounds': remaining_inbounds,
                'context': context
            }
        }
        
        inbound_remark = current_inbound.get('remark', f"ID: {current_inbound.get('id')}")
        
        prompt_text = (
            f"لطفاً یک **لینک کانفیگ نمونه** برای اینباند زیر ارسال کنید:\n\n"
            f"▫️ **سرور:** {context['server_name']}\n"
            f"▫️ **اینباند:** {inbound_remark}"
        )
        
        prompt = _show_menu(admin_id, prompt_text, None, message)
        _admin_states[admin_id]['prompt_message_id'] = prompt.message_id
    def process_sample_config_input(admin_id, message):
        """
        کانفیگ نمونه را پردازش، تجزیه کرده و هم پارامترها و هم متن خام آن را ذخیره می‌کند.
        """
        state_info = _admin_states.get(admin_id)
        if not state_info or state_info.get('state') != 'waiting_for_sample_config':
            return

        raw_template_link = message.text.strip()
        parsed_params = parse_config_link(raw_template_link)

        if not parsed_params:
            _bot.send_message(admin_id, "❌ لینک ارسال شده نامعتبر است. لطفاً یک لینک VLESS صحیح برای همین اینباند ارسال کنید.")
            return
        
        inbound_info = state_info['data']['current_inbound']
        context = state_info['data']['context']
        params_json = json.dumps(parsed_params)

        success = False
        if context['type'] == 'profile':
            success = _db_manager.update_profile_inbound_template(context['profile_id'], context['server_id'], inbound_info['id'], params_json, raw_template_link)
        else:
            success = _db_manager.update_server_inbound_template(context['server_id'], inbound_info['id'], params_json, raw_template_link)

        if success:
            _bot.edit_message_text("✅ پارامترها و الگوی خام با موفقیت ذخیره شد.", admin_id, state_info['prompt_message_id'])
        else:
            _bot.edit_message_text("❌ خطایی در ذخیره الگو در دیتابیس رخ داد.", admin_id, state_info['prompt_message_id'])

        start_sample_config_flow(admin_id, message, state_info['data']['remaining_inbounds'], context)
    def show_template_management_menu(admin_id, message):
        """منوی مدیریت الگوهای کانفیگ را نمایش می‌دهد."""
        all_inbounds = _db_manager.get_all_active_inbounds_with_server_info()
        markup = inline_keyboards.get_template_management_menu(all_inbounds)
        _show_menu(admin_id, "برای ثبت یا ویرایش الگوی یک اینباند، روی آن کلیک کنید:", markup, message)




    def show_profile_template_management_menu(admin_id, message):
        """منوی مدیریت الگوهای کانفیگ برای پروفایل‌ها را نمایش می‌دهد."""
        # ما به یک تابع جدید در db_manager نیاز داریم تا این اطلاعات را بخواند
        all_profile_inbounds = _db_manager.get_all_profile_inbounds_with_status()
        # از یک کیبورد جدید برای نمایش این اطلاعات استفاده خواهیم کرد
        markup = inline_keyboards.get_profile_template_management_menu(all_profile_inbounds)
        _show_menu(admin_id, "برای ثبت یا ویرایش الگوی یک اینباند در پروفایل، روی آن کلیک کنید:", markup, message)
        
        
    def show_profile_inbounds_db_status(admin_id, message):
        """محتوای جدول profile_inbounds را برای دیباگ نمایش می‌دهد."""
        records = _db_manager.get_all_profile_inbounds_for_debug()
        
        if not records:
            text = "جدول `profile_inbounds` در حال حاضر خالی است."
        else:
            text = "📄 **محتوای فعلی جدول `profile_inbounds`:**\n\n"
            for rec in records:
                text += (
                    f"▫️ **پروفایل:** `{rec['profile_id']}` ({rec['profile_name']})\n"
                    f"▫️ **سرور:** `{rec['server_id']}` ({rec['server_name']})\n"
                    f"▫️ **اینباند:** `{rec['inbound_id']}`\n"
                    "--------------------\n"
                )
                
        _show_menu(admin_id, text, inline_keyboards.get_back_button("admin_profile_management"), message)

   
    def show_branding_settings_menu(admin_id, message):
        """منوی تنظیمات برندینگ را نمایش می‌دهد."""
        brand_name = _db_manager.get_setting('brand_name') or "Alamor" # نام پیش‌فرض
        text = (
            f"🎨 **تنظیمات برندینگ**\n\n"
            f"نام برند فعلی شما: **{brand_name}**\n\n"
            f"این نام در ایمیل و remark کانفیگ‌ها استفاده خواهد شد."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✏️ تغییر نام برند", callback_data="admin_change_brand_name"))
        markup.add(inline_keyboards.get_back_button("admin_main_menu").keyboard[0][0])
        _show_menu(admin_id, text, markup, message, parse_mode='Markdown')

    def start_change_brand_name_flow(admin_id, message):
        """فرآیند درخواست نام جدید برند را شروع می‌کند."""
        _clear_admin_state(admin_id)
        prompt = _show_menu(admin_id, "لطفاً نام برند جدید را وارد کنید (فقط حروف و اعداد انگلیسی، بدون فاصله):", inline_keyboards.get_back_button("admin_branding_settings"), message)
        _admin_states[admin_id] = {'state': 'waiting_for_brand_name', 'prompt_message_id': prompt.message_id}
        
        
        
    def show_message_management_menu(admin_id, message):
        """منوی اصلی برای مدیریت پیام‌های ربات را نمایش می‌دهد."""
        all_messages = _db_manager.get_all_bot_messages()
        markup = inline_keyboards.get_message_management_menu(all_messages)
        text = "✍️ **مدیریت پیام‌ها**\n\nبرای ویرایش هر پیام، روی آن کلیک کنید:"
        _show_menu(admin_id, text, markup, message, parse_mode='Markdown')