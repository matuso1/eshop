import os
import json
import secrets
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. Databázová konfigurácia
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eshop.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Admin prihlasovacie údaje
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "Matus123.")

security = HTTPBasic()

# Overenie admina (zabezpečenie administrácie)
def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávne meno alebo heslo",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# 2. Databázové modely (Produkty + Kupóny)
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    discount_price = Column(Float, nullable=True)
    stock = Column(Integer, default=0)
    image_url = Column(String, nullable=True)

class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)
    discount_percent = Column(Float, nullable=False)

# Vytvorenie tabuliek
Base.metadata.create_all(bind=engine)

# Bezpečnostná poistka pre PostgreSQL stĺpce
with engine.begin() as conn:
    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS discount_price FLOAT;"))
    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT 0;"))

app = FastAPI(title="eshop-7")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_cart_from_cookie(request: Request) -> dict:
    cart_cookie = request.cookies.get("cart")
    if cart_cookie:
        try:
            return json.loads(cart_cookie)
        except:
            return {}
    return {}

# -------------------------------------------------------------
# 3. VEREJNÝ E-SHOP (Produkty, Triedenie, Košík, Kupóny)
# -------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request, sort: str = None, db: Session = Depends(get_db)):
    query = db.query(Product)
    
    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    elif sort == "name_asc":
        query = query.order_by(Product.name.asc())
    elif sort == "name_desc":
        query = query.order_by(Product.name.desc())
        
    products = query.all()
    cart = get_cart_from_cookie(request)
    cart_count = sum(cart.values())

    return templates.TemplateResponse(request, "index.html", {
        "request": request, 
        "products": products, 
        "current_sort": sort,
        "cart_count": cart_count
    })

@app.get("/cart", response_class=HTMLResponse)
async def view_cart(request: Request, coupon_code: str = None, db: Session = Depends(get_db)):
    cart = get_cart_from_cookie(request)
    cart_items = []
    subtotal = 0.0

    for prod_id_str, qty in cart.items():
        prod_id = int(prod_id_str)
        product = db.query(Product).filter(Product.id == prod_id).first()
        if product:
            effective_price = product.discount_price if product.discount_price is not None else product.price
            total_price = effective_price * qty
            subtotal += total_price
            cart_items.append({
                "product": product,
                "quantity": qty,
                "total_price": total_price
            })

    discount_amount = 0.0
    applied_coupon = None
    if coupon_code:
        coupon = db.query(Coupon).filter(Coupon.code == coupon_code.upper()).first()
        if coupon:
            applied_coupon = coupon.code
            discount_amount = subtotal * (coupon.discount_percent / 100.0)

    final_total = subtotal - discount_amount

    return templates.TemplateResponse(request, "cart.html", {
        "request": request,
        "cart_items": cart_items,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "final_total": final_total,
        "applied_coupon": applied_coupon
    })

@app.post("/cart/add/{product_id}")
async def add_to_cart_action(request: Request, product_id: int, db: Session = Depends(get_db)):
