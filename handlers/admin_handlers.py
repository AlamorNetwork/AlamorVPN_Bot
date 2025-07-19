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

logger = logging.getLogger(__name__)

# ماژول‌های سراسری
_bot: telebot.TeleBot = None
_db_manager: DatabaseManager = None
_xui_api: XuiAPIClient = None
_config_generator: ConfigGenerator = None
_admin_states = {}

def register_admin_handlers(bot_instance, db_manager_instance, xui_api_instance):
    global _bot, _db_manager, _xui_api, _config_generator
    _bot = bot_instance
    _db_manager = db_manager_instance
    _xui_api = xui_api_instance
    _config_generator = ConfigGenerator(xui_api_instance, db_manager_instance)

    # =============================================================================
    # SECTION: Helper and Menu Functions
    # =============================================================================

    def _clear_admin_state(admin_id):
        """وضعیت ادمین را فقط از دیکشنری پاک می‌کند."""
        if admin_id in _admin_states:
            del _admin_states[admin_id]

    def _show_menu(user_id, text, markup, message=None):
        try:
            if message:
                return _bot.edit_message_text(text, user_id, message.message_id, reply_markup=markup, parse_mode='Markdown')
            else:
                return _bot.send_message(user_id, text, reply_markup=markup, parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
            if 'message to edit not found' in e.description:
                return _bot.send_message(user_id, text, reply_markup=markup, parse_mode='Markdown')
            elif 'message is not modified' not in e.description:
                logger.warning(f"Error handling menu for {user_id}: {e}")
        return message

    def _show_admin_main_menu(admin_id, message=None): _show_menu(admin_id, messages.ADMIN_WELCOME, inline_keyboards.get_admin_main_inline_menu(), message)
    def _show_server_management_menu(admin_id, message=None): _show_menu(admin_id, messages.SERVER_MGMT_MENU_TEXT, inline_keyboards.get_server_management_inline_menu(), message)
    def _show_plan_management_menu(admin_id, message=None): _show_menu(admin_id, messages.PLAN_MGMT_MENU_TEXT, inline_keyboards.get_plan_management_inline_menu(), message)
    def _show_payment_gateway_management_menu(admin_id, message=None): _show_menu(admin_id, messages.PAYMENT_GATEWAY_MGMT_MENU_TEXT, inline_keyboards.get_payment_gateway_management_inline_menu(), message)
    def _show_user_management_menu(admin_id, message=None): _show_menu(admin_id, messages.USER_MGMT_MENU_TEXT, inline_keyboards.get_user_management_inline_menu(), message)

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
        servers = _db_manager.get_all_servers()
        if not servers:
            _bot.send_message(admin_id, messages.NO_SERVERS_FOUND); _show_server_management_menu(admin_id); return
        results = []
        for s in servers:
            temp_xui_client = _xui_api(panel_url=s['panel_url'], username=s['username'], password=s['password'])
            is_online = temp_xui_client.login()
            _db_manager.update_server_status(s['id'], is_online, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            results.append(f"{'✅' if is_online else '❌'} {helpers.escape_markdown_v1(s['name'])}")
        _bot.send_message(admin_id, messages.TEST_RESULTS_HEADER + "\n".join(results), parse_mode='Markdown')
        _show_server_management_menu(admin_id)

    # =============================================================================
    # SECTION: Stateful Process Handlers
    # =============================================================================

    def _handle_stateful_message(admin_id, message):
        state_info = _admin_states.get(admin_id, {})
        state = state_info.get("state")
        prompt_id = state_info.get("prompt_message_id")
        data = state_info.get("data", {})
        text = message.text
        

        # --- Server Flows ---
        if state == 'waiting_for_server_name':
            data['name'] = text; state_info['state'] = 'waiting_for_server_url'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_URL, admin_id, prompt_id)
        elif state == 'waiting_for_server_url':
            data['url'] = text; state_info['state'] = 'waiting_for_server_username'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_USERNAME, admin_id, prompt_id)
        elif state == 'waiting_for_server_username':
            data['username'] = text; state_info['state'] = 'waiting_for_server_password'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_PASSWORD, admin_id, prompt_id)
        elif state == 'waiting_for_server_password':
            data['password'] = text; state_info['state'] = 'waiting_for_sub_base_url'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_SUB_BASE_URL, admin_id, prompt_id)
        elif state == 'waiting_for_sub_base_url':
            data['sub_base_url'] = text; state_info['state'] = 'waiting_for_sub_path_prefix'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_SUB_PATH_PREFIX, admin_id, prompt_id)
        elif state == 'waiting_for_sub_path_prefix':
            data['sub_path_prefix'] = text; execute_add_server(admin_id, data)
        elif state == 'waiting_for_server_id_to_delete':
            if not text.isdigit() or not (server := _db_manager.get_server_by_id(int(text))):
                _bot.edit_message_text(f"{messages.SERVER_NOT_FOUND}\n\n{messages.DELETE_SERVER_PROMPT}", admin_id, prompt_id); return
            confirm_text = messages.DELETE_SERVER_CONFIRM.format(server_name=server['name'], server_id=server['id'])
            markup = inline_keyboards.get_confirmation_menu(f"confirm_delete_server_{server['id']}", "admin_server_management")
            _bot.edit_message_text(confirm_text, admin_id, prompt_id, reply_markup=markup)

        # --- Plan Flows ---
        elif state == 'waiting_for_plan_name':
            data['name'] = text; state_info['state'] = 'waiting_for_plan_type'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_TYPE, admin_id, prompt_id, reply_markup=inline_keyboards.get_plan_type_selection_menu_admin())
        elif state == 'waiting_for_plan_volume':
            if not helpers.is_float_or_int(text): _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_VOLUME}", admin_id, prompt_id); return
            data['volume_gb'] = float(text); state_info['state'] = 'waiting_for_plan_duration'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_DURATION, admin_id, prompt_id)
        elif state == 'waiting_for_plan_duration':
            if not text.isdigit(): _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_DURATION}", admin_id, prompt_id); return
            data['duration_days'] = int(text); state_info['state'] = 'waiting_for_plan_price'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_PRICE, admin_id, prompt_id)
        elif state == 'waiting_for_plan_price':
            if not helpers.is_float_or_int(text): _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_PRICE}", admin_id, prompt_id); return
            data['price'] = float(text); execute_add_plan(admin_id, data)
        elif state == 'waiting_for_per_gb_price':
            if not helpers.is_float_or_int(text): _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_PER_GB_PRICE}", admin_id, prompt_id); return
            data['per_gb_price'] = float(text); state_info['state'] = 'waiting_for_gb_plan_duration'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_DURATION_GB, admin_id, prompt_id)
        elif state == 'waiting_for_gb_plan_duration':
            if not text.isdigit(): _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_DURATION_GB}", admin_id, prompt_id); return
            data['duration_days'] = int(text); execute_add_plan(admin_id, data)
        elif state == 'waiting_for_plan_id_to_toggle':
            execute_toggle_plan_status(admin_id, text)

        # --- Gateway Flows ---
        if state == 'waiting_for_gateway_name':
            data['name'] = text
            state_info['state'] = 'waiting_for_gateway_type'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_TYPE, admin_id, prompt_id, reply_markup=inline_keyboards.get_gateway_type_selection_menu())
        elif state == 'waiting_for_merchant_id':
            data['merchant_id'] = text
            state_info['state'] = 'waiting_for_gateway_description'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_DESCRIPTION, admin_id, prompt_id)

        elif state == 'waiting_for_card_number':
            if not text.isdigit() or len(text) not in [16]:
                _bot.edit_message_text(f"شماره کارت نامعتبر است.\n\n{messages.ADD_GATEWAY_PROMPT_CARD_NUMBER}", admin_id, prompt_id)
                return
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
            
        # --- Inbound Flow ---
        elif state == 'waiting_for_server_id_for_inbounds':
            process_manage_inbounds_flow(admin_id, message)

        
    # =============================================================================
    # SECTION: Process Starters and Callback Handlers
    # =============================================================================
    def start_add_server_flow(admin_id, message):
        _clear_admin_state(admin_id)
        _admin_states[admin_id] = {'state': 'waiting_for_server_name', 'data': {}, 'prompt_message_id': message.message_id}
        _bot.edit_message_text(messages.ADD_SERVER_PROMPT_NAME, admin_id, message.message_id)

    def start_delete_server_flow(admin_id, message):
        _clear_admin_state(admin_id)
        list_text = _generate_server_list_text()
        if list_text == messages.NO_SERVERS_FOUND:
            _bot.edit_message_text(list_text, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management")); return
        _admin_states[admin_id] = {'state': 'waiting_for_server_id_to_delete', 'prompt_message_id': message.message_id}
        prompt_text = f"{list_text}\n\n{messages.DELETE_SERVER_PROMPT}"
        _bot.edit_message_text(prompt_text, admin_id, message.message_id, parse_mode='Markdown')

    def start_add_plan_flow(admin_id, message):
        _clear_admin_state(admin_id)
        _admin_states[admin_id] = {'state': 'waiting_for_plan_name', 'data': {}, 'prompt_message_id': message.message_id}
        _bot.edit_message_text(messages.ADD_PLAN_PROMPT_NAME, admin_id, message.message_id)
        
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

    def get_plan_details_from_callback(admin_id, message, plan_type):
        state_info = _admin_states.get(admin_id, {})
        if state_info.get('state') != 'waiting_for_plan_type': return
        state_info['data']['plan_type'] = plan_type
        if plan_type == 'fixed_monthly':
            state_info['state'] = 'waiting_for_plan_volume'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_VOLUME, admin_id, message.message_id)
        elif plan_type == 'gigabyte_based':
            state_info['state'] = 'waiting_for_per_gb_price'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_PER_GB_PRICE, admin_id, message.message_id)
        state_info['prompt_message_id'] = message.message_id

    # ... other functions remain the same ...

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

        # --- بخش اصلاح شده ---
        # تعریف توابع داخلی برای خوانایی بهتر
        def list_plans_action(a_id, msg):
            # پاس دادن صحیح پارامترها به تابع اصلی
            text = list_all_plans(a_id, msg, return_text=True)
            _bot.edit_message_text(text, a_id, msg.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_plan_management"))

        def list_gateways_action(a_id, msg):
            # پاس دادن صحیح پارامترها به تابع اصلی
            text = list_all_gateways(a_id, msg, return_text=True)
            _bot.edit_message_text(text, a_id, msg.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_payment_management"))
        # --- پایان بخش اصلاح شده ---

        actions = {
            "admin_create_backup": create_backup,
            "admin_main_menu": _show_admin_main_menu,
            "admin_server_management": _show_server_management_menu,
            "admin_plan_management": _show_plan_management_menu,
            "admin_payment_management": _show_payment_gateway_management_menu,
            "admin_user_management": _show_user_management_menu,
            "admin_add_server": start_add_server_flow,
            "admin_delete_server": start_delete_server_flow,
            "admin_add_plan": start_add_plan_flow,
            "admin_toggle_plan_status": start_toggle_plan_status_flow,
            "admin_add_gateway": start_add_gateway_flow,
            "admin_toggle_gateway_status": start_toggle_gateway_status_flow,
            "admin_list_servers": list_all_servers,
            "admin_test_all_servers": test_all_servers,
            "admin_list_plans": list_plans_action,
            "admin_list_gateways": list_gateways_action,
            "admin_list_users": list_all_users,
            "admin_manage_inbounds": start_manage_inbounds_flow,
        }
        
        if data in actions:
            _clear_admin_state(admin_id)
            actions[data](admin_id, message)
            return

        # --- هندل کردن موارد پیچیده‌تر ---
        if data.startswith("gateway_type_"):
            handle_gateway_type_selection(admin_id, call.message, data.replace('gateway_type_', ''))
        elif data.startswith("plan_type_"):
            get_plan_details_from_callback(admin_id, message, data.replace('plan_type_', ''))
        elif data.startswith("confirm_delete_server_"):
            execute_delete_server(admin_id, message, int(data.split('_')[-1]))
        elif data.startswith("inbound_"):
            handle_inbound_selection(admin_id, call)
        elif data.startswith("admin_approve_payment_"):
            process_payment_approval(admin_id, int(data.split('_')[-1]), message)
        elif data.startswith("admin_reject_payment_"):
            process_payment_rejection(admin_id, int(data.split('_')[-1]), message)
        else:
            _bot.edit_message_text(messages.UNDER_CONSTRUCTION, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_main_menu"))
    @_bot.message_handler(func=lambda msg: helpers.is_admin(msg.from_user.id) and _admin_states.get(msg.from_user.id))
    def handle_admin_stateful_messages(message):
        _handle_stateful_message(message.from_user.id, message)
        
        


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

    def process_manage_inbounds_flow(admin_id, message):
        state_info = _admin_states.get(admin_id, {})
        if state_info.get('state') != 'waiting_for_server_id_for_inbounds': return
        server_id_str = message.text.strip()
        prompt_id = state_info.get('prompt_message_id')
        try: _bot.delete_message(admin_id, message.message_id)
        except Exception: pass
        if not server_id_str.isdigit() or not (server_data := _db_manager.get_server_by_id(int(server_id_str))):
            _bot.edit_message_text(f"{messages.SERVER_NOT_FOUND}\n\n{messages.SELECT_SERVER_FOR_INBOUNDS_PROMPT}", admin_id, prompt_id, parse_mode='Markdown'); return
        server_id = int(server_id_str)
        _bot.edit_message_text(messages.FETCHING_INBOUNDS, admin_id, prompt_id)
        temp_xui_client = _xui_api(panel_url=server_data['panel_url'], username=server_data['username'], password=server_data['password'])
        panel_inbounds = temp_xui_client.list_inbounds()
        if not panel_inbounds:
            _bot.edit_message_text(messages.NO_INBOUNDS_FOUND_ON_PANEL, admin_id, prompt_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
            _clear_admin_state(admin_id); return
        active_db_inbound_ids = [i['inbound_id'] for i in _db_manager.get_server_inbounds(server_id, only_active=True)]
        state_info['state'] = f'selecting_inbounds_for_{server_id}'
        state_info['data'] = {'panel_inbounds': panel_inbounds, 'selected_inbound_ids': active_db_inbound_ids}
        markup = inline_keyboards.get_inbound_selection_menu(server_id, panel_inbounds, active_db_inbound_ids)
        _bot.edit_message_text(messages.SELECT_INBOUNDS_TO_ACTIVATE.format(server_name=server_data['name']), admin_id, prompt_id, reply_markup=markup, parse_mode='Markdown')

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
            _bot.edit_message_caption("⏳ در حال ساخت سرویس...", message.chat.id, message.message_id)
            payment = _db_manager.get_payment_by_id(payment_id)
            if not payment or payment['is_confirmed']:
                _bot.answer_callback_query(message.id, "این پرداخت قبلاً پردازش شده است.", show_alert=True); return
            order_details = json.loads(payment['order_details_json'])
            user_telegram_id = order_details['user_telegram_id']
            user_db_id = order_details['user_db_id']
            
            if order_details['plan_type'] == 'fixed_monthly':
                plan = order_details['plan_details']
                total_gb = plan['volume_gb']
                duration_days = plan['duration_days']
                plan_id = plan['id']
            else: # gigabyte_based
                gb_plan = order_details['gb_plan_details']
                total_gb = order_details['requested_gb']
                duration_days = gb_plan.get('duration_days', 0)
                plan_id = gb_plan['id']
                
            client_details, sub_link, single_configs = _config_generator.create_client_and_configs(user_telegram_id, order_details['server_id'], total_gb, duration_days)
            if not client_details:
                _bot.edit_message_caption("❌ خطا در ساخت سرویس در پنل X-UI.", message.chat.id, message.message_id); return
            
            expire_date = (datetime.datetime.now() + datetime.timedelta(days=duration_days)) if duration_days and duration_days > 0 else None
            purchase_id = _db_manager.add_purchase(
                user_db_id, order_details['server_id'], plan_id,
                expire_date.strftime("%Y-%m-%d %H:%M:%S") if expire_date else None,
                total_gb, client_details['uuid'], client_details['email'],
                client_details['subscription_id'], single_configs
            )
            if not purchase_id:
                _bot.edit_message_caption("❌ خطا در ذخیره خرید در دیتابیس.", message.chat.id, message.message_id); return
                
            _db_manager.update_payment_status(payment_id, True, admin_id)
            admin_user = _bot.get_chat_member(admin_id, admin_id).user
            new_caption = message.caption + "\n\n" + messages.ADMIN_PAYMENT_CONFIRMED_DISPLAY.format(admin_username=f"@{admin_user.username}" if admin_user.username else admin_user.first_name)
            _bot.edit_message_caption(new_caption, message.chat.id, message.message_id, parse_mode='Markdown')
            
            _bot.send_message(user_telegram_id, messages.SERVICE_ACTIVATION_SUCCESS_USER)
            
            # --- بخش اصلاح شده ---
            # فراخوانی تابع مشترک جدید برای ارسال لینک و QR کد
            send_subscription_info(_bot, user_telegram_id, sub_link)



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
            """فرآیند مدیریت اینباند را با نمایش لیست سرورها آغاز می‌کند."""
            _clear_admin_state(admin_id)
            list_text = _generate_server_list_text()
            if list_text == messages.NO_SERVERS_FOUND:
                _bot.edit_message_text(list_text, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
                return
            
            _admin_states[admin_id] = {'state': 'waiting_for_server_id_for_inbounds', 'prompt_message_id': message.message_id}
            prompt_text = f"{list_text}\n\n{messages.SELECT_SERVER_FOR_INBOUNDS_PROMPT}"
            _bot.edit_message_text(prompt_text, admin_id, message.message_id, parse_mode='Markdown')


    def process_manage_inbounds_flow(admin_id, message):
        """
        پس از دریافت ID سرور از ادمین، لیست اینباندهای آن را از پنل X-UI گرفته و نمایش می‌دهد.
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
        
        temp_xui_client = _xui_api(panel_url=server_data['panel_url'], username=server_data['username'], password=server_data['password'])
        panel_inbounds = temp_xui_client.list_inbounds()

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