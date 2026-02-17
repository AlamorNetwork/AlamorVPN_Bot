# database/base.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DB_URI # این را در مرحله بعد می‌سازیم

# ساخت موتور دیتابیس
engine = create_engine(DB_URI, echo=False)

# ساخت Session برای کوئری زدن
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# کلاس پایه برای مدل‌ها
Base = declarative_base()

def init_db():
    """ساخت تمام جداول در دیتابیس"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """تابع کمکی برای گرفتن سشن دیتابیس"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()