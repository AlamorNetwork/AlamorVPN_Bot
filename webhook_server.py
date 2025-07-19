# webhook_server.py

from flask import Flask, request, render_template
import requests
import json
import logging
import os
import sys
import datetime

# افزودن مسیر پروژه به sys.path تا بتوان ماژول‌ها را پیدا کرد
project_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_path)

# وارد کردن ماژول‌های پروژه
from config import ZARINPAL_SANDBOX, BOT_TOKEN
from database.db_manager import DatabaseManager
from utils.bot_helpers import send_subscription_info
from utils.config_generator import ConfigGenerator
from api_client.xui_api_client import XuiAPIClient
import telebot

# تنظیمات اولیه
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
db_manager = DatabaseManager()
bot = telebot.TeleBot(BOT_TOKEN)
config_gen = ConfigGenerator(XuiAPIClient, db_manager)

# بر اساس وضعیت سندباکس، آدرس صحیح را انتخاب کن
if ZARINPAL_SANDBOX:
    ZARINPAL_VERIFY_URL = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
else:
    ZARINPAL_VERIFY_URL = "https://api.zarinpal.com/pg/v4/payment/verify.json"
BOT_USERNAME = "YourBotUsername" # یوزرنیم ربات خود را اینجا وارد کنید

@app.route('/zarinpal/verify', methods=['GET'])
def handle_zarinpal_callback():
    authority = request.args.get('Authority')
    status = request.args.get('Status')

    logger.info(f"Callback received from Zarinpal >> Status: {status}, Authority: {authority}")

    if not authority or not status:
        return render_template('payment_status.html', status='error', message="اطلاعات بازگشتی از درگاه ناقص است.", bot_username=BOT_USERNAME)

    payment = db_manager.get_payment_by_authority(authority)
    if not payment:
        logger.warning(f"Payment not found for Authority: {authority}")
        return render_template('payment_status.html', status='error', message="تراکنش یافت نشد. ممکن است این لینک منقضی شده باشد.", bot_username=BOT_USERNAME)
    
    user_db_info = db_manager.get_user_by_id(payment['user_id'])
    user_telegram_id = user_db_info['telegram_id']

    if payment['is_confirmed']:
        logger.warning(f"Payment ID {payment['id']} has already been confirmed.")
        return render_template('payment_status.html', status='success', ref_id=payment.get('ref_id'), bot_username=BOT_USERNAME)

    if status == 'OK':
        gateway = db_manager.get_payment_gateway_by_id(json.loads(payment['order_details_json'])['gateway_details']['id'])
        
        payload = {"merchant_id": gateway['merchant_id'], "amount": int(payment['amount']) * 10, "authority": authority}
        
        try:
            response = requests.post(ZARINPAL_VERIFY_URL, json=payload, timeout=20)
            response.raise_for_status()
            result = response.json()

            if result.get("data") and result.get("data", {}).get("code") in [100, 101]:
                ref_id = result.get("data", {}).get("ref_id", "N/A")
                logger.info(f"Payment {payment['id']} verified successfully. Ref ID: {ref_id}")
                
                order_details = json.loads(payment['order_details_json'])
                
                if order_details['plan_type'] == 'fixed_monthly':
                    plan = order_details['plan_details']
                    total_gb, duration_days = plan['volume_gb'], plan['duration_days']
                else:
                    gb_plan = order_details['gb_plan_details']
                    total_gb, duration_days = order_details['requested_gb'], gb_plan.get('duration_days', 0)
                
                client_details, sub_link, _ = config_gen.create_client_and_configs(user_telegram_id, order_details['server_id'], total_gb, duration_days)
                
                if sub_link:
                    db_manager.confirm_online_payment(payment['id'], str(ref_id))
                    bot.send_message(user_telegram_id, "✅ پرداخت شما با موفقیت تایید و سرویس شما فعال گردید.")
                    send_subscription_info(bot, user_telegram_id, sub_link)
                else:
                    bot.send_message(user_telegram_id, "❌ در فعال‌سازی سرویس شما خطایی رخ داد. لطفاً با پشتیبانی تماس بگیرید.")
                
                return render_template('payment_status.html', status='success', ref_id=ref_id, bot_username=BOT_USERNAME)
            else:
                error_message = result.get("errors", {}).get("message", "خطای نامشخص")
                bot.send_message(user_telegram_id, f"❌ پرداخت شما توسط درگاه تایید نشد. لطفاً با پشتیبانی تماس بگیرید. (خطا: {error_message})")
                return render_template('payment_status.html', status='error', message=error_message, bot_username=BOT_USERNAME)

        except requests.exceptions.RequestException as e:
            logger.error(f"Error verifying with Zarinpal: {e}")
            return render_template('payment_status.html', status='error', message="خطا در ارتباط با سرور درگاه پرداخت.", bot_username=BOT_USERNAME)
    else:
        bot.send_message(user_telegram_id, "شما فرآیند پرداخت را لغو کردید. سفارش شما ناتمام باقی ماند.")
        return render_template('payment_status.html', status='error', message="تراکنش توسط شما لغو شد.", bot_username=BOT_USERNAME)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)