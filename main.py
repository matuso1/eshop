import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import secrets

# -------------------------------------------------------------------
# 1. DATABÁZA & NASTAVENIA
# -------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shop.db")

# Render často posiela 'postgres://', no SQLAlchemy vyžaduje 'postgresql://'
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite potrebuje špeciálny argument pre vlákna, PostgreSQL nie
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -------------------------------------------------------------------
# 2. PRIHLASOVACIE ÚDAJE PRE ADMINA (Z ENVIRONMENT VARIABLES)
# -------------------------------------------------------------------
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "matus123")

security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Neplatné prihlasovacie údaje",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# -------------------------------------------------------------------
# 3. DATABÁZOVÉ MODELY
# -------------------------------------------------------------------
class ProductDB(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    stock = Column(Integer, default=10)


class CouponDB(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    discount_percent = Column(Float)


Base.metadata.create_all(bind=engine)

# -------------------------------------------------------------------
# 4. APP & INICIALIZÁCIA
# -------------------------------------------------------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Pomocná funkcia na získanie databázovej relácie
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------------------------------------------------
# 5. WEBOVÉ ROUTY (E-SHOP)
# -------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    return templates.TemplateResponse("index.html", {"request": request, "products": products})


@app.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request, 
    username: str = Depends(verify_admin), 
    db: Session =
