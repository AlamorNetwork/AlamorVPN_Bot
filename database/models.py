# database/models.py
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, DateTime, BigInteger, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.base import Base

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
    is_active = Column(Boolean, default=True)
    
    # ارتباط با اینباندها
    inbounds = relationship("Inbound", back_populates="server", cascade="all, delete-orphan")

class Inbound(Base):
    __tablename__ = 'inbounds'
    id = Column(Integer, primary_key=True)
    server_id = Column(Integer, ForeignKey('servers.id'))
    
    xui_id = Column(Integer, nullable=False) # ID داخل پنل
    remark = Column(String)
    port = Column(Integer)
    protocol = Column(String)
    
    is_active = Column(Boolean, default=True)
    
    server = relationship("Server", back_populates="inbounds")
    purchases = relationship("Purchase", back_populates="inbound")

class Plan(Base):
    __tablename__ = 'plans'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    volume_gb = Column(Float, nullable=False)
    duration_days = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)

class Purchase(Base):
    __tablename__ = 'purchases'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    inbound_id = Column(Integer, ForeignKey('inbounds.id')) # اتصال به اینباند
    
    uuid = Column(String, unique=True)
    sub_link = Column(String)
    expire_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="purchases")
    inbound = relationship("Inbound", back_populates="purchases")

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    amount = Column(Float)
    status = Column(String, default="pending")
    authority = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="payments")