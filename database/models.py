# database/models.py
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, DateTime, BigInteger, Table, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.base import Base

# جدول واسط برای اتصال پلن‌ها به اینباندها (Many-to-Many)
plan_inbound_association = Table(
    'plan_inbound', Base.metadata,
    Column('plan_id', Integer, ForeignKey('plans.id')),
    Column('inbound_id', Integer, ForeignKey('inbounds.id'))
)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    first_name = Column(String)
    username = Column(String)
    balance = Column(Float, default=0.0)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    purchases = relationship("Purchase", back_populates="user")
    payments = relationship("Payment", back_populates="user")

class Server(Base):
    __tablename__ = 'servers'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    panel_url = Column(String, nullable=False)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    subscription_url = Column(String, nullable=False)
    
    # فیلد جدید: تمپلیت کانفیگ (برای ساخت کانفیگ تکی)
    # مثال: vless://UUID@domain:port?security=...
    config_template = Column(Text, nullable=True)
    
    is_active = Column(Boolean, default=True)
    inbounds = relationship("Inbound", back_populates="server", cascade="all, delete-orphan")

class Inbound(Base):
    __tablename__ = 'inbounds'
    id = Column(Integer, primary_key=True)
    server_id = Column(Integer, ForeignKey('servers.id'))
    xui_id = Column(Integer, nullable=False)
    remark = Column(String)
    port = Column(Integer)
    protocol = Column(String)
    is_active = Column(Boolean, default=True)
    
    server = relationship("Server", back_populates="inbounds")
    # رابطه با پلن‌ها
    plans = relationship("Plan", secondary=plan_inbound_association, back_populates="inbounds")

class Plan(Base):
    __tablename__ = 'plans'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    volume_gb = Column(Float, nullable=False)
    duration_days = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # پلن به کدام اینباندها متصل است؟
    inbounds = relationship("Inbound", secondary=plan_inbound_association, back_populates="plans")

class Purchase(Base):
    __tablename__ = 'purchases'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    
    # چون یک خرید ممکن است شامل چند اینباند باشد، اینجا فقط پلن را نگه می‌داریم
    # اما برای سادگی فعلاً فرض می‌کنیم کانفیگ اصلی روی یک اینباند اصلی است یا مولتی پورت است
    # برای جلوگیری از پیچیدگی، ما خرید را به "پلن" وصل می‌کنیم، نه اینباند تکی
    plan_id = Column(Integer, ForeignKey('plans.id'))
    
    uuid = Column(String, unique=True)
    sub_link = Column(String)
    expire_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="purchases")
    plan = relationship("Plan")

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    plan_id = Column(Integer, ForeignKey('plans.id')) # چه پلنی می‌خواست بخرد؟
    
    amount = Column(Float)
    status = Column(String, default="pending") # pending, approved, rejected
    payment_method = Column(String, default="card") # card, zarinpal
    
    # برای کارت به کارت
    receipt_image_id = Column(String, nullable=True) # آیدی فایل عکس در تلگرام
    admin_note = Column(String, nullable=True) # دلیل رد یا تایید
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="payments")
    plan = relationship("Plan")