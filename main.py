import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine.url import make_url
import secrets

# -------------------------------------------------------------------
# 1. DATABÁZA & BEZPEČNÉ PARSOVANIE URL
# -------------------------------------------------------------------
raw_db_url = os.getenv("DATABASE_URL")

if not raw_db_url:
    DATABASE_URL = "sqlite:///./shop.db"
else:
    DATABASE_URL = raw_db_url.strip().strip('"').strip("'")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    try:
        make_url(DATABASE_URL)
    except Exception as e:
        print(f"POZOR: Neplatná DATABASE_URL z Renderu ('{DATABASE_URL}'). Chyba: {e}")
        print("Automaticky prepínam na lokálnu SQLite databázu, aby aplikácia nepadala.")
        DATABASE_URL = "sqlite:///./shop.db"

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -------------------------------------------------------------------
# 2. PRIHLASOVACIE ÚDAJE PRE ADMINA
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
    image = Column(String, default="https://via.placeholder.com/150") # Podpora pre fotky


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
    return templates.TemplateResponse(request, "index.html", {"products": products})


@app.get("/cart", response_class=HTMLResponse)
def cart_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "cart.html", {"cart_items": []})


@app.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request, 
    username: str = Depends(verify_admin), 
    db: Session = Depends(get_db)
):
    products = db.query(ProductDB).all()
    coupons = db.query(CouponDB).all()
    return templates.TemplateResponse(
        request, 
        "admin.html", 
        {"products": products, "coupons": coupons, "admin": username}
    )


@app.post("/admin/add-product")
def add_product(
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    image: str = Form("https://via.placeholder.com/150"), # Voliteľný odkaz na fotku
    username: str = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    new_product = ProductDB(name=name, price=price, stock=stock, image=image)
    db.add(new_product)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


# --- NOVÉ: ROUTY NA MAZANIE ---
@app.get("/admin/delete-product/{product_id}")
def delete_product(
    product_id: int,
    username: str = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@app.get("/admin/delete-coupon/{coupon_id}")
def delete_coupon(
    coupon_id: int,
    username: str = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    coupon = db.query(CouponDB).filter(CouponDB.id == coupon_id).first()
    if coupon:
        db.delete(coupon)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/add-coupon")
def add_coupon(
    code: str = Form(...),
    discount_percent: float = Form(...),
    username: str = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    new_coupon = CouponDB(code=code.upper(), discount_percent=discount_percent)
    db.add(new_coupon)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)
