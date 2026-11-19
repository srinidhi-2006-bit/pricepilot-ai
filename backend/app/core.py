"""Database models, auth (JWT + RBAC)."""
import os, hmac, hashlib, secrets, datetime as dt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pricepilot.db")
SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, default="analyst")  # admin | pricing_manager | analyst

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, default="General")
    cost = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)

class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    date = Column(Date, index=True)
    units = Column(Integer)
    price = Column(Float)
    discount = Column(Float, default=0)          # percent
    competitor_price = Column(Float)

class CompetitorPrice(Base):
    __tablename__ = "competitor_prices"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    competitor = Column(String)
    price = Column(Float)
    date = Column(Date)

class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    old_price = Column(Float); new_price = Column(Float)
    changed_by = Column(String); date = Column(Date, default=dt.date.today)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    return f"{salt}${hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 100_000).hex()}"

def check_pw(pw, stored):
    salt, h = stored.split("$")
    return hmac.compare_digest(hash_pw(pw, salt).split("$")[1], h)

def make_token(user):
    exp = dt.datetime.utcnow() + dt.timedelta(hours=12)
    return jwt.encode({"sub": user.email, "role": user.role, "exp": exp}, SECRET, algorithm="HS256")

oauth2 = OAuth2PasswordBearer(tokenUrl="auth/login")

def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)):
    try:
        email = jwt.decode(token, SECRET, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    user = db.query(User).filter(User.email == email).first()
    if not user: raise HTTPException(401, "User not found")
    return user

def require(*roles):
    def dep(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, f"Requires role: {', '.join(roles)}")
        return user
    return dep
