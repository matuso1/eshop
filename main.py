import os
import json
from fastapi import FastAPI, Depends, HTTPException, Request, Form, status, Cookie
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Bezpečné načítanie: Ak DATABASE_URL na Renderi chýba, nespadne, ale použije lokálny SQLite
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("POZOR: DATABASE_URL nie je nastavená, fallbackujem na SQLite.")
    DATABASE_URL = "sqlite:///./database.db"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Definícia tabuliek (Ochrana pred SQL Injection cez ORM)
class ProductDB(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False)
    discount = Column(Float, default=0.0)
    image_url = Column(String, default="")

class CouponDB(Base):
    __tablename__ = "coupons"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False, index=True)
    discount_percent = Column(Float, nullable=False)

Base.metadata.create_all(bind=engine)

app = FastAPI()
security = HTTPBasic()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "admin" or credentials.password != "matus123":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávne prihlasovacie údaje",
            headers={"WWW-Authenticate": "Basic"}
        )
    return credentials.username

@app.get("/")
def read_root(request: Request, cart: str = Cookie(None), db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    
    cart_items = json.loads(cart) if cart else {}
    cart_count = sum(cart_items.values())
    
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"products": products, "cart_count": cart_count}
    )

@app.post("/cart/add/{product_id}")
def add_to_cart(product_id: int, cart: str = Cookie(None), db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    
    if product and product.stock > 0:
        product.stock -= 1
        db.commit()
        
        cart_items = json.loads(cart) if cart else {}
        str_id = str(product_id)
        cart_items[str_id] = cart_items.get(str_id, 0) + 1
        
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="cart", value=json.dumps(cart_items))
    else:
        response = RedirectResponse(url="/", status_code=303)
        
    return response

@app.get("/cart")
def view_cart(request: Request, cart: str = Cookie(None), applied_coupon: str = Cookie(None), db: Session = Depends(get_db)):
    cart_items = json.loads(cart) if cart else {}
    
    products_in_cart = []
    subtotal = 0.0
    
    for str_id, quantity in cart_items.items():
        product = db.query(ProductDB).filter(ProductDB.id == int(str_id)).first()
        if product:
            final_item_price = product.price * (1.0 - product.discount / 100.0)
            item_total = final_item_price * quantity
            subtotal += item_total
            
            products_in_cart.append({
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "discount": product.discount,
                "final_item_price": final_item_price,
                "quantity": quantity,
                "item_total": item_total,
                "image_url": product.image_url
            })
            
    coupon_discount = 0.0
    if applied_coupon:
        coupon = db.query(CouponDB).filter(CouponDB.code == applied_coupon.upper()).first()
        if coupon:
            coupon_discount = float(coupon.discount_percent)
            
    total = subtotal * (1.0 - coupon_discount / 100.0)
    cart_count = sum(cart_items.values())
    
    return templates.TemplateResponse(
        request=request,
        name="cart.html",
        context={
            "products_in_cart": products_in_cart,
            "subtotal": subtotal,
            "coupon_discount": coupon_discount,
            "applied_coupon": applied_coupon,
            "total": total,
            "cart_count": cart_count
        }
    )

@app.post("/cart/apply-coupon")
def apply_coupon(coupon_code: str = Form(...), db: Session = Depends(get_db)):
    coupon = db.query(CouponDB).filter(CouponDB.code == coupon_code.strip().upper()).first()
    
    response = RedirectResponse(url="/cart", status_code=303)
    if coupon:
        response.set_cookie(key="applied_coupon", value=coupon.code)
    else:
        response.delete_cookie(key="applied_coupon")
    return response

@app.get("/cart/remove-coupon")
def remove_coupon():
    response = RedirectResponse(url="/cart", status_code=303)
    response.delete_cookie(key="applied_coupon")
    return response

@app.get("/cart/clear")
def clear_cart(cart: str = Cookie(None), db: Session = Depends(get_db)):
    if cart:
        try:
            cart_items = json.loads(cart)
            for str_id, quantity in cart_items.items():
                product = db.query(ProductDB).filter(ProductDB.id == int(str_id)).first()
                if product:
                    product.stock += quantity
            db.commit()
        except Exception:
            pass

    response = RedirectResponse(url="/cart", status_code=303)
    response.delete_cookie(key="cart")
    response.delete_cookie(key="applied_coupon")
    return response

@app.get("/admin")
def admin_page(request: Request, username: str = Depends(verify_credentials), db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    coupons = db.query(CouponDB).all()
    
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"products": products, "coupons": coupons}
    )

@app.post("/admin/add-product")
def add_product(
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    discount: float = Form(0.0),
    image_url: str = Form(""),
    username: str = Depends(verify_credentials),
    db: Session = Depends(get_db)
):
    new_product = ProductDB(
        name=name,
        price=price,
        stock=stock,
        discount=discount,
        image_url=image_url
    )
    db.add(new_product)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/restock/{product_id}")
def restock_product(product_id: int, username: str = Depends(verify_credentials), db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if product:
        product.stock += 1
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete/{product_id}")
def delete_product(product_id: int, username: str = Depends(verify_credentials), db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/add-coupon")
def add_coupon(
    code: str = Form(...),
    discount_percent: float = Form(...),
    username: str = Depends(verify_credentials),
    db: Session = Depends(get_db)
):
    existing
