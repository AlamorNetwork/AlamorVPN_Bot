import telebot
from telebot import types
import logging
import json
import qrcode
from io import BytesIO
import requests
from config import WEBHOOK_DOMAIN
from config import ZARINPAL_MERCHANT_ID, WEBHOOK_DOMAIN
from config import SUPPORT_CHANNEL_LINK, ADMIN_IDS
from database.db_manager import DatabaseManager
from api_client.xui_api_client import XuiAPIClient
from utils import messages, helpers
from keyboards import inline_keyboards
from utils.config_generator import ConfigGenerator
from utils.helpers import is_float_or_int , escape_markdown_v1
from utils.bot_helpers import send_subscription_info # این ایمپورت جدید است
from config import ZARINPAL_MERCHANT_ID, WEBHOOK_DOMAIN , ZARINPAL_SANDBOX

logger = logging.getLogger(__name__)

# ماژول های سراسری
_bot: telebot.TeleBot = None
_db_manager: DatabaseManager = None
_xui_api: XuiAPIClient = None
_config_generator: ConfigGenerator = None

# متغیرهای وضعیت
_user_menu_message_ids = {} # {user_id: message_id}
_user_states = {} # {user_id: {'state': '...', 'data': {...}}}

if ZARINPAL_SANDBOX:
    ZARINPAL_API_URL = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
    ZARINPAL_STARTPAY_URL = "https://sandbox.zarinpal.com/pg/StartPay/"
else:
    ZARINPAL_API_URL = "https://api.zarinpal.com/pg/v4/payment/request.json"
    ZARINPAL_STARTPAY_URL = "https://www.zarinpal.com/pg/StartPay/"
def register_user_handlers(bot_instance, db_manager_instance, xui_api_instance):
    global _bot, _db_manager, _xui_api, _config_generator
    _bot = bot_instance
    _db_manager = db_manager_instance
    _xui_api = xui_api_instance
    _config_generator = ConfigGenerator(_xui_api, _db_manager)

    # --- هندلرهای اصلی ---
    @_bot.callback_query_handler(func=lambda call: not call.from_user.is_bot and call.data.startswith('user_'))
    def handle_main_callbacks(call):
        """هندل کردن دکمه‌های منوی اصلی کاربر"""
        user_id = call.from_user.id
        _bot.answer_callback_query(call.id)
        
        # فقط در صورتی وضعیت را پاک کن که یک آیتم از منوی اصلی انتخاب شده باشد
        if call.data in ["user_main_menu", "user_buy_service", "user_my_services", "user_free_test", "user_support"]:
            _clear_user_state(user_id)

        data = call.data
        if data == "user_main_menu":
            _show_user_main_menu(user_id, message_to_edit=call.message)
        elif data == "user_buy_service":
            start_purchase(user_id, call.message)
        elif data == "user_my_services":
            show_my_services_list(user_id, call.message)
        
        # --- بخش اصلاح شده ---
        elif data == "user_free_test":
            # اکنون تابع ساخت اکانت تست فراخوانی می‌شود
            handle_free_test_request(user_id, call.message)
        # --- پایان بخش اصلاح شده ---

        elif data == "user_support":
            _bot.edit_message_text(f"📞 برای پشتیبانی با ما در ارتباط باشید: {SUPPORT_CHANNEL_LINK}", user_id, call.message.message_id)
        elif data.startswith("user_service_details_"):
            purchase_id = int(data.replace("user_service_details_", ""))
            show_service_details(user_id, purchase_id, call.message)
        elif data.startswith("user_get_single_configs_"):
            purchase_id = int(data.replace("user_get_single_configs_", ""))
            send_single_configs(user_id, purchase_id)
    @_bot.callback_query_handler(func=lambda call: not call.from_user.is_bot and call.data.startswith(('buy_', 'select_', 'confirm_', 'cancel_')))
    def handle_purchase_callbacks(call):
        """هندل کردن دکمه‌های فرآیند خرید"""
        _bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        data = call.data
        
        # پاک کردن پیام قبلی
        try:
            _bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=None)
        except Exception:
            pass

        if data.startswith("buy_select_server_"):
            server_id = int(data.replace("buy_select_server_", ""))
            select_server_for_purchase(user_id, server_id, call.message)
        elif data.startswith("buy_plan_type_"):
            select_plan_type(user_id, data.replace("buy_plan_type_", ""), call.message)
        elif data.startswith("buy_select_plan_"):
            plan_id = int(data.replace("buy_select_plan_", ""))
            select_fixed_plan(user_id, plan_id, call.message)
        elif data == "confirm_and_pay":
            display_payment_gateways(user_id, call.message)
        elif data.startswith("select_gateway_"):
            gateway_id = int(data.replace("select_gateway_", ""))
            select_payment_gateway(user_id, gateway_id, call.message)
        elif data == "cancel_order":
            _clear_user_state(user_id)
            _bot.edit_message_text(messages.ORDER_CANCELED, user_id, call.message.message_id, reply_markup=inline_keyboards.get_back_button("user_main_menu"))


    @_bot.message_handler(content_types=['text', 'photo'], func=lambda msg: _user_states.get(msg.from_user.id))
    def handle_stateful_messages(message):
        """هندل کردن پیام‌های متنی یا عکسی که کاربر در یک وضعیت خاص ارسال می‌کند"""
        user_id = message.from_user.id
        state_info = _user_states[user_id]
        current_state = state_info.get('state')

        # حذف پیام ورودی کاربر برای تمیز ماندن چت
        try: _bot.delete_message(user_id, message.message_id)
        except Exception: pass

        if current_state == 'waiting_for_gigabytes_input':
            process_gigabyte_input(message)
        elif current_state == 'waiting_for_payment_receipt':
            process_payment_receipt(message)


    # --- توابع کمکی و اصلی ---
    def _clear_user_state(user_id):
        if user_id in _user_states:
            del _user_states[user_id]
        _bot.clear_step_handler_by_chat_id(chat_id=user_id)

    def _show_user_main_menu(user_id, message_to_edit=None):
        _clear_user_state(user_id)
        menu_text = messages.USER_MAIN_MENU_TEXT
        menu_markup = inline_keyboards.get_user_main_inline_menu()
        if message_to_edit:
            try:
                _bot.edit_message_text(menu_text, user_id, message_to_edit.message_id, reply_markup=menu_markup)
            except telebot.apihelper.ApiTelegramException: # Message not modified
                pass
        else:
            _bot.send_message(user_id, menu_text, reply_markup=menu_markup)

    # --- فرآیند خرید ---
    def start_purchase(user_id, message):
        active_servers = [s for s in _db_manager.get_all_servers() if s['is_active'] and s['is_online']]
        if not active_servers:
            _bot.edit_message_text(messages.NO_ACTIVE_SERVERS_FOR_BUY, user_id, message.message_id, reply_markup=inline_keyboards.get_back_button("user_main_menu"))
            return
        
        _user_states[user_id] = {'state': 'selecting_server', 'data': {}}
        _bot.edit_message_text(messages.SELECT_SERVER_PROMPT, user_id, message.message_id, reply_markup=inline_keyboards.get_server_selection_menu(active_servers))

    def select_server_for_purchase(user_id, server_id, message):
        _user_states[user_id]['data']['server_id'] = server_id
        _user_states[user_id]['state'] = 'selecting_plan_type'
        _bot.edit_message_text(messages.SELECT_PLAN_TYPE_PROMPT_USER, user_id, message.message_id, reply_markup=inline_keyboards.get_plan_type_selection_menu_user(server_id))
    
    def select_plan_type(user_id, plan_type, message):
        _user_states[user_id]['data']['plan_type'] = plan_type
        if plan_type == 'fixed_monthly':
            active_plans = [p for p in _db_manager.get_all_plans(only_active=True) if p['plan_type'] == 'fixed_monthly']
            if not active_plans:
                _bot.edit_message_text(messages.NO_FIXED_PLANS_AVAILABLE, user_id, message.message_id, reply_markup=inline_keyboards.get_back_button(f"buy_select_server_{_user_states[user_id]['data']['server_id']}"))
                return
            _user_states[user_id]['state'] = 'selecting_fixed_plan'
            _bot.edit_message_text(messages.SELECT_FIXED_PLAN_PROMPT, user_id, message.message_id, reply_markup=inline_keyboards.get_fixed_plan_selection_menu(active_plans))
        
        elif plan_type == 'gigabyte_based':
            gb_plan = next((p for p in _db_manager.get_all_plans(only_active=True) if p['plan_type'] == 'gigabyte_based'), None)
            if not gb_plan or not gb_plan.get('per_gb_price'):
                _bot.edit_message_text(messages.GIGABYTE_PLAN_NOT_CONFIGURED, user_id, message.message_id, reply_markup=inline_keyboards.get_back_button(f"buy_select_server_{_user_states[user_id]['data']['server_id']}"))
                return
            _user_states[user_id]['data']['gb_plan_details'] = gb_plan
            _user_states[user_id]['state'] = 'waiting_for_gigabytes_input'
            sent_msg = _bot.edit_message_text(messages.ENTER_GIGABYTES_PROMPT, user_id, message.message_id, reply_markup=inline_keyboards.get_back_button(f"buy_select_server_{_user_states[user_id]['data']['server_id']}"))
            _user_states[user_id]['prompt_message_id'] = sent_msg.message_id

    def select_fixed_plan(user_id, plan_id, message):
        plan = _db_manager.get_plan_by_id(plan_id)
        if not plan:
            _bot.edit_message_text(messages.OPERATION_FAILED, user_id, message.message_id)
            return
        _user_states[user_id]['data']['plan_details'] = plan
        show_order_summary(user_id, message)
        
    def process_gigabyte_input(message):
        user_id = message.from_user.id
        state_data = _user_states[user_id]
        
        if not is_float_or_int(message.text) or float(message.text) <= 0:
            _bot.edit_message_text(messages.INVALID_GIGABYTE_INPUT + "\n" + messages.ENTER_GIGABYTES_PROMPT, user_id, state_data['prompt_message_id'])
            return
            
        state_data['data']['requested_gb'] = float(message.text)
        show_order_summary(user_id, message)

    def show_order_summary(user_id, message):
        _user_states[user_id]['state'] = 'confirming_order'
        order_data = _user_states[user_id]['data']
        
        server_info = _db_manager.get_server_by_id(order_data['server_id'])
        summary_text = messages.ORDER_SUMMARY_HEADER
        summary_text += messages.ORDER_SUMMARY_SERVER.format(server_name=server_info['name'])
        
        total_price = 0
        plan_details_for_admin = ""
        
        if order_data['plan_type'] == 'fixed_monthly':
            plan = order_data['plan_details']
            summary_text += messages.ORDER_SUMMARY_FIXED_PLAN.format(
                plan_name=plan['name'],
                volume_gb=plan['volume_gb'],
                duration_days=plan['duration_days']
            )
            total_price = plan['price']
            plan_details_for_admin = f"{plan['name']} ({plan['volume_gb']}GB, {plan['duration_days']} روز)"

        elif order_data['plan_type'] == 'gigabyte_based':
            gb_plan = order_data['gb_plan_details']
            requested_gb = order_data['requested_gb']
            total_price = requested_gb * gb_plan['per_gb_price']
            summary_text += messages.ORDER_SUMMARY_GIGABYTE_PLAN.format(gigabytes=requested_gb)
            plan_details_for_admin = f"{requested_gb} گیگابایت"

        summary_text += messages.ORDER_SUMMARY_TOTAL_PRICE.format(total_price=total_price)
        summary_text += messages.ORDER_SUMMARY_CONFIRM_PROMPT
        
        order_data['total_price'] = total_price
        order_data['plan_details_for_admin'] = plan_details_for_admin
        
        prompt_id = _user_states[user_id].get('prompt_message_id', message.message_id)
        _bot.edit_message_text(summary_text, user_id, prompt_id, reply_markup=inline_keyboards.get_order_confirmation_menu())

    # --- فرآیند پرداخت ---
    def display_payment_gateways(user_id, message):
        _user_states[user_id]['state'] = 'selecting_gateway'
        active_gateways = _db_manager.get_all_payment_gateways(only_active=True)
        if not active_gateways:
            _bot.edit_message_text(messages.NO_ACTIVE_PAYMENT_GATEWAYS, user_id, message.message_id, reply_markup=inline_keyboards.get_back_button("show_order_summary"))
            return
        
        _bot.edit_message_text(messages.SELECT_PAYMENT_GATEWAY_PROMPT, user_id, message.message_id, reply_markup=inline_keyboards.get_payment_gateway_selection_menu(active_gateways))
        
    def select_payment_gateway(user_id, gateway_id, message):
        gateway = _db_manager.get_payment_gateway_by_id(gateway_id)
        if not gateway:
            _bot.edit_message_text(messages.OPERATION_FAILED, user_id, message.message_id)
            return

        order_data = _user_states[user_id]['data']
        user_db_info = _db_manager.get_user_by_telegram_id(user_id)
        
        # --- منطق تفکیک نوع درگاه ---
        if gateway['type'] == 'zarinpal':
            _bot.edit_message_text("⏳ در حال ساخت لینک پرداخت امن... لطفاً صبر کنید.", user_id, message.message_id)
            
            amount_toman = int(order_data['total_price'])
            
            # FIX: اطلاعات درگاه را به سفارش اضافه می‌کنیم تا در وب‌هوک قابل دسترس باشد
            order_data['gateway_details'] = gateway
            
            order_details_for_db = json.dumps(order_data)
            payment_id = _db_manager.add_payment(user_db_info['id'], amount_toman, message.message_id, order_details_for_db)
            
            if not payment_id:
                _bot.edit_message_text("❌ در ایجاد صورتحساب خطایی رخ داد.", user_id, message.message_id)
                return

            callback_url = f"https://{WEBHOOK_DOMAIN}/zarinpal/verify"
            
            payload = {
                "merchant_id": gateway['merchant_id'],
                "amount": amount_toman * 10, # FIX: تبدیل تومان به ریال
                "callback_url": callback_url,
                "description": f"خرید سرویس از ربات - سفارش شماره {payment_id}",
                "metadata": {"user_id": str(user_id), "payment_id": str(payment_id)}
            }
            
            try:
                response = requests.post(ZARINPAL_API_URL, json=payload, timeout=20)
                response.raise_for_status()
                result = response.json()

                if result.get("data") and result.get("data", {}).get("code") == 100:
                    authority = result['data']['authority']
                    payment_url = f"{ZARINPAL_STARTPAY_URL}{authority}"
                    _db_manager.set_payment_authority(payment_id, authority)
                    
                    # FIX: ساخت صحیح کیبورد با دو دکمه مجزا
                    markup = types.InlineKeyboardMarkup()
                    btn_pay = types.InlineKeyboardButton("🚀 پرداخت آنلاین", url=payment_url)
                    btn_back = types.InlineKeyboardButton("❌ انصراف و بازگشت", callback_data="user_main_menu")
                    markup.add(btn_pay)
                    markup.add(btn_back)
                    
                    _bot.edit_message_text("لینک پرداخت شما ساخته شد. لطفاً از طریق دکمه زیر اقدام کنید.", user_id, message.message_id, reply_markup=markup)
                    _clear_user_state(user_id)
                else:
                    error_code = result.get("errors", {}).get("code", "نامشخص")
                    error_message = result.get("errors", {}).get("message", "خطای نامشخص از درگاه پرداخت")
                    _bot.edit_message_text(f"❌ خطا در ساخت لینک پرداخت: {error_message} (کد: {error_code})", user_id, message.message_id)

            except requests.exceptions.HTTPError as http_err:
                logger.error(f"HTTP error occurred: {http_err} - Response: {http_err.response.text}")
                _bot.edit_message_text("❌ درگاه پرداخت با خطای داخلی مواجه شد. لطفاً بعداً تلاش کنید.", user_id, message.message_id)
            except requests.exceptions.RequestException as e:
                logger.error(f"Error connecting to Zarinpal: {e}")
                _bot.edit_message_text("❌ امکان اتصال به درگاه پرداخت در حال حاضر وجود ندارد.", user_id, message.message_id)

        # --- منطق برای کارت به کارت ---
        elif gateway['type'] == 'card_to_card':
            _user_states[user_id]['data']['gateway_details'] = gateway
            _user_states[user_id]['state'] = 'waiting_for_payment_receipt'
            total_price = order_data['total_price']
            payment_text = messages.PAYMENT_GATEWAY_DETAILS.format(
                name=gateway['name'], card_number=gateway['card_number'],
                card_holder_name=gateway['card_holder_name'],
                description_line=f"**توضیحات:** {gateway['description']}\n" if gateway.get('description') else "",
                amount=total_price
            )
            sent_msg = _bot.edit_message_text(payment_text, user_id, message.message_id, reply_markup=inline_keyboards.get_back_button("show_order_summary"))
            _user_states[user_id]['prompt_message_id'] = sent_msg.message_id

    def process_payment_receipt(message):
        user_id = message.from_user.id
        state_data = _user_states.get(user_id)

        # اگر کاربر در وضعیت انتظار رسید نیست، خارج شو
        if not state_data or state_data.get('state') != 'waiting_for_payment_receipt':
            return

        # اگر پیام عکس نیست، به کاربر اطلاع بده
        if not message.photo:
            prompt_id = state_data.get('prompt_message_id')
            current_text = _bot.get_chat(user_id).text or ""
            _bot.edit_message_text(f"{messages.INVALID_RECEIPT_FORMAT}\n\n{current_text}", user_id, prompt_id)
            return

        # دریافت اطلاعات لازم از وضعیت کاربر
        order_data = state_data['data']
        user_db_info = _db_manager.get_user_by_telegram_id(user_id)
        if not user_db_info:
            _bot.send_message(user_id, messages.OPERATION_FAILED)
            _clear_user_state(user_id)
            return

        # ساخت جزئیات سفارش برای ذخیره در دیتابیس
        order_details_for_db = {
            'user_telegram_id': user_id,
            'user_db_id': user_db_info['id'],
            'user_first_name': message.from_user.first_name,
            'server_id': order_data['server_id'],
            'server_name': _db_manager.get_server_by_id(order_data['server_id'])['name'],
            'plan_type': order_data['plan_type'],
            'plan_details': order_data.get('plan_details'),
            'gb_plan_details': order_data.get('gb_plan_details'),
            'requested_gb': order_data.get('requested_gb'),
            'total_price': order_data['total_price'],
            'gateway_name': order_data['gateway_details']['name'],
            'plan_details_text_display': order_data['plan_details_for_admin'],
            'receipt_file_id': message.photo[-1].file_id
        }

        # ثبت پرداخت در دیتابیس
        payment_id = _db_manager.add_payment(
            user_db_info['id'],
            order_data['total_price'],
            message.message_id,
            json.dumps(order_details_for_db)
        )

        if not payment_id:
            _bot.send_message(user_id, messages.RECEIPT_SEND_ERROR)
            _clear_user_state(user_id)
            return

        # --- بخش جدید: ارسال نوتیفیکیشن به ادمین‌ها مستقیماً از اینجا ---
        from config import ADMIN_IDS # ایمپورت لیست ادمین‌ها

        caption = messages.ADMIN_NEW_PAYMENT_NOTIFICATION_DETAILS.format(
            user_first_name=helpers.escape_markdown_v1(order_details_for_db['user_first_name']),
            user_telegram_id=order_details_for_db['user_telegram_id'],
            amount=order_details_for_db['total_price'],
            server_name=helpers.escape_markdown_v1(order_details_for_db['server_name']),
            plan_details=helpers.escape_markdown_v1(order_details_for_db['plan_details_text_display']),
            gateway_name=helpers.escape_markdown_v1(order_details_for_db['gateway_name'])
        )
        markup = inline_keyboards.get_admin_payment_action_menu(payment_id)
        
        # ارسال پیام به تمام ادمین‌ها
        for admin_id in ADMIN_IDS:
            try:
                sent_msg = _bot.send_photo(
                    admin_id,
                    order_details_for_db['receipt_file_id'],
                    caption=messages.ADMIN_NEW_PAYMENT_NOTIFICATION_HEADER + caption,
                    parse_mode='Markdown',
                    reply_markup=markup
                )
                # آیدی پیام ارسال شده به اولین ادمین را برای ویرایش‌های بعدی ذخیره می‌کنیم
                if admin_id == ADMIN_IDS[0]:
                    _db_manager.update_payment_admin_notification_id(payment_id, sent_msg.message_id)
            except Exception as e:
                logger.error(f"Failed to send payment notification to admin {admin_id}: {e}")
        # --- پایان بخش جدید ---

        _bot.send_message(user_id, messages.RECEIPT_RECEIVED_USER)
        _clear_user_state(user_id)
        _show_user_main_menu(user_id)

    # --- سرویس‌های من ---
    def show_service_details(user_id, purchase_id, message):
        purchase = _db_manager.get_purchase_by_id(purchase_id)
        if not purchase:
            _bot.edit_message_text(messages.OPERATION_FAILED, user_id, message.message_id)
            return
            
        sub_link = ""
        server = _db_manager.get_server_by_id(purchase['server_id'])
        if server and purchase['subscription_id']:
            sub_base = server['subscription_base_url'].rstrip('/')
            sub_path = server['subscription_path_prefix'].strip('/')
            sub_link = f"{sub_base}/{sub_path}/{purchase['subscription_id']}"
        
        if sub_link:
            # --- بخش اصلاح شده ---
            # فراخوانی escape_markdown_v1 از اینجا نیز حذف شد
            text = messages.CONFIG_DELIVERY_HEADER + \
                messages.CONFIG_DELIVERY_SUB_LINK.format(sub_link=sub_link)
            
            # ساخت کیبورد با دکمه‌های بازگشت و دریافت کانفیگ تکی
            markup = types.InlineKeyboardMarkup()
            btn_single_configs = types.InlineKeyboardButton(messages.GET_SINGLE_CONFIGS_BUTTON, callback_data=f"user_get_single_configs_{purchase_id}")
            btn_back = types.InlineKeyboardButton("🔙 بازگشت به سرویس‌ها", callback_data="user_my_services")
            markup.add(btn_single_configs)
            markup.add(btn_back)

            _bot.edit_message_text(text, user_id, message.message_id, parse_mode='Markdown', reply_markup=markup)
            
            # ارسال QR کد به صورت یک پیام جدید
            try:
                import qrcode
                from io import BytesIO
                qr_image = qrcode.make(sub_link)
                bio = BytesIO()
                bio.name = 'qrcode.jpeg'
                qr_image.save(bio, 'JPEG')
                bio.seek(0)
                _bot.send_photo(user_id, bio, caption=messages.QR_CODE_CAPTION)
            except Exception as e:
                logger.error(f"Failed to generate or send QR code in service details: {e}")
        else:
            _bot.edit_message_text(messages.OPERATION_FAILED, user_id, message.message_id)
    def send_single_configs(user_id, purchase_id):
        purchase = _db_manager.get_purchase_by_id(purchase_id)
        if not purchase or not purchase['single_configs_json']:
            _bot.send_message(user_id, messages.NO_SINGLE_CONFIGS_AVAILABLE)
            return
            
        configs = purchase['single_configs_json']
        text = messages.SINGLE_CONFIG_HEADER
        for config in configs:
            text += f"**{config['remark']} ({config['protocol']}/{config['network']})**:\n`{config['url']}`\n\n"
        
        _bot.send_message(user_id, text, parse_mode='Markdown')
        
        
    # در فایل handlers/user_handlers.py

    def show_order_summary(user_id, message):
        """نمایش خلاصه سفارش به کاربر با منطق اصلاح شده برای مدت زمان."""
        _user_states[user_id]['state'] = 'confirming_order'
        order_data = _user_states[user_id]['data']
        
        server_info = _db_manager.get_server_by_id(order_data['server_id'])
        summary_text = messages.ORDER_SUMMARY_HEADER
        summary_text += messages.ORDER_SUMMARY_SERVER.format(server_name=server_info['name'])
        
        total_price = 0
        plan_details_for_admin = ""
        
        if order_data['plan_type'] == 'fixed_monthly':
            plan = order_data['plan_details']
            summary_text += messages.ORDER_SUMMARY_PLAN.format(plan_name=plan['name'])
            summary_text += messages.ORDER_SUMMARY_VOLUME.format(volume_gb=plan['volume_gb'])
            duration_days = plan.get('duration_days')
            duration_text = f"{duration_days} روز"
            total_price = plan['price']
            plan_details_for_admin = f"{plan['name']} ({plan['volume_gb']}GB, {duration_days} روز)"

        elif order_data['plan_type'] == 'gigabyte_based':
            gb_plan = order_data['gb_plan_details']
            requested_gb = order_data['requested_gb']
            summary_text += messages.ORDER_SUMMARY_PLAN.format(plan_name=gb_plan['name'])
            summary_text += messages.ORDER_SUMMARY_VOLUME.format(volume_gb=requested_gb)
            
            # --- بخش اصلاح شده ---
            duration_days = gb_plan.get('duration_days') # مقدار ممکن است None باشد
            if duration_days and duration_days > 0:
                duration_text = f"{duration_days} روز"
            else:
                duration_text = "نامحدود"
            # --- پایان بخش اصلاح شده ---
                
            total_price = requested_gb * gb_plan['per_gb_price']
            plan_details_for_admin = f"{gb_plan['name']} ({requested_gb}GB, {duration_text})"

        summary_text += messages.ORDER_SUMMARY_DURATION.format(duration_days=duration_text)
        summary_text += messages.ORDER_SUMMARY_TOTAL_PRICE.format(total_price=total_price)
        summary_text += messages.ORDER_SUMMARY_CONFIRM_PROMPT
        
        order_data['total_price'] = total_price
        order_data['plan_details_for_admin'] = plan_details_for_admin
        
        prompt_id = _user_states[user_id].get('prompt_message_id', message.message_id)
        _bot.edit_message_text(summary_text, user_id, prompt_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_order_confirmation_menu())
        
        
    def handle_free_test_request(user_id, message):
        _bot.edit_message_text(messages.PLEASE_WAIT, user_id, message.message_id)
        user_db_info = _db_manager.get_user_by_telegram_id(user_id)
        if not user_db_info:
            _bot.edit_message_text(messages.OPERATION_FAILED, user_id, message.message_id); return

        if _db_manager.check_free_test_usage(user_db_info['id']):
            _bot.edit_message_text(messages.FREE_TEST_ALREADY_USED, user_id, message.message_id, reply_markup=inline_keyboards.get_back_button("user_main_menu")); return

        active_servers = [s for s in _db_manager.get_all_servers() if s['is_active'] and s['is_online']]
        if not active_servers:
            _bot.edit_message_text(messages.NO_ACTIVE_SERVERS_FOR_BUY, user_id, message.message_id); return
        
        test_server_id = active_servers[0]['id']
        test_volume_gb = 0.1 # 100 MB
        test_duration_days = 1 # 1 day

        from utils.config_generator import ConfigGenerator
        config_gen = ConfigGenerator(_xui_api, _db_manager)
        client_details, sub_link, _ = config_gen.create_client_and_configs(user_id, test_server_id, test_volume_gb, test_duration_days)

        if sub_link:
            print("Free test subscription created successfully.")
            print(f"Subscription Link: {sub_link}")
            _db_manager.record_free_test_usage(user_db_info['id'])
            _bot.delete_message(user_id, message.message_id)
            _bot.send_message(user_id, messages.GET_FREE_TEST_SUCCESS)
            send_subscription_info(user_id, sub_link)
        else:
            _bot.edit_message_text(messages.OPERATION_FAILED, user_id, message.message_id)

    # تابع جدید برای ارسال لینک و QR کد
    def send_subscription_info(user_id, sub_link):
        _bot.send_message(user_id, messages.CONFIG_DELIVERY_HEADER, parse_mode='Markdown')
        
        # Create QR Code in memory
        qr_image = qrcode.make(sub_link)
        bio = BytesIO()
        bio.name = 'qrcode.jpeg'
        qr_image.save(bio, 'JPEG')
        bio.seek(0)

        # Send QR Code
        _bot.send_photo(user_id, bio, caption=messages.QR_CODE_CAPTION)
        
        # Send Subscription Link
        _bot.send_message(user_id, messages.CONFIG_DELIVERY_SUB_LINK.format(sub_link=sub_link), parse_mode='Markdown')

    def show_my_services_list(user_id, message):
        user_db_info = _db_manager.get_user_by_telegram_id(user_id)
        if not user_db_info:
            _bot.edit_message_text(messages.OPERATION_FAILED, user_id, message.message_id)
            return

        purchases = _db_manager.get_user_purchases(user_db_info['id'])
        
        _bot.edit_message_text(
            messages.MY_SERVICES_HEADER,
            user_id,
            message.message_id,
            reply_markup=inline_keyboards.get_my_services_menu(purchases),
            parse_mode='Markdown'
        )