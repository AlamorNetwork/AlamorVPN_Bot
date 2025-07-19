# database/db_manager.py

import sqlite3
import logging
from cryptography.fernet import Fernet
import os
import json

from config import ENCRYPTION_KEY, DATABASE_NAME

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path=DATABASE_NAME):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.fernet = Fernet(ENCRYPTION_KEY)
        logger.info(f"DatabaseManager initialized with DB: {self.db_path}")

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def create_tables(self):
        """
        جداول لازم را در دیتابیس ایجاد می‌کند اگر وجود نداشته باشند.
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # جدول کاربران
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    username TEXT,
                    is_admin BOOLEAN DEFAULT FALSE,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # جدول سرورها
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    panel_url TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    subscription_base_url TEXT NOT NULL,
                    subscription_path_prefix TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_online BOOLEAN DEFAULT FALSE
                )
            """)
            
            # جدول پلن‌ها
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    plan_type TEXT NOT NULL,
                    volume_gb REAL,
                    duration_days INTEGER,
                    price REAL,
                    per_gb_price REAL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            
            # جدول Inboundهای پیکربندی شده برای هر سرور
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS server_inbounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id INTEGER NOT NULL,
                    inbound_id INTEGER NOT NULL,
                    remark TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (server_id) REFERENCES servers (id) ON DELETE CASCADE,
                    UNIQUE (server_id, inbound_id)
                )
            """)

            # جدول خریدها
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    server_id INTEGER NOT NULL,
                    plan_id INTEGER,
                    purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expire_date TIMESTAMP,
                    initial_volume_gb REAL NOT NULL,
                    xui_client_uuid TEXT,
                    xui_client_email TEXT,
                    subscription_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    single_configs_json TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (server_id) REFERENCES servers (id),
                    FOREIGN KEY (plan_id) REFERENCES plans (id)
                )
            """)

            # جدول درگاه‌های پرداخت
            cursor.execute("""
                    CREATE TABLE IF NOT EXISTS payment_gateways (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        type TEXT NOT NULL,
                        card_number TEXT,
                        card_holder_name TEXT,
                        merchant_id TEXT,
                        description TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        priority INTEGER DEFAULT 0
                    )
                """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS free_test_usage (
                    user_id INTEGER PRIMARY KEY,
                    usage_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)
                
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    receipt_message_id INTEGER,
                    is_confirmed BOOLEAN DEFAULT FALSE,
                    admin_confirmed_by INTEGER,
                    confirmation_date TIMESTAMP,
                    order_details_json TEXT,
                    admin_notification_message_id INTEGER,
                    authority TEXT,
                    ref_id TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)


            conn.commit()
            logger.info("Database tables created or already exist.")
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            raise e
        finally:
            if conn:
                conn.close()

    def _encrypt(self, data):
        if data is None: return None
        if isinstance(data, str):
            data = data.encode('utf-8')
        return self.fernet.encrypt(data).decode('utf-8')

    def _decrypt(self, encrypted_data):
        if encrypted_data is None: return None
        if isinstance(encrypted_data, str):
            encrypted_data = encrypted_data.encode('utf-8')
        return self.fernet.decrypt(encrypted_data).decode('utf-8')

    # --- توابع کاربران ---
    def add_or_update_user(self, telegram_id, first_name, last_name=None, username=None):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (telegram_id, first_name, last_name, username, last_activity)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    username = excluded.username,
                    last_activity = CURRENT_TIMESTAMP
            """, (telegram_id, first_name, last_name, username))
            conn.commit()
            logger.info(f"User {telegram_id} added or updated.")
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error adding/updating user {telegram_id}: {e}")
            return None
        finally:
            if conn: conn.close()
            
    def get_all_users(self):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, telegram_id, first_name, username, join_date FROM users ORDER BY id DESC")
            users = cursor.fetchall()
            return [dict(user) for user in users]
        except sqlite3.Error as e:
            logger.error(f"Error getting all users: {e}")
            return []
        finally:
            if conn: conn.close()

    def get_user_by_telegram_id(self, telegram_id):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            user = cursor.fetchone()
            return dict(user) if user else None
        except sqlite3.Error as e:
            logger.error(f"Error getting user by telegram_id {telegram_id}: {e}")
            return None
        finally:
            if conn: conn.close()

    def get_user_by_id(self, user_db_id):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_db_id,))
            user = cursor.fetchone()
            return dict(user) if user else None
        except sqlite3.Error as e:
            logger.error(f"Error getting user by DB ID {user_db_id}: {e}")
            return None
        finally:
            if conn: conn.close()

    # --- توابع سرورها ---
    def add_server(self, name, panel_url, username, password, sub_base_url, sub_path_prefix):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO servers (name, panel_url, username, password, subscription_base_url, subscription_path_prefix)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, self._encrypt(panel_url), self._encrypt(username), self._encrypt(password), self._encrypt(sub_base_url), self._encrypt(sub_path_prefix)))
            conn.commit()
            logger.info(f"Server '{name}' added successfully.")
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.warning(f"Server with name '{name}' already exists.")
            return None
        except sqlite3.Error as e:
            logger.error(f"Error adding server '{name}': {e}")
            return None
        finally:
            if conn: conn.close()

    def get_all_servers(self):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM servers ORDER BY id")
            servers_data = cursor.fetchall()
            
            decrypted_servers = []
            for server in servers_data:
                server_dict = dict(server)
                server_dict['panel_url'] = self._decrypt(server_dict['panel_url'])
                server_dict['username'] = self._decrypt(server_dict['username'])
                server_dict['password'] = self._decrypt(server_dict['password'])
                server_dict['subscription_base_url'] = self._decrypt(server_dict['subscription_base_url'])
                server_dict['subscription_path_prefix'] = self._decrypt(server_dict['subscription_path_prefix'])
                decrypted_servers.append(server_dict)
            return decrypted_servers
        except sqlite3.Error as e:
            logger.error(f"Error getting all servers: {e}")
            return []
        finally:
            if conn: conn.close()
            
    def get_server_by_id(self, server_id):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM servers WHERE id = ?", (server_id,))
            server = cursor.fetchone()
            if server:
                server_dict = dict(server)
                server_dict['panel_url'] = self._decrypt(server_dict['panel_url'])
                server_dict['username'] = self._decrypt(server_dict['username'])
                server_dict['password'] = self._decrypt(server_dict['password'])
                server_dict['subscription_base_url'] = self._decrypt(server_dict['subscription_base_url'])
                server_dict['subscription_path_prefix'] = self._decrypt(server_dict['subscription_path_prefix'])
                return server_dict
            return None
        except sqlite3.Error as e:
            logger.error(f"Error getting server by ID {server_id}: {e}")
            return None
        finally:
            if conn: conn.close()

    def delete_server(self, server_id):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            # Deleting a server will cascade and delete related inbounds
            cursor.execute("DELETE FROM servers WHERE id = ?", (server_id,))
            conn.commit()
            logger.info(f"Server with ID {server_id} has been deleted.")
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error deleting server with ID {server_id}: {e}")
            return False
        finally:
            if conn: conn.close()

    def update_server_status(self, server_id, is_online, last_checked):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE servers SET is_online = ?, last_checked = ? WHERE id = ?
            """, (is_online, last_checked, server_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating server status for ID {server_id}: {e}")
            return False
        finally:
            if conn: conn.close()

    # --- توابع Inboundهای سرور ---
    def get_server_inbounds(self, server_id, only_active=True):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = "SELECT * FROM server_inbounds WHERE server_id = ?"
            params = [server_id]
            if only_active:
                query += " AND is_active = TRUE"
            cursor.execute(query, params)
            inbounds = cursor.fetchall()
            return [dict(inbound) for inbound in inbounds]
        except sqlite3.Error as e:
            logger.error(f"Error getting inbounds for server {server_id}: {e}")
            return []
        finally:
            if conn: conn.close()

    def update_server_inbounds(self, server_id, selected_inbounds: list):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            # First, remove all existing inbounds for this server
            cursor.execute("DELETE FROM server_inbounds WHERE server_id = ?", (server_id,))
            # Then, insert the new selection
            if selected_inbounds:
                inbounds_to_insert = [
                    (server_id, inbound['id'], inbound['remark'], True)
                    for inbound in selected_inbounds
                ]
                cursor.executemany("""
                    INSERT INTO server_inbounds (server_id, inbound_id, remark, is_active)
                    VALUES (?, ?, ?, ?)
                """, inbounds_to_insert)
            conn.commit()
            logger.info(f"Updated inbounds for server ID {server_id}.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating inbounds for server ID {server_id}: {e}")
            conn.rollback()
            return False
        finally:
            if conn: conn.close()

    # --- توابع پلن‌ها ---
    def add_plan(self, name, plan_type, volume_gb, duration_days, price, per_gb_price):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO plans (name, plan_type, volume_gb, duration_days, price, per_gb_price, is_active)
                VALUES (?, ?, ?, ?, ?, ?, TRUE)
            """, (name, plan_type, volume_gb, duration_days, price, per_gb_price))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None
        except sqlite3.Error as e:
            logger.error(f"Error adding plan '{name}': {e}")
            return None
        finally:
            if conn: conn.close()

    def get_all_plans(self, only_active=False):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = "SELECT * FROM plans"
            if only_active:
                query += " WHERE is_active = TRUE"
            query += " ORDER BY price"
            cursor.execute(query)
            plans = cursor.fetchall()
            return [dict(plan) for plan in plans]
        except sqlite3.Error as e:
            logger.error(f"Error getting plans: {e}")
            return []
        finally:
            if conn: conn.close()
            
    def get_plan_by_id(self, plan_id):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
            plan = cursor.fetchone()
            return dict(plan) if plan else None
        except sqlite3.Error as e:
            logger.error(f"Error getting plan by ID {plan_id}: {e}")
            return None
        finally:
            if conn: conn.close()
            
    def update_plan_status(self, plan_id, is_active):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE plans SET is_active = ? WHERE id = ?", (is_active, plan_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating plan status for ID {plan_id}: {e}")
            return False
        finally:
            if conn: conn.close()
            
    # --- توابع درگاه پرداخت ---
    def add_payment_gateway(self, name: str, gateway_type: str, card_number: str = None, card_holder_name: str = None, merchant_id: str = None, description: str = None, priority: int = 0):
        """یک درگاه پرداخت جدید را با تمام اطلاعات لازم اضافه می‌کند."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # رمزنگاری اطلاعات حساس
            encrypted_card_number = self._encrypt(card_number) if card_number else None
            encrypted_card_holder_name = self._encrypt(card_holder_name) if card_holder_name else None
            encrypted_merchant_id = self._encrypt(merchant_id) if merchant_id else None

            cursor.execute("""
                INSERT INTO payment_gateways (name, type, card_number, card_holder_name, merchant_id, description, is_active, priority)
                VALUES (?, ?, ?, ?, ?, ?, TRUE, ?)
            """, (name, gateway_type, encrypted_card_number, encrypted_card_holder_name, encrypted_merchant_id, description, priority))
            conn.commit()
            logger.info(f"Payment Gateway '{name}' ({gateway_type}) added successfully.")
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.warning(f"Payment Gateway with name '{name}' already exists.")
            return None
        except sqlite3.Error as e:
            logger.error(f"Error adding payment gateway '{name}': {e}")
            return None
        finally:
            if conn: conn.close()

    def get_all_payment_gateways(self, only_active=False):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = "SELECT * FROM payment_gateways"
            if only_active:
                query += " WHERE is_active = TRUE"
            query += " ORDER BY priority DESC, id"
            cursor.execute(query)
            gateways = cursor.fetchall()
            
            decrypted_gateways = []
            for gateway in gateways:
                gateway_dict = dict(gateway)
                # رمزگشایی اطلاعات حساس
                if gateway_dict.get('card_number'):
                    gateway_dict['card_number'] = self._decrypt(gateway_dict['card_number'])
                if gateway_dict.get('card_holder_name'):
                    gateway_dict['card_holder_name'] = self._decrypt(gateway_dict['card_holder_name'])
                
                # --- بخش اصلاح شده ---
                # رمزگشایی مرچنت کد اضافه شد
                if gateway_dict.get('merchant_id'):
                    gateway_dict['merchant_id'] = self._decrypt(gateway_dict['merchant_id'])
                # --- پایان بخش اصلاح شده ---

                decrypted_gateways.append(gateway_dict)
            return decrypted_gateways
        except Exception as e:
            logger.error(f"Error getting payment gateways: {e}")
            return []
        finally:
            if conn: conn.close()

    def get_payment_gateway_by_id(self, gateway_id):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM payment_gateways WHERE id = ?", (gateway_id,))
            gateway = cursor.fetchone()
            if gateway:
                gateway_dict = dict(gateway)
                # رمزگشایی اطلاعات حساس
                if gateway_dict.get('card_number'):
                    gateway_dict['card_number'] = self._decrypt(gateway_dict['card_number'])
                if gateway_dict.get('card_holder_name'):
                    gateway_dict['card_holder_name'] = self._decrypt(gateway_dict['card_holder_name'])
                
                # --- بخش اصلاح شده ---
                # رمزگشایی مرچنت کد اضافه شد
                if gateway_dict.get('merchant_id'):
                    gateway_dict['merchant_id'] = self._decrypt(gateway_dict['merchant_id'])
                # --- پایان بخش اصلاح شده ---

                return gateway_dict
            return None
        except Exception as e:
            logger.error(f"Error getting payment gateway {gateway_id}: {e}")
            return None
        finally:
            if conn: conn.close()

    def update_payment_gateway_status(self, gateway_id, is_active):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE payment_gateways SET is_active = ? WHERE id = ?", (is_active, gateway_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating gateway status for ID {gateway_id}: {e}")
            return False
        finally:
            if conn: conn.close()

    # --- توابع پرداخت‌ها (Payments) ---
    def add_payment(self, user_id, amount, receipt_message_id, order_details_json):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO payments (user_id, amount, receipt_message_id, order_details_json, is_confirmed)
                VALUES (?, ?, ?, ?, FALSE)
            """, (user_id, amount, receipt_message_id, order_details_json))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error adding payment request for user {user_id}: {e}")
            return None
        finally:
            if conn: conn.close()

    def get_payment_by_id(self, payment_id):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
            payment = cursor.fetchone()
            return dict(payment) if payment else None
        except sqlite3.Error as e:
            logger.error(f"Error getting payment {payment_id}: {e}")
            return None
        finally:
            if conn: conn.close()

    def update_payment_status(self, payment_id, is_confirmed, admin_id=None):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE payments 
                SET is_confirmed = ?, admin_confirmed_by = ?, confirmation_date = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (is_confirmed, admin_id, payment_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating payment status for ID {payment_id}: {e}")
            return False
        finally:
            if conn: conn.close()
            
    def update_payment_admin_notification_id(self, payment_id, message_id):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE payments SET admin_notification_message_id = ? WHERE id = ?", (message_id, payment_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating admin notification message ID for payment {payment_id}: {e}")
            return False
        finally:
            if conn: conn.close()

    # --- توابع خریدها (Purchases) ---
    def add_purchase(self, user_id, server_id, plan_id, expire_date, initial_volume_gb, client_uuid, client_email, sub_id, single_configs):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO purchases (user_id, server_id, plan_id, expire_date, initial_volume_gb, xui_client_uuid, xui_client_email, subscription_id, single_configs_json, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE)
            """, (user_id, server_id, plan_id, expire_date, initial_volume_gb, client_uuid, client_email, sub_id, json.dumps(single_configs)))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error adding purchase for user {user_id}: {e}")
            return None
        finally:
            if conn: conn.close()

    def get_user_purchases(self, user_db_id):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.id, p.purchase_date, p.expire_date, p.initial_volume_gb, p.is_active, s.name as server_name
                FROM purchases p
                JOIN servers s ON p.server_id = s.id
                WHERE p.user_id = ?
                ORDER BY p.id DESC
            """, (user_db_id,))
            purchases = cursor.fetchall()
            return [dict(p) for p in purchases]
        except sqlite3.Error as e:
            logger.error(f"Error getting purchases for user DB ID {user_db_id}: {e}")
            return []
        finally:
            if conn: conn.close()
            
    def get_purchase_by_id(self, purchase_id):
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
            purchase = cursor.fetchone()
            if purchase:
                purchase_dict = dict(purchase)
                purchase_dict['single_configs_json'] = json.loads(purchase_dict['single_configs_json'] or '[]')
                return purchase_dict
            return None
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Error getting purchase by ID {purchase_id}: {e}")
            return None
        finally:
            if conn: conn.close()
            
            
    def check_free_test_usage(self, user_db_id: int) -> bool:
        """بررسی می‌کند آیا کاربر قبلاً از تست رایگان استفاده کرده است."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM free_test_usage WHERE user_id = ?", (user_db_id,))
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Error checking free test usage for user {user_db_id}: {e}")
            return True # در صورت خطا، فرض می‌کنیم استفاده کرده تا از سوءاستفاده جلوگیری شود
        finally:
            if conn: conn.close()

    def record_free_test_usage(self, user_db_id: int):
        """استفاده کاربر از تست رایگان را ثبت می‌کند."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO free_test_usage (user_id) VALUES (?)", (user_db_id,))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error recording free test usage for user {user_db_id}: {e}")
            return False

    def reset_free_test_usage(self, user_db_id: int):
        """به ادمین اجازه می‌دهد دسترسی کاربر به تست رایگان را ریست کند."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM free_test_usage WHERE user_id = ?", (user_db_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error resetting free test usage for user {user_db_id}: {e}")
            return False
        
        
        
    # در فایل database/db_manager.py

    def get_payment_by_authority(self, authority: str):
        """پرداخت را بر اساس شناسه Authority زرین‌پال پیدا می‌کند."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM payments WHERE authority = ?", (authority,))
            payment = cursor.fetchone()
            return dict(payment) if payment else None
        except sqlite3.Error as e:
            logger.error(f"Error getting payment by authority {authority}: {e}")
            return None
        finally:
            if conn: conn.close()

    def confirm_online_payment(self, payment_id: int, ref_id: str):
        """وضعیت یک پرداخت آنلاین را به 'تایید شده' تغییر داده و کد رهگیری را ذخیره می‌کند."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE payments 
                SET is_confirmed = TRUE, ref_id = ?, confirmation_date = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (ref_id, payment_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error confirming online payment for ID {payment_id}: {e}")
            return False
        finally:
            if conn: conn.close()
            
            
            
    def set_payment_authority(self, payment_id: int, authority: str):
        """شناسه authority را برای یک رکورد پرداخت ثبت می‌کند."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE payments SET authority = ? WHERE id = ?", (authority, payment_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error setting authority for payment ID {payment_id}: {e}")
            return False
        finally:
            if conn: conn.close()