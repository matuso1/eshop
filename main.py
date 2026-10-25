import os
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. Databázová konfigurácia (načítava sa z DATABASE_URL z Renderu)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eshop.db")

# Zmena adresy ak Render vracia starý tvar postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Admin prihlasovacie údaje z Environment Variables
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "Matus123.")

# 2. Databázový model Produktu
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    image_url = Column(String, nullable=True)

# Vytvorenie tabuliek
Base.metadata.create_all(bind=engine)

# 3. Inicializácia FastAPI appky a šablón
app = FastAPI(title="eshop-7")
templates = Jinja2Templates(directory="templates")

# Závislosť na získanie DB relácie
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 4. ROUTY PRE VEREREJNÝ E-SHOP
@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return templates.TemplateResponse("index.html", {"request": request, "products": products})

# 5. ADMIN ROUTY

# Zobrazenie Admin panela
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return templates.TemplateResponse("admin.html", {"request": request, "products": products})

# Pridanie nového produktu
@app.post("/admin/products/add")
async def add_product(
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    image_url: str = Form(None),
    db: Session = Depends(get_db)
):
    new_product = Product(name=name, price=price, stock=stock, image_url=image_url)
    db.add(new_product)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

# FUNKCIA DOSKLADNIŤ (Pridanie kusov na sklad)
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
