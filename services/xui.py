# services/xui.py
import requests
import json
import logging
import urllib3

# غیرفعال کردن اخطارهای امنیتی SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# تنظیمات لاگ
logger = logging.getLogger(__name__)

class XUIClient:
    def __init__(self, panel_url: str, username: str, password: str):
        self.base_url = panel_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.is_logged_in = False
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json'
        })
        self.session.verify = False

    def _get_url(self, endpoint: str) -> str:
        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint
        return self.base_url + endpoint

    def login(self) -> bool:
        url = self._get_url('/login')
        payload = {'username': self.username, 'password': self.password}
        try:
            response = self.session.post(url, json=payload, timeout=30)
            if response.status_code == 200 and response.json().get('success'):
                self.is_logged_in = True
                return True
            return False
        except Exception as e:
            logger.error(f"Login Error: {e}")
            return False

    def _request(self, method: str, endpoint: str, **kwargs):
        if not self.is_logged_in:
            if not self.login(): return None

        url = self._get_url(endpoint)
        req_kwargs = {'timeout': 30, 'verify': False}
        req_kwargs.update(kwargs)

        try:
            response = self.session.request(method, url, **req_kwargs)
            if response.status_code in [401, 403]:
                if self.login():
                    response = self.session.request(method, url, **req_kwargs)
                else:
                    return None
            return response.json()
        except Exception as e:
            logger.error(f"API Request Error ({endpoint}): {e}")
            return None

    # ==========================
    # توابع کمکی هوشمند
    # ==========================
    def _get_client_db_id(self, uuid: str):
        """یافتن شناسه عددی کلاینت با UUID"""
        traffic_data = self.get_client_traffic(uuid)
        if traffic_data and 'id' in traffic_data:
            return traffic_data['id']
        return None

    # ==========================
    # 1. مدیریت سیستم
    # ==========================
    def get_system_status(self):
        return self._request('POST', '/panel/api/inbounds/onlines')

    def get_xray_version(self):
        return self._request('GET', '/server/status')

    # ==========================
    # 2. مدیریت اینباندها
    # ==========================
    def get_inbounds(self):
        res = self._request('GET', '/panel/api/inbounds/list')
        return res.get('obj', []) if res and res.get('success') else []

    def get_inbound(self, inbound_id: int):
        res = self._request('GET', f'/panel/api/inbounds/get/{inbound_id}')
        return res.get('obj') if res and res.get('success') else None

    def add_inbound(self, remark: str, port: int, protocol: str, settings: dict, stream_settings: dict):
        payload = {
            "up": 0, "down": 0, "total": 0, "remark": remark,
            "enable": True, "expiryTime": 0,
            "listen": "", "port": port, "protocol": protocol,
            "settings": json.dumps(settings),
            "streamSettings": json.dumps(stream_settings),
            "sniffing": json.dumps({"enabled": True, "destOverride": ["http", "tls"]})
        }
        res = self._request('POST', '/panel/api/inbounds/add', json=payload)
        return res and res.get('success')

    def update_inbound(self, inbound_id: int, data: dict):
        res = self._request('POST', f'/panel/api/inbounds/update/{inbound_id}', json=data)
        return res and res.get('success')

    def delete_inbound(self, inbound_id: int):
        res = self._request('POST', f'/panel/api/inbounds/del/{inbound_id}')
        return res and res.get('success')

    # ==========================
    # 3. مدیریت کلاینت‌ها
    # ==========================
    def add_client(self, inbound_id: int, email: str, uuid: str, sub_id: str, total_gb: float = 0, expiry_time: int = 0, enable: bool = True, limit_ip: int = 1, flow: str = ""):
        """
        افزودن کلاینت با کنترل دقیق SubId، حجم و زمان.
        total_gb <= 0  --> نامحدود
        expiry_time <= 0 --> نامحدود (Lifetime)
        """
        
        # محاسبه حجم (اگر صفر یا کمتر بود، یعنی نامحدود، پس 0 میفرستیم)
        final_total = int(total_gb * 1024**3) if total_gb > 0 else 0
        
        # محاسبه زمان (اگر صفر یا کمتر بود، یعنی نامحدود، پس 0 میفرستیم)
        final_expiry = expiry_time if expiry_time > 0 else 0

        client = {
            "id": uuid,
            "email": email,
            "limitIp": limit_ip,
            "totalGB": final_total, 
            "expiryTime": final_expiry,
            "enable": enable,
            "tgId": "",
            "subId": sub_id,  # <--- ارسال دستی SubID
            "flow": flow
        }
        
        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client]})
        }
        
        res = self._request('POST', '/panel/api/inbounds/addClient', json=payload)
        return res and res.get('success')

    def update_client(self, client_uuid: str, client_settings: dict):
        """
        ویرایش هوشمند کلاینت:
        ۱. شناسه عددی را پیدا می‌کند.
        ۲. اطلاعات فعلی را می‌گیرد.
        ۳. تغییرات را ادغام می‌کند تا فیلدهای ضروری حذف نشوند.
        """
        # 1. یافتن ID عددی
        db_id = self._get_client_db_id(client_uuid)
        if not db_id:
            logger.error(f"Cannot update client: UUID {client_uuid} not found.")
            return False

        # 2. دریافت اطلاعات فعلی برای جلوگیری از حذف شدن فیلدهای مهم
        current_data = self.get_client_traffic(client_uuid)
        if not current_data:
            # اگر نتوانستیم اطلاعات فعلی را بگیریم، یک قالب پیش‌فرض می‌سازیم
            current_data = {
                "id": client_uuid,
                "flow": "",
                "limitIp": 0,
                "totalGB": 0,
                "expiryTime": 0,
                "enable": True,
                "tgId": "",
                "subId": ""
            }

        # 3. ادغام تنظیمات جدید با اطلاعات فعلی
        current_data.update(client_settings)
        
        # اطمینان از اینکه فیلدهای حیاتی وجود دارند (پنل بدون اینها ارور می‌دهد)
        if "limitIp" not in current_data: current_data["limitIp"] = 0
        if "flow" not in current_data: current_data["flow"] = ""
        if "totalGB" not in current_data: current_data["totalGB"] = 0
        if "email" not in current_data: current_data["email"] = f"user_{db_id}"

        # 4. ارسال درخواست آپدیت
        endpoint = f'/panel/api/inbounds/updateClient/{db_id}'
        res = self._request('POST', endpoint, json=current_data)
        return res and res.get('success')

    def delete_client(self, inbound_id: int, client_uuid: str):
        db_id = self._get_client_db_id(client_uuid)
        if not db_id:
            logger.error(f"Cannot delete client: UUID {client_uuid} not found.")
            return False
            
        endpoint = f'/panel/api/inbounds/{inbound_id}/delClient/{db_id}'
        res = self._request('POST', endpoint)
        return res and res.get('success')

    def get_client_info(self, inbound_id: int, uuid_or_email: str):
        inbound = self.get_inbound(inbound_id)
        if not inbound: return None
        try:
            clients = json.loads(inbound.get('settings', '{}')).get('clients', [])
            for c in clients:
                if c.get('id') == uuid_or_email or c.get('email') == uuid_or_email:
                    return c
        except: pass
        return None

    # ==========================
    # 4. ترافیک
    # ==========================
    def get_client_traffic(self, uuid: str):
        res = self._request('GET', f'/panel/api/inbounds/getClientTrafficsById/{uuid}')
        if res and res.get('success'):
            data = res.get('obj')
            if isinstance(data, list) and data:
                return data[0]
            elif isinstance(data, dict):
                return data
        return None

    def reset_client_traffic(self, inbound_id: int, email: str):
        res = self._request('POST', f'/panel/api/inbounds/{inbound_id}/resetClientTraffic/{email}')
        return res and res.get('success')