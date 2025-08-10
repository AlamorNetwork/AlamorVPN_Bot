# database/db_manager.py

import psycopg2
import psycopg2.extras
import logging
from cryptography.fernet import Fernet
import os
import json
from config import ENCRYPTION_KEY, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.db_name = DB_NAME
        self.db_user = DB_USER
        self.db_password = DB_PASSWORD
        self.db_host = DB_HOST
        self.db_port = DB_PORT
        self.fernet = Fernet(ENCRYPTION_KEY.encode('utf-8'))
        logger.info(f"DatabaseManager initialized for PostgreSQL DB: {self.db_name}")

    def _get_connection(self):
        """Establishes a new connection to the PostgreSQL database."""
        return psycopg2.connect(
            dbname=self.db_name, user=self.db_user, password=self.db_password,
            host=self.db_host, port=self.db_port
        )

    def _encrypt(self, data: str) -> str:
        if data is None: return None
        return self.fernet.encrypt(data.encode('utf-8')).decode('utf-8')

    def _decrypt(self, encrypted_data: str) -> str:
        if encrypted_data is None: return None
        return self.fernet.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')

    def create_tables(self):
        """
        جداول لازم را با ترتیب صحیح وابستگی‌ها در دیتاب斯 PostgreSQL ایجاد می‌کند. (نسخه نهایی و کامل)
        """
        # --- لیست کامل دستورات ساخت جداول با ترتیب صحیح ---
        commands = [
            # --- بخش ۱: جداول پایه (بدون وابستگی به جداول دیگر پروژه) ---
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                is_admin BOOLEAN DEFAULT FALSE, 
                join_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS servers (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                panel_type TEXT NOT NULL DEFAULT 'x-ui',
                panel_url TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                subscription_base_url TEXT NOT NULL,
                subscription_path_prefix TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                last_checked TIMESTAMPTZ,
                is_online BOOLEAN DEFAULT FALSE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                plan_type TEXT NOT NULL,
                volume_gb REAL,
                duration_days INTEGER,
                price REAL,
                per_gb_price REAL,
                is_active BOOLEAN DEFAULT TRUE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tutorials (
                id SERIAL PRIMARY KEY,
                platform TEXT NOT NULL,
                app_name TEXT NOT NULL,
                forward_chat_id BIGINT NOT NULL,
                forward_message_id BIGINT NOT NULL,
                UNIQUE (platform, app_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                per_gb_price REAL NOT NULL,
                duration_days INTEGER NOT NULL,
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS subscription_domains (
                id SERIAL PRIMARY KEY,
                domain_name TEXT UNIQUE NOT NULL,
                is_active BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS payment_gateways (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,
                card_number TEXT,
                card_holder_name TEXT,
                merchant_id TEXT,
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                priority INTEGER DEFAULT 0
            )
            """,
            # --- بخش ۲: جداول وابسته (دارای Foreign Key به جداول پایه) ---
            """
            CREATE TABLE IF NOT EXISTS synced_configs (
                id SERIAL PRIMARY KEY,
                server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
                inbound_id INTEGER NOT NULL,
                remark TEXT,
                port INTEGER,
                protocol TEXT,
                settings TEXT,
                stream_settings TEXT,
                UNIQUE (server_id, inbound_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS server_inbounds (
                id SERIAL PRIMARY KEY,
                server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
                inbound_id INTEGER NOT NULL,
                remark TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                UNIQUE (server_id, inbound_id)
            )
            CREATE TABLE IF NOT EXISTS profile_inbounds (
                id SERIAL PRIMARY KEY,
                profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
                inbound_id INTEGER NOT NULL,
                UNIQUE (profile_id, server_id, inbound_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
                plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
                profile_id INTEGER REFERENCES profiles(id) ON DELETE SET NULL,
                purchase_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                expire_date TIMESTAMPTZ,
                initial_volume_gb REAL NOT NULL,
                client_uuid TEXT,
                client_email TEXT,
                sub_id TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                single_configs_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS free_test_usage (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                usage_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                amount REAL NOT NULL,
                payment_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                receipt_message_id BIGINT,
                is_confirmed BOOLEAN DEFAULT FALSE,
                admin_confirmed_by BIGINT,
                confirmation_date TIMESTAMPTZ,
                order_details_json TEXT,
                admin_notification_message_id BIGINT,
                authority TEXT,
                ref_id TEXT
            )
            """
        ]
        
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                logger.info("Dropping potentially outdated tables (purchases, payments) to ensure schema is up-to-date...")
                cur.execute("DROP TABLE IF EXISTS purchases CASCADE;")
                cur.execute("DROP TABLE IF EXISTS payments CASCADE;")

                logger.info("Creating all tables in the correct order...")
                for command in commands:
                    cur.execute(command)

            conn.commit()
            logger.info("Database tables created or updated successfully.")
        except psycopg2.Error as e:
            logger.error(f"Error creating PostgreSQL tables: {e}")
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()

    def _decrypt_server_row(self, server_row: psycopg2.extras.DictRow) -> dict or None:
        """Helper function to decrypt a single server record."""
        if not server_row:
            return None
        server_dict = dict(server_row)
        try:
            server_dict['panel_url'] = self._decrypt(server_dict['panel_url'])
            server_dict['username'] = self._decrypt(server_dict['username'])
            server_dict['password'] = self._decrypt(server_dict['password'])
            server_dict['subscription_base_url'] = self._decrypt(server_dict['subscription_base_url'])
            server_dict['subscription_path_prefix'] = self._decrypt(server_dict['subscription_path_prefix'])
            return server_dict
        except Exception as e:
            logger.error(f"Could not decrypt credentials for server ID {server_dict.get('id')}: {e}")
            return None

    # --- User Functions ---
    def add_or_update_user(self, telegram_id, first_name, last_name=None, username=None):
        sql = """
            INSERT INTO users (telegram_id, first_name, last_name, username, last_activity)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (telegram_id) DO UPDATE SET
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                username = EXCLUDED.username,
                last_activity = CURRENT_TIMESTAMP
            RETURNING id;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (telegram_id, first_name, last_name, username))
                    user_id = cursor.fetchone()[0]
                    conn.commit()
                    logger.info(f"User {telegram_id} added or updated.")
                    return user_id
        except psycopg2.Error as e:
            logger.error(f"Error adding/updating user {telegram_id}: {e}")
            return None

    def get_all_users(self):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT id, telegram_id, first_name, username, join_date FROM users ORDER BY id DESC")
                    return [dict(user) for user in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting all users: {e}")
            return []

    def get_user_by_telegram_id(self, telegram_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
                    user = cursor.fetchone()
                    return dict(user) if user else None
        except psycopg2.Error as e:
            logger.error(f"Error getting user by telegram_id {telegram_id}: {e}")
            return None

    def get_user_by_id(self, user_db_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM users WHERE id = %s", (user_db_id,))
                    user = cursor.fetchone()
                    return dict(user) if user else None
        except psycopg2.Error as e:
            logger.error(f"Error getting user by DB ID {user_db_id}: {e}")
            return None

    # --- Server Functions ---
    def add_server(self, name, panel_type, panel_url, username, password, sub_base_url, sub_path_prefix):
        sql = """
            INSERT INTO servers (name, panel_type, panel_url, username, password, subscription_base_url, subscription_path_prefix) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    encrypted_data = (
                        name, panel_type, self._encrypt(panel_url), self._encrypt(username),
                        self._encrypt(password), self._encrypt(sub_base_url), self._encrypt(sub_path_prefix)
                    )
                    cursor.execute(sql, encrypted_data)
                    server_id = cursor.fetchone()[0]
                    conn.commit()
                    return server_id
        except psycopg2.IntegrityError:
            logger.warning(f"A server with the name '{name}' already exists.")
            return None
        except psycopg2.Error as e:
            logger.error(f"Error adding server '{name}': {e}")
            return None

    def get_all_servers(self, only_active=True):
        query = "SELECT * FROM servers"
        if only_active:
            query += " WHERE is_active = TRUE AND is_online = TRUE"
        
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(query)
                    servers_data = cursor.fetchall()
                    decrypted_list = [self._decrypt_server_row(row) for row in servers_data]
                    return [s for s in decrypted_list if s is not None]
        except psycopg2.Error as e:
            logger.error(f"Error getting all servers: {e}")
            return []
                
    def get_server_by_id(self, server_id: int):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM servers WHERE id = %s", (server_id,))
                    server_row = cursor.fetchone()
                    return self._decrypt_server_row(server_row)
        except psycopg2.Error as e:
            logger.error(f"Error getting server by ID {server_id}: {e}")
            return None

    def delete_server(self, server_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM servers WHERE id = %s", (server_id,))
                    conn.commit()
                    logger.info(f"Server with ID {server_id} has been deleted.")
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error deleting server with ID {server_id}: {e}")
            return False

    def update_server_status(self, server_id, is_online, last_checked):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE servers SET is_online = %s, last_checked = %s WHERE id = %s",
                        (is_online, last_checked, server_id)
                    )
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating server status for ID {server_id}: {e}")
            return False

    # --- Server Inbound Functions ---
    def get_server_inbounds(self, server_id, only_active=True):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    query = "SELECT * FROM server_inbounds WHERE server_id = %s"
                    params = [server_id]
                    if only_active:
                        query += " AND is_active = TRUE"
                    cursor.execute(query, tuple(params))
                    return [dict(inbound) for inbound in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting inbounds for server {server_id}: {e}")
            return []

    def update_server_inbounds(self, server_id, selected_inbounds: list):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM server_inbounds WHERE server_id = %s", (server_id,))
                    if selected_inbounds:
                        inbounds_to_insert = [
                            (server_id, inbound['id'], inbound['remark'], True)
                            for inbound in selected_inbounds
                        ]
                        psycopg2.extras.execute_values(
                            cursor,
                            "INSERT INTO server_inbounds (server_id, inbound_id, remark, is_active) VALUES %s",
                            inbounds_to_insert
                        )
                    conn.commit()
                    logger.info(f"Updated inbounds for server ID {server_id}.")
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating inbounds for server ID {server_id}: {e}")
            return False
            
    def update_active_inbounds_for_server(self, server_id: int, active_inbound_ids: list):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE server_inbounds SET is_active = FALSE WHERE server_id = %s", (server_id,))
                    if active_inbound_ids:
                        query = "UPDATE server_inbounds SET is_active = TRUE WHERE server_id = %s AND inbound_id = ANY(%s)"
                        cursor.execute(query, (server_id, active_inbound_ids))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating active inbounds for server {server_id}: {e}")
            return False

    # --- Plan Functions ---
    def add_plan(self, name, plan_type, volume_gb, duration_days, price, per_gb_price):
        sql = """
            INSERT INTO plans (name, plan_type, volume_gb, duration_days, price, per_gb_price, is_active) 
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            RETURNING id;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (name, plan_type, volume_gb, duration_days, price, per_gb_price))
                    plan_id = cursor.fetchone()[0]
                    conn.commit()
                    logger.info(f"Successfully added plan '{name}' with ID {plan_id}.")
                    return plan_id
        except psycopg2.IntegrityError:
            logger.warning(f"Plan with name '{name}' already exists.")
            return None
        except psycopg2.Error as e:
            logger.error(f"A database error occurred while adding plan '{name}': {e}")
            return None

    def get_all_plans(self, only_active=False):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    query = "SELECT * FROM plans"
                    if only_active:
                        query += " WHERE is_active = TRUE"
                    query += " ORDER BY price"
                    cursor.execute(query)
                    return [dict(plan) for plan in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting plans: {e}")
            return []

    def get_plan_by_id(self, plan_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM plans WHERE id = %s", (plan_id,))
                    plan = cursor.fetchone()
                    return dict(plan) if plan else None
        except psycopg2.Error as e:
            logger.error(f"Error getting plan by ID {plan_id}: {e}")
            return None
    
    def update_plan(self, plan_id: int, name: str, price: float, volume_gb: float, duration_days: int) -> bool:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE plans SET name = %s, price = %s, volume_gb = %s, duration_days = %s
                        WHERE id = %s
                    """, (name, price, volume_gb, duration_days, plan_id))
                    conn.commit()
                    logger.info(f"Plan with ID {plan_id} has been updated.")
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error updating plan {plan_id}: {e}")
            return False
            
    def delete_plan(self, plan_id: int) -> bool:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM plans WHERE id = %s", (plan_id,))
                    conn.commit()
                    logger.info(f"Plan with ID {plan_id} has been deleted.")
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error deleting plan with ID {plan_id}: {e}")
            return False

    def get_plans_for_server(self, server_id: int, plan_type: str = 'fixed_monthly'):
        # This function seems to have a logical error as plans are not tied to servers directly.
        # Assuming a global plan system as per the schema.
        # If plans were per server, the 'plans' table would need a 'server_id' column.
        # Re-implementing based on global plans.
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(
                        "SELECT * FROM plans WHERE plan_type = %s AND is_active = TRUE ORDER BY price",
                        (plan_type,)
                    )
                    return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting plans for type {plan_type}: {e}")
            return []

    # --- Payment Gateway Functions ---
    def add_payment_gateway(self, name: str, gateway_type: str, card_number: str = None, card_holder_name: str = None, merchant_id: str = None, description: str = None, priority: int = 0):
        sql = """
            INSERT INTO payment_gateways (name, type, card_number, card_holder_name, merchant_id, description, is_active, priority)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
            RETURNING id;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    encrypted_card_number = self._encrypt(card_number) if card_number else None
                    encrypted_card_holder_name = self._encrypt(card_holder_name) if card_holder_name else None
                    encrypted_merchant_id = self._encrypt(merchant_id) if merchant_id else None
                    params = (name, gateway_type, encrypted_card_number, encrypted_card_holder_name, encrypted_merchant_id, description, priority)
                    cursor.execute(sql, params)
                    gateway_id = cursor.fetchone()[0]
                    conn.commit()
                    logger.info(f"Payment Gateway '{name}' ({gateway_type}) added successfully.")
                    return gateway_id
        except psycopg2.IntegrityError:
            logger.warning(f"Payment Gateway with name '{name}' already exists.")
            return None
        except psycopg2.Error as e:
            logger.error(f"Error adding payment gateway '{name}': {e}")
            return None

    def get_all_payment_gateways(self, only_active=False):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    query = "SELECT * FROM payment_gateways"
                    if only_active:
                        query += " WHERE is_active = TRUE"
                    query += " ORDER BY priority DESC, id"
                    cursor.execute(query)
                    gateways = cursor.fetchall()
                    
                    decrypted_gateways = []
                    for gateway in gateways:
                        gateway_dict = dict(gateway)
                        if gateway_dict.get('card_number'):
                            gateway_dict['card_number'] = self._decrypt(gateway_dict['card_number'])
                        if gateway_dict.get('card_holder_name'):
                            gateway_dict['card_holder_name'] = self._decrypt(gateway_dict['card_holder_name'])
                        if gateway_dict.get('merchant_id'):
                            gateway_dict['merchant_id'] = self._decrypt(gateway_dict['merchant_id'])
                        decrypted_gateways.append(gateway_dict)
                    return decrypted_gateways
        except Exception as e:
            logger.error(f"Error getting payment gateways: {e}")
            return []

    def get_payment_gateway_by_id(self, gateway_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM payment_gateways WHERE id = %s", (gateway_id,))
                    gateway = cursor.fetchone()
                    if gateway:
                        gateway_dict = dict(gateway)
                        if gateway_dict.get('card_number'):
                            gateway_dict['card_number'] = self._decrypt(gateway_dict['card_number'])
                        if gateway_dict.get('card_holder_name'):
                            gateway_dict['card_holder_name'] = self._decrypt(gateway_dict['card_holder_name'])
                        if gateway_dict.get('merchant_id'):
                            gateway_dict['merchant_id'] = self._decrypt(gateway_dict['merchant_id'])
                        return gateway_dict
                    return None
        except Exception as e:
            logger.error(f"Error getting payment gateway {gateway_id}: {e}")
            return None

    def update_payment_gateway_status(self, gateway_id, is_active):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE payment_gateways SET is_active = %s WHERE id = %s", (is_active, gateway_id))
                    conn.commit()
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error updating gateway status for ID {gateway_id}: {e}")
            return False

    # --- Payment Functions ---
    def add_payment(self, user_id, amount, receipt_message_id, order_details_json):
        sql = """
            INSERT INTO payments (user_id, amount, receipt_message_id, order_details_json, is_confirmed)
            VALUES (%s, %s, %s, %s, FALSE)
            RETURNING id;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (user_id, amount, receipt_message_id, order_details_json))
                    payment_id = cursor.fetchone()[0]
                    conn.commit()
                    return payment_id
        except psycopg2.Error as e:
            logger.error(f"Error adding payment request for user {user_id}: {e}")
            return None

    def get_payment_by_id(self, payment_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM payments WHERE id = %s", (payment_id,))
                    payment = cursor.fetchone()
                    return dict(payment) if payment else None
        except psycopg2.Error as e:
            logger.error(f"Error getting payment {payment_id}: {e}")
            return None

    def update_payment_status(self, payment_id, is_confirmed, admin_id=None):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE payments SET is_confirmed = %s, admin_confirmed_by = %s, confirmation_date = CURRENT_TIMESTAMP WHERE id = %s",
                        (is_confirmed, admin_id, payment_id)
                    )
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating payment status for ID {payment_id}: {e}")
            return False

    def update_payment_admin_notification_id(self, payment_id, message_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE payments SET admin_notification_message_id = %s WHERE id = %s", (message_id, payment_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating admin notification message ID for payment {payment_id}: {e}")
            return False

    def get_payment_by_authority(self, authority: str):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM payments WHERE authority = %s", (authority,))
                    payment = cursor.fetchone()
                    return dict(payment) if payment else None
        except psycopg2.Error as e:
            logger.error(f"Error getting payment by authority {authority}: {e}")
            return None

    def confirm_online_payment(self, payment_id: int, ref_id: str):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE payments SET is_confirmed = TRUE, ref_id = %s, confirmation_date = CURRENT_TIMESTAMP WHERE id = %s",
                        (ref_id, payment_id)
                    )
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error confirming online payment for ID {payment_id}: {e}")
            return False

    def set_payment_authority(self, payment_id: int, authority: str):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE payments SET authority = %s WHERE id = %s", (authority, payment_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error setting authority for payment ID {payment_id}: {e}")
            return False

    # --- Purchase Functions ---
    def add_purchase(self, user_id, server_id, plan_id, expire_date, initial_volume_gb, client_uuids, client_email, sub_id, single_configs_json, profile_id=None):
        """
        Adds a new purchase to the database. (Final Version)
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                sql = """
                    INSERT INTO purchases (user_id, server_id, plan_id, expire_date, initial_volume_gb, client_uuid, client_email, sub_id, single_configs_json, is_active, profile_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                    RETURNING id;
                """
                client_uuids_str = json.dumps(client_uuids) if client_uuids else None
                
                cur.execute(sql, (user_id, server_id, plan_id, expire_date, initial_volume_gb, client_uuids_str, client_email, sub_id, single_configs_json, profile_id))
                purchase_id = cur.fetchone()[0]
                conn.commit()
                return purchase_id
        except psycopg2.Error as e:
            logger.error(f"Error adding purchase for user {user_id}: {e}")
            if conn: conn.rollback()
            return None
        finally:
            if conn: conn.close()
    def get_user_purchases(self, user_db_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("""
                        SELECT p.id, p.purchase_date, p.expire_date, p.initial_volume_gb, p.is_active, s.name as server_name
                        FROM purchases p
                        JOIN servers s ON p.server_id = s.id
                        WHERE p.user_id = %s
                        ORDER BY p.id DESC
                    """, (user_db_id,))
                    return [dict(p) for p in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting purchases for user DB ID {user_db_id}: {e}")
            return []
            
    def get_purchase_by_id(self, purchase_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM purchases WHERE id = %s", (purchase_id,))
                    purchase = cursor.fetchone()
                    if purchase:
                        purchase_dict = dict(purchase)
                        purchase_dict['single_configs_json'] = json.loads(purchase_dict['single_configs_json'] or '[]')
                        return purchase_dict
                    return None
        except (psycopg2.Error, json.JSONDecodeError) as e:
            logger.error(f"Error getting purchase by ID {purchase_id}: {e}")
            return None
            
    def get_user_purchases_by_telegram_id(self, telegram_id: int):
        user = self.get_user_by_telegram_id(telegram_id)
        if not user:
            return []
        return self.get_user_purchases(user['id'])

    def delete_purchase(self, purchase_id: int) -> bool:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM purchases WHERE id = %s", (purchase_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error deleting purchase {purchase_id}: {e}")
            return False

    # --- Free Test Functions ---
    def check_free_test_usage(self, user_db_id: int) -> bool:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM free_test_usage WHERE user_id = %s", (user_db_id,))
                    return cursor.fetchone() is not None
        except psycopg2.Error as e:
            logger.error(f"Error checking free test usage for user {user_db_id}: {e}")
            return True

    def record_free_test_usage(self, user_db_id: int):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO free_test_usage (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_db_id,))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error recording free test usage for user {user_db_id}: {e}")
            return False

    def reset_free_test_usage(self, user_db_id: int):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM free_test_usage WHERE user_id = %s", (user_db_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error resetting free test usage for user {user_db_id}: {e}")
            return False

    # --- Settings Functions ---
    def get_setting(self, key: str) -> str or None:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT value FROM settings WHERE key = %s", (key,))
                    result = cursor.fetchone()
                    return result[0] if result else None
        except psycopg2.Error as e:
            logger.error(f"Error getting setting {key}: {e}")
            return None

    def update_setting(self, key: str, value: str):
        sql = """
            INSERT INTO settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (key, value))
                    conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Error updating setting {key}: {e}")

    # --- Tutorial Functions ---
    def add_tutorial(self, platform: str, app_name: str, chat_id: int, message_id: int):
        sql = """
            INSERT INTO tutorials (platform, app_name, forward_chat_id, forward_message_id) 
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (platform, app_name, chat_id, message_id))
                    tutorial_id = cursor.fetchone()[0]
                    conn.commit()
                    return tutorial_id
        except psycopg2.IntegrityError:
            logger.warning(f"Tutorial for {platform} - {app_name} already exists.")
            return None
        except psycopg2.Error as e:
            logger.error(f"Error adding tutorial: {e}")
            return None

    def get_all_tutorials(self):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM tutorials ORDER BY platform, app_name")
                    return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting all tutorials: {e}")
            return []

    def delete_tutorial(self, tutorial_id: int) -> bool:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM tutorials WHERE id = %s", (tutorial_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error deleting tutorial {tutorial_id}: {e}")
            return False

    def get_distinct_platforms(self):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT DISTINCT platform FROM tutorials ORDER BY platform")
                    return [row[0] for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting distinct platforms: {e}")
            return []

    def get_tutorials_by_platform(self, platform: str):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM tutorials WHERE platform = %s ORDER BY app_name", (platform,))
                    return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting tutorials for platform {platform}: {e}")
            return []
    
    def get_tutorial_by_id(self, tutorial_id: int):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM tutorials WHERE id = %s", (tutorial_id,))
                    tutorial = cursor.fetchone()
                    return dict(tutorial) if tutorial else None
        except psycopg2.Error as e:
            logger.error(f"Error getting tutorial by ID {tutorial_id}: {e}")
            return None
        
        
        
    def add_profile(self, name, per_gb_price, duration_days, description):
        """یک پروفایل حجمی جدید به دیتابیس اضافه می‌کند."""
        sql = """
            INSERT INTO profiles (name, per_gb_price, duration_days, description, is_active)
            VALUES (%s, %s, %s, %s, TRUE)
            RETURNING id;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (name, per_gb_price, duration_days, description))
                profile_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Profile '{name}' added with ID {profile_id}.")
                return profile_id
        except psycopg2.IntegrityError:
            logger.warning(f"Profile with name '{name}' already exists.")
            if conn: conn.rollback()
            return None
        except psycopg2.Error as e:
            logger.error(f"Error adding profile '{name}': {e}")
            if conn: conn.rollback()
            return False
        finally:
            if conn: conn.close()
            
            
    def get_all_profiles(self, only_active=False):
        """تمام پروفایل‌های ثبت شده در دیتابیس را برمی‌گرداند."""
        query = "SELECT * FROM profiles ORDER BY id"
        if only_active:
            query = "SELECT * FROM profiles WHERE is_active = TRUE ORDER BY id"
        
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(query)
                profiles = cur.fetchall()
                # fetchall در psycopg2 با DictCursor لیستی از ردیف‌های دیکشنری مانند برمی‌گرداند
                return profiles
        except psycopg2.Error as e:
            logger.error(f"Error getting all profiles: {e}")
            return []
        finally:
            if conn:
                conn.close()
                
                
                
    def get_inbounds_for_profile(self, profile_id: int, server_id: int = None, with_server_info: bool = False):
        """
        اینباندهای متصل به یک پروفایل را برمی‌گرداند. (نسخه نهایی و کامل)
        server_id: نتایج را برای یک سرور خاص فیلتر می‌کند.
        with_server_info: اطلاعات کامل سرور و الگوها را نیز برمی‌گرداند.
        """
        # --- اصلاح اصلی اینجاست: ساختار کوئری به طور کامل بازنویسی شده ---
        if with_server_info:
            sql = """
                SELECT 
                    pi.inbound_id, 
                    pi.config_params, 
                    pi.raw_template, 
                    s.* FROM profile_inbounds pi
                JOIN servers s ON pi.server_id = s.id
                WHERE pi.profile_id = %s;
            """
            params = (profile_id,)
        else:
            sql = "SELECT inbound_id FROM profile_inbounds WHERE profile_id = %s"
            params = [profile_id]
            if server_id:
                sql += " AND server_id = %s"
                params.append(server_id)
        
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute(sql, tuple(params))
                    results = []
                    rows = cur.fetchall()

                    if with_server_info:
                        for row in rows:
                            server_info = self._decrypt_server_row(row)
                            if server_info:
                                results.append({
                                    'inbound_id': row['inbound_id'],
                                    'config_params': row['config_params'],
                                    'raw_template': row['raw_template'], # <-- این فیلد کلیدی حالا به درستی خوانده می‌شود
                                    'server': server_info
                                })
                    else:
                        results = [row['inbound_id'] for row in rows]
                        
                    return results
        except psycopg2.Error as e:
            logger.error(f"Error getting inbounds for profile {profile_id}: {e}")
            return []
            
    def update_inbounds_for_profile(self, profile_id: int, server_id: int, inbound_ids: list):
        """
        اینباندهای یک پروفایل برای یک سرور خاص را به صورت اتمیک آپدیت می‌کند.
        ابتدا تمام رکوردهای قدیمی برای آن سرور را حذف و سپس جدیدها را اضافه می‌کند.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # قدم ۱: حذف تمام رکوردهای قدیمی فقط برای این پروفایل و این سرور
                logger.info(f"Deleting old inbounds for profile {profile_id} on server {server_id}...")
                cur.execute(
                    "DELETE FROM profile_inbounds WHERE profile_id = %s AND server_id = %s;",
                    (profile_id, server_id)
                )
                logger.info(f"Deletion complete. {cur.rowcount} rows affected.")

                # قدم ۲: اضافه کردن رکوردهای جدید
                if inbound_ids:
                    logger.info(f"Inserting {len(inbound_ids)} new inbounds...")
                    data_to_insert = [(profile_id, server_id, inbound_id) for inbound_id in inbound_ids]
                    # از psycopg2.extras.execute_values برای درج بهینه استفاده می‌کنیم
                    from psycopg2.extras import execute_values
                    execute_values(
                        cur,
                        "INSERT INTO profile_inbounds (profile_id, server_id, inbound_id) VALUES %s",
                        data_to_insert
                    )
                    logger.info("Insertion complete.")
                
                # اگر همه چیز موفق بود، تراکنش را نهایی کن
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"DATABASE TRANSACTION FAILED for profile {profile_id} on server {server_id}: {e}")
            # در صورت بروز هرگونه خطا، تمام تغییرات را به حالت قبل برگردان
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    def get_profile_by_id(self, profile_id):
        """اطلاعات یک پروفایل خاص را بر اساس ID آن برمی‌گرداند."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM profiles WHERE id = %s", (profile_id,))
                return cur.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting profile by ID {profile_id}: {e}")
            return None
        finally:
            if conn:
                conn.close()
                
                
    def add_subscription_domain(self, domain_name):
        sql = "INSERT INTO subscription_domains (domain_name) VALUES (%s) RETURNING id;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (domain_name,))
                domain_id = cur.fetchone()[0]
                conn.commit()
                return domain_id
        except psycopg2.IntegrityError:
            return None # دامنه تکراری
        except psycopg2.Error as e:
            logger.error(f"Error adding subscription domain {domain_name}: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if conn: conn.close()

    def get_all_subscription_domains(self):
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM subscription_domains ORDER BY id")
                return cur.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Error getting all subscription domains: {e}")
            return []
        finally:
            if conn: conn.close()

    def set_active_subscription_domain(self, domain_id):
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # ابتدا همه را غیرفعال کن
                cur.execute("UPDATE subscription_domains SET is_active = FALSE")
                # سپس دامنه مورد نظر را فعال کن
                cur.execute("UPDATE subscription_domains SET is_active = TRUE WHERE id = %s", (domain_id,))
                conn.commit()
                return True
        except psycopg2.Error as e:
            logger.error(f"Error setting active domain for ID {domain_id}: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if conn: conn.close()

    def get_active_subscription_domain(self):
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM subscription_domains WHERE is_active = TRUE LIMIT 1")
                return cur.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting active subscription domain: {e}")
            return None
        finally:
            if conn: conn.close()
            
            
    def sync_configs_for_server(self, server_id, configs_data):
        """کانفیگ‌های یک سرور را در دیتابیس محلی همگام‌سازی می‌کند."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # 1. حذف تمام رکوردهای قدیمی برای این سرور
                cur.execute("DELETE FROM synced_configs WHERE server_id = %s", (server_id,))
                
                # 2. آماده‌سازی و درج رکوردهای جدید
                if not configs_data:
                    conn.commit()
                    return 0 # هیچ کانفیگی برای افزودن وجود نداشت

                data_to_insert = []
                for config in configs_data:
                    data_to_insert.append((
                        server_id,
                        config.get('id'),
                        config.get('remark'),
                        config.get('port'),
                        config.get('protocol'),
                        config.get('settings', '{}'),
                        config.get('streamSettings', '{}')
                    ))
                
                cur.executemany(
                    """
                    INSERT INTO synced_configs (server_id, inbound_id, remark, port, protocol, settings, stream_settings)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    data_to_insert
                )
                conn.commit()
                return len(data_to_insert)
        except psycopg2.Error as e:
            logger.error(f"Error syncing configs for server {server_id}: {e}")
            if conn: conn.rollback()
            return -1 # نشان‌دهنده خطا
        finally:
            if conn: conn.close()
            
            
    def get_purchase_by_sub_id(self, sub_id):
        """یک خرید را بر اساس شناسه اشتراک یکتای آن پیدا می‌کند."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM purchases WHERE sub_id = %s", (sub_id,))
                return cur.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting purchase by sub_id {sub_id}: {e}")
            return None
        finally:
            if conn: conn.close()
            
    def get_synced_configs_for_profile(self, profile_id):
        """
        تمام کانفیگ‌های همگام‌سازی شده برای یک پروفایل خاص را به همراه آدرس سرورشان برمی‌گرداند.
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # با JOIN کردن جداول، اطلاعات سرور را نیز استخراج می‌کنیم
                sql = """
                    SELECT sc.*, s.subscription_base_url 
                    FROM synced_configs sc
                    JOIN profile_inbounds pi ON sc.server_id = pi.server_id AND sc.inbound_id = pi.inbound_id
                    JOIN servers s ON sc.server_id = s.id
                    WHERE pi.profile_id = %s;
                """
                cur.execute(sql, (profile_id,))
                
                # قبل از بازگرداندن، اطلاعات حساس سرور را رمزگشایی می‌کنیم
                configs = []
                for row in cur.fetchall():
                    config_dict = dict(row)
                    config_dict['subscription_base_url'] = self._decrypt(config_dict['subscription_base_url'])
                    configs.append(config_dict)
                return configs
        except psycopg2.Error as e:
            logger.error(f"Error getting synced configs for profile {profile_id}: {e}")
            return []
        finally:
            if conn: conn.close()
            
    def delete_subscription_domain(self, domain_id):
        sql = "DELETE FROM subscription_domains WHERE id = %s;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (domain_id,))
                conn.commit()
                return cur.rowcount > 0 # اگر سطری حذف شده باشد True برمی‌گرداند
        except psycopg2.Error as e:
            logger.error(f"Error deleting subscription domain {domain_id}: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if conn: conn.close()
            
            
    def set_user_admin_status(self, telegram_id, is_admin):
        """وضعیت ادمین بودن یک کاربر را تغییر می‌دهد."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET is_admin = %s WHERE telegram_id = %s", (is_admin, telegram_id))
                conn.commit()
                return cur.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error setting admin status for {telegram_id}: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if conn: conn.close()

    def get_all_admins(self):
        """لیست تمام کاربرانی که ادمین هستند را برمی‌گرداند."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE is_admin = TRUE")
                return cur.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Error getting all admins: {e}")
            return []
        finally:
            if conn: conn.close()
            
            
    def check_connection(self):
        """اتصال به دیتابیس را بررسی می‌کند."""
        conn = None
        try:
            conn = self._get_connection()
            # اگر کانکشن موفق باشد، یک کوئری ساده اجرا می‌کنیم
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False
        finally:
            if conn:
                conn.close()
                
                
    def update_server_inbound_params(self, server_id: int, inbound_id: int, params_json: str):
        """پارامترهای کانفیگ تجزیه شده را برای یک اینباند سرور خاص آپدیت می‌کند."""
        sql = "UPDATE server_inbounds SET config_params = %s WHERE server_id = %s AND inbound_id = %s"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (params_json, server_id, inbound_id))
                    conn.commit()
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error updating server inbound params for s:{server_id}-i:{inbound_id}: {e}")
            return False

    def update_profile_inbound_params(self, profile_id: int, server_id: int, inbound_id: int, params_json: str):
        """پارامترهای کانفیگ تجزیه شده را برای یک اینباند پروفایل خاص آپدیت می‌کند."""
        sql = "UPDATE profile_inbounds SET config_params = %s WHERE profile_id = %s AND server_id = %s AND inbound_id = %s"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (params_json, profile_id, server_id, inbound_id))
                    conn.commit()
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error updating profile inbound params for p:{profile_id}-s:{server_id}-i:{inbound_id}: {e}")
            return False
        
        
        
    def get_all_active_inbounds_with_server_info(self):
        """
        لیست تمام اینباندهای فعال از تمام سرورها را به همراه نام سرور برمی‌گرداند.
        """
        sql = """
            SELECT si.server_id, si.inbound_id, si.remark, si.config_params, s.name as server_name
            FROM server_inbounds si
            JOIN servers s ON si.server_id = s.id
            WHERE si.is_active = TRUE
            ORDER BY s.name, si.remark;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(sql)
                    return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting all active inbounds with server info: {e}")
            return []
        
        
    
    def get_active_inbounds_for_server_with_template(self, server_id: int):
        """اینباندهای فعال یک سرور را به همراه الگوی کانفیگ آنها برمی‌گرداند."""
        sql = """
            SELECT si.inbound_id, si.config_params, si.remark, s.*
            FROM server_inbounds si
            JOIN servers s ON si.server_id = s.id
            WHERE si.server_id = %s AND si.is_active = TRUE;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute(sql, (server_id,))
                    results = []
                    server_info = None
                    for row in cur.fetchall():
                        if not server_info: # فقط یک بار اطلاعات سرور را رمزگشایی کن
                            server_info = self._decrypt_server_row(row)
                        
                        if server_info:
                            results.append({
                                'inbound_id': row['inbound_id'],
                                'remark': row['remark'],
                                'config_params': row['config_params'],
                                'server': server_info
                            })
                    return results
        except psycopg2.Error as e:
            logger.error(f"Error getting active inbounds with template for server {server_id}: {e}")
            return []
        
        
        
    def get_all_profile_inbounds_with_status(self):
        """
        لیست تمام اینباندهای متصل به پروفایل‌ها را به همراه وضعیت الگو برمی‌گرداند.
        """
        sql = """
            SELECT 
                pi.profile_id, p.name as profile_name,
                pi.server_id, s.name as server_name,
                pi.inbound_id, si.remark,
                pi.config_params
            FROM profile_inbounds pi
            JOIN profiles p ON pi.profile_id = p.id
            JOIN servers s ON pi.server_id = s.id
            LEFT JOIN server_inbounds si ON pi.server_id = si.server_id AND pi.inbound_id = si.inbound_id
            ORDER BY p.name, s.name, si.remark;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(sql)
                    return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting all profile inbounds with status: {e}")
            return []

    def get_server_inbound_details(self, server_id: int, inbound_id: int):
        """جزئیات یک اینباند خاص (مانند remark) را از جدول server_inbounds می‌خواند."""
        sql = "SELECT remark FROM server_inbounds WHERE server_id = %s AND inbound_id = %s;"
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(sql, (server_id, inbound_id))
                    return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting server inbound details for s:{server_id}-i:{inbound_id}: {e}")
            return None
        
        
        
    def run_migrations(self):
        """
        تغییرات لازم در ساختار دیتابیس را به صورت خودکار اعمال می‌کند. (نسخه نهایی)
        """
        logging.info("Checking for necessary database migrations...")
        
        # لیست کامل دستورات SQL برای ساخت یا آپدیت جداول
        migrations = [
            # --- جداول پایه ---
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                is_admin BOOLEAN DEFAULT FALSE,
                join_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                balance REAL DEFAULT 0.0,
                is_verified BOOLEAN DEFAULT FALSE
            );
            """,
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);",
            """
            CREATE TABLE IF NOT EXISTS servers (
                id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, panel_type TEXT NOT NULL DEFAULT 'x-ui',
                panel_url TEXT NOT NULL, username TEXT NOT NULL, password TEXT NOT NULL,
                subscription_base_url TEXT NOT NULL, subscription_path_prefix TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE, last_checked TIMESTAMPTZ, is_online BOOLEAN DEFAULT FALSE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, plan_type TEXT NOT NULL,
                volume_gb REAL, duration_days INTEGER, price REAL, per_gb_price REAL,
                is_active BOOLEAN DEFAULT TRUE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, per_gb_price REAL NOT NULL,
                duration_days INTEGER NOT NULL, description TEXT, is_active BOOLEAN DEFAULT TRUE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS config_domains (
                id SERIAL PRIMARY KEY, domain_name TEXT UNIQUE NOT NULL, is_active BOOLEAN DEFAULT FALSE
            );
            """,
            # --- جداول وابسته با ستون‌های جدید ---
            """
            CREATE TABLE IF NOT EXISTS server_inbounds (
                id SERIAL PRIMARY KEY,
                server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
                inbound_id INTEGER NOT NULL,
                remark TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                config_params JSONB,
                raw_template TEXT,
                UNIQUE (server_id, inbound_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS profile_inbounds (
                id SERIAL PRIMARY KEY,
                profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
                inbound_id INTEGER NOT NULL,
                config_params JSONB,
                raw_template TEXT,
                UNIQUE (profile_id, server_id, inbound_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS bot_messages (
                message_key TEXT PRIMARY KEY,
                message_text TEXT NOT NULL
            );
            """,
            # --- دستورات ALTER برای کاربرانی که از نسخه‌های قدیمی‌تر آپدیت می‌کنند ---
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance REAL DEFAULT 0.0;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE server_inbounds ADD COLUMN IF NOT EXISTS config_params JSONB;",
            "ALTER TABLE server_inbounds ADD COLUMN IF NOT EXISTS raw_template TEXT;",
            "ALTER TABLE profile_inbounds ADD COLUMN IF NOT EXISTS config_params JSONB;",
            "ALTER TABLE profile_inbounds ADD COLUMN IF NOT EXISTS raw_template TEXT;"
        ]
        
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                for sql in migrations:
                    cur.execute(sql)
            conn.commit()
            logging.info("Database schema is up to date.")
        except Exception as e:
            logging.error(f"A critical error occurred during database migration: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
        self._seed_messages_table()
    def add_to_user_balance(self, user_id: int, amount: float):
        """مبلغ مشخص شده را به موجودی کیف پول کاربر اضافه می‌کند."""
        sql = "UPDATE users SET balance = balance + %s WHERE id = %s;"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (amount, user_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error adding balance for user {user_id}: {e}")
            return False
        
        
        
    def deduct_from_user_balance(self, user_id: int, amount: float):
        """
        مبلغ مشخص شده را از موجودی کیف پول کاربر کسر می‌کند.
        برای جلوگیری از منفی شدن موجودی، یک شرط در کوئری قرار داده شده است.
        """
        sql = "UPDATE users SET balance = balance - %s WHERE id = %s AND balance >= %s;"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (amount, user_id, amount))
                    conn.commit()
                    # اگر سطری آپدیت شده باشد، یعنی موجودی کافی بوده است
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error deducting balance for user {user_id}: {e}")
            return False
        
        
    # این دو تابع را در db_manager.py پیدا و جایگزین کنید

    def update_server_inbound_template(self, server_id: int, inbound_id: int, params_json: str, raw_template: str):
        """پارامترها و متن خام الگو را برای یک اینباند سرور خاص آپدیت می‌کند."""
        sql = "UPDATE server_inbounds SET config_params = %s, raw_template = %s WHERE server_id = %s AND inbound_id = %s"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (params_json, raw_template, server_id, inbound_id))
                    conn.commit()
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error updating server inbound template for s:{server_id}-i:{inbound_id}: {e}")
            return False

    def update_profile_inbound_template(self, profile_id: int, server_id: int, inbound_id: int, params_json: str, raw_template: str):
        """پارامترها و متن خام الگو را برای یک اینباند پروفایل خاص آپدیت می‌کند."""
        sql = "UPDATE profile_inbounds SET config_params = %s, raw_template = %s WHERE profile_id = %s AND server_id = %s AND inbound_id = %s"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (params_json, raw_template, profile_id, server_id, inbound_id))
                    conn.commit()
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error updating profile inbound template for p:{profile_id}-s:{server_id}-i:{inbound_id}: {e}")
            return False
        
        
    def get_all_profile_inbounds_for_debug(self):
        """تمام رکوردهای جدول profile_inbounds را با نام‌های خوانا برمی‌گرداند."""
        sql = """
            SELECT 
                pi.profile_id, p.name as profile_name,
                pi.server_id, s.name as server_name,
                pi.inbound_id
            FROM profile_inbounds pi
            JOIN profiles p ON pi.profile_id = p.id
            JOIN servers s ON pi.server_id = s.id
            ORDER BY pi.profile_id, pi.server_id, pi.inbound_id;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(sql)
                    return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting all profile inbounds for debug: {e}")
            return []
        
        
    def _seed_messages_table(self):
        """
        جدول bot_messages را با مقادیر پیش‌فرض از فایل messages.py پر می‌کند.
        فقط کلیدهایی که از قبل وجود نداشته باشند را اضافه می‌کند.
        """
        import utils.messages as messages_module
        
        all_messages = {
            key: getattr(messages_module, key)
            for key in dir(messages_module)
            if not key.startswith('__') and isinstance(getattr(messages_module, key), str)
        }
        
        if not all_messages:
            return

        sql = "INSERT INTO bot_messages (message_key, message_text) VALUES (%s, %s) ON CONFLICT (message_key) DO NOTHING;"
        
        data_to_insert = list(all_messages.items())
        
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                from psycopg2.extras import execute_batch
                execute_batch(cur, sql, data_to_insert)
                conn.commit()
                logger.info(f"Successfully seeded/updated {len(data_to_insert)} message keys into the database.")
        except Exception as e:
            logger.error(f"Error seeding messages table: {e}")
            if conn: conn.rollback()
        finally:
            if conn: conn.close()