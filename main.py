from fastapi import FastAPI, Depends, Request, Form, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
import os
import secrets
import html

# Načítanie databázového URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./shop.db"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Tabuľka produktov
class ProductDB(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    description = Column(String)
    category = Column(String, index=True)
    image_url = Column(String)
    stock = Column(Integer, default=10)

# Tabuľka pre nákupný košík
class CartItemDB(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    
    product = relationship("ProductDB")

# Tabuľka pre zľavové kupóny
class CouponDB(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    discount_percent = Column(Float)

# Vytvorenie tabuliek
Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

# Bezpečné načítanie admin údajov z Environment Variables (s fallbackom pre lokálny test)
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "matus123")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávne meno alebo heslo",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

applied_coupon = {"code": None, "discount": 0.0}

# --- VEREJNÉ CESTY ---

@app.get("/")
def read_root(request: Request, db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    cart_count = db.query(CartItemDB).count()
    return templates.TemplateResponse(request, "index.html", {
        "products": products, 
        "is_admin": False,
        "cart_count": cart_count
    })

@app.get("/cart")
def view_cart(request: Request, db: Session = Depends(get_db)):
    cart_items = db.query(CartItemDB).all()
    subtotal = sum(item.product.price * item.quantity for item in cart_items if item.product)
    
    discount_amount = (subtotal * applied_coupon["discount"]) / 100
    total_price = subtotal - discount_amount
    cart_count = db.query(CartItemDB).count()

    return templates.TemplateResponse(request, "cart.html", {
        "cart_items": cart_items,
        "subtotal": subtotal,
        "total_price": total_price,
        "discount_percent": applied_coupon["discount"],
        "coupon_code": applied_coupon["code"],
        "cart_count": cart_count
    })

@app.post("/cart/add/{product_id}")
def add_to_cart(product_id: int, db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produkt neexistuje")
    
    if product.stock <= 0:
        raise HTTPException(status_code=400, detail="Produkt je vypredaný!")

    cart_item = db.query(CartItemDB).filter(CartItemDB.product_id == product_id).first()
    if cart_item:
        if product.stock > cart_item.quantity:
            cart_item.quantity += 1
        else:
            raise HTTPException(status_code=400, detail="Nedostatok tovaru na sklade!")
    else:
        cart_item = CartItemDB(product_id=product_id, quantity=1)
        db.add(cart_item)
    
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/cart/apply-coupon")
def apply_coupon(coupon_code: str = Form(...), db: Session = Depends(get_db)):
    clean_code = html.escape(coupon_code.strip().upper(), quote=True)
    coupon = db.query(CouponDB).filter(CouponDB.code == clean_code).first()
    
    if coupon:
        applied_coupon["code"] = coupon.code
        applied_coupon["discount"] = coupon.discount_percent
    else:
        raise HTTPException(status_code=400, detail="Neplatný zľavový kupón!")

    return RedirectResponse(url="/cart", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/cart/remove-coupon")
def remove_coupon():
    applied_coupon["code"] = None
    applied_coupon["discount"] = 0.0
    return RedirectResponse(url="/cart", status_code=status.HTTP_303_SEE_OTHER)

# --- ADMIN CESTY ---

@app.get("/admin")
def admin_page(request: Request, username: str = Depends(verify_credentials), db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    coupons = db.query(CouponDB).all()
    cart_count = db.query(CartItemDB).count()
    return templates.TemplateResponse(request, "index.html", {
        "products": products, 
        "coupons": coupons,
        "is_admin": True,
        "cart_count": cart_count
    })

@app.post("/admin/add-product")
def add_product(
    name: str = Form(...),
    price: float = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    image_url: str = Form(...),
    stock: int = Form(...),
    username: str = Depends(verify_credentials),
    db: Session = Depends(get_db)
):
    try:
        clean_name = html.escape(name.strip().lower(), quote=True)
        clean_category = html.escape(category.strip().lower(), quote=True)

        existing_product = db.query(ProductDB).filter(
            ProductDB.name == clean_name, 
            ProductDB.category == clean_category
        ).first()

        if existing_product:
            raise HTTPException(status_code=400, detail="Tento produkt v tejto kategórii už existuje!")

        new_product = ProductDB(
            name=name.strip(),
            price=price,
            description=description,
            category=category.strip(),
            image_url=image_url.strip(),
            stock=stock
        )
        db.add(new_product)
        db.commit()
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Chyba: {str(e)}")
    
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/add-coupon")
def add_coupon(
    code: str = Form(...),
    discount_percent: float = Form(...),
    username: str = Depends(verify_credentials),
    db: Session = Depends(get_db)
):
    clean_clean_code = html.escape(code.strip().upper(), quote=True)
    existing = db.query(CouponDB).filter(CouponDB.code == clean_clean_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tento kupón už existuje!")

    new_coupon = CouponDB(code=clean_clean_code, discount_percent=discount_percent)
    db.add(new_coupon)
    db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/delete-product/{product_id}")
def delete_product(
    product_id: int,
    username: str = Depends(verify_credentials),
    db: Session = Depends(get_db)
):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if product:
        db.query(CartItemDB).filter(CartItemDB.product_id == product_id).delete()
        db.delete(product)
        db.commit()
    
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/delete-coupon/{coupon_id}")
def delete_coupon(
    coupon_id: int,
    username: str = Depends(verify_credentials),
    db: Session = Depends(get_db)
):
    coupon = db.query(CouponDB).filter(CouponDB.id == coupon_id).first()
    if coupon:
        db.delete(coupon)
        db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
