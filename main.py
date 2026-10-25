import os
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
    discount_percent = Column(Float, nullable=False) # Napr. 10 pre 10%

# Vytvorenie tabuliek
Base.metadata.create_all(bind=engine)

# BEZPEČNOSTNÁ POISTKA pre existujúcu PostgreSQL databázu
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

# -------------------------------------------------------------
# 3. VEREJNÝ E-SHOP (Produkty, Triedenie, Košík, Kupóny)
# -------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request, sort: str = None, db: Session = Depends(get_db)):
    query = db.query(Product)
    
    # Triedenie
    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    elif sort == "name_asc":
        query = query.order_by(Product.name.asc())
    elif sort == "name_desc":
        query = query.order_by(Product.name.desc())
        
    products = query.all()
    
    # Získanie košíka zo session/cookies (jednoduchá in-memory/cookie simulácia cez query/dict ak treba, resp. dictionary v session)
    # Pre jednoduchosť uchovávame košík v cookies alebo session, tu ukážeme základnú štruktúru šablóny
    return templates.TemplateResponse(request, "index.html", {
        "request": request, 
        "products": products, 
        "current_sort": sort
    })

# Pridanie do košíka (uloženie do cookies / session alebo jednoduché presmerovanie)
@app.post("/cart/add/{product_id}")
async def add_to_cart(product_id: int, db: Session = Depends(get_db)):
    # Tu sa produkt pridáva do košíka (môžeš si to prepojiť so session)
    return RedirectResponse(url="/", status_code=303)

# -------------------------------------------------------------
# 4. ADMIN ROUTY (Správa produktov, Sklad/Doskladnenie, Kupóny)
# -------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).all()
    coupons = db.query(Coupon).all()
    return templates.TemplateResponse(request, "admin.html", {
        "request": request, 
        "products": products,
        "coupons": coupons
    })

# Pridanie nového produktu
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

# DOSKLADNIŤ PRODUKT
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

# Vymazanie produktu
@app.post("/admin/products/{product_id}/delete")
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

# PRIDANIE KUPÓNU V ADMINI
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

# VYMAZANIE KUPÓNU
@app.post("/admin/coupons/{coupon_id}/delete")
async def delete_coupon(coupon_id: int, db: Session = Depends(get_db)):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if coupon:
        db.delete(coupon)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)
