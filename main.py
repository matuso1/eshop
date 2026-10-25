import os
import json
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Float, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Databázová konfigurácia
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eshop.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Admin prihlasovacie údaje
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "Matus123.")

# Databázové modely
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

# --- VEREJNÝ E-SHOP ---

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
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or product.stock <= 0:
        return RedirectResponse(url="/", status_code=303)

    cart = get_cart_from_cookie(request)
    str_id = str(product_id)
    cart[str_id] = cart.get(str_id, 0) + 1

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="cart", value=json.dumps(cart))
    return response

@app.post("/cart/remove/{product_id}")
async def remove_from_cart(request: Request, product_id: int):
    cart = get_cart_from_cookie(request)
    str_id = str(product_id)
    if str_id in cart:
        del cart[str_id]

    response = RedirectResponse(url="/cart", status_code=303)
    response.set_cookie(key="cart", value=json.dumps(cart))
    return response


# --- ADMIN ROUTY ---

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).all()
    coupons = db.query(Coupon).all()
    return templates.TemplateResponse(request, "admin.html", {
        "request": request, 
        "products": products,
        "coupons": coupons
    })

@app.post("/admin/products/add")
async def add_product(
    name: str = Form(...),
    price: float = Form(...),
    discount_price: float = Form(None),
    stock: int = Form(...),
    image_url: str = Form(None),
    db: Session = Depends(get_db)
):
    new_product = Product(
        name=name, 
        price=price, 
        discount_price=discount_price if discount_price else None, 
        stock=stock, 
        image_url=image_url
    )
    db.add(new_product)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/products/{product_id}/restock")
async def restock_product(
    product_id: int,
    quantity: int = Form(...),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        product.stock = (product.stock or 0) + quantity
        db.commit()
        db.refresh(product)
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/products/{product_id}/delete")
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/coupons/add")
async def add_coupon(
    code: str = Form(...),
    discount_percent: float = Form(...),
    db: Session = Depends(get_db)
):
    new_coupon = Coupon(code=code.upper(), discount_percent=discount_percent)
    db.add(new_coupon)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/coupons/{coupon_id}/delete")
async def delete_coupon(coupon_id: int, db: Session = Depends(get_db)):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if coupon:
        db.delete(coupon)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)
