import os
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Float
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

# 2. Databázový model Produktu
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    discount_price = Column(Float, nullable=True)
    stock = Column(Integer, default=0)
    image_url = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="eshop-7")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 4. VEREJNÝ E-SHOP S TRIEDENÍM (SORT)
@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request, sort: str = None, db: Session = Depends(get_db)):
    query = db.query(Product)
    
    # Logika pre triedenie
    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    elif sort == "name_asc":
        query = query.order_by(Product.name.asc())
    elif sort == "name_desc":
        query = query.order_by(Product.name.desc())
        
    products = query.all()
    return templates.TemplateResponse(request, "index.html", {"request": request, "products": products, "current_sort": sort})

# 5. ADMIN ROUTY
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return templates.TemplateResponse(request, "admin.html", {"request": request, "products": products})

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
