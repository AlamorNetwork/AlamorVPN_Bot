# database/models.py
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, DateTime, BigInteger, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.base import Base

# جدول کاربران
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    first_name = Column(String)
    username = Column(String)
    balance = Column(Float, default=0.0)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ارتباط با خریدها
    purchases = relationship("Purchase", back_populates="user")
    payments = relationship("Payment", back_populates="user")

# جدول سرورها (پنل‌های ثنایی)
class Server(Base):
    __tablename__ = 'servers'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    
    # اطلاعات ورود به پنل (برای ربات)
    panel_url = Column(String, nullable=False)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    
    # آدرس سابسکریپشن (برای کاربر) - این فیلد جدید است
    # مثال مقدار: https://parssafe.irplatforme.ir:2096/subzero
    subscription_url = Column(String, nullable=False) 
    
    is_active = Column(Boolean, default=True)
    
    purchases = relationship("Purchase", back_populates="server")

# جدول پلن‌ها (تعرفه)
class Plan(Base):
    __tablename__ = 'plans'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    volume_gb = Column(Float, nullable=False)
    duration_days = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)

# جدول خریدها (سابسکریپشن‌ها)
class Purchase(Base):
    __tablename__ = 'purchases'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    server_id = Column(Integer, ForeignKey('servers.id'))
    plan_id = Column(Integer, ForeignKey('plans.id'))
    
    uuid = Column(String, unique=True)  # برای کلید کلاینت
    sub_link = Column(String)           # لینک سابسکریپشن
    expire_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # روابط
    user = relationship("User", back_populates="purchases")
    server = relationship("Server", back_populates="purchases")

# جدول پرداخت‌ها
class Payment(Base):
    __tablename__ = 'payments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    amount = Column(Float)
    status = Column(String, default="pending") # pending, paid, cancelled
    authority = Column(String) # برای زرین‌پال
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="payments")