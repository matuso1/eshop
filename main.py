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

# Tabuľka produktov (vrátane kategórie a image_url)
class ProductDB(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    description = Column(String)
    category = Column(String, index=True)
    image_url = Column(String)

# Tabuľka pre nákupný košík
class CartItemDB(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    
    product = relationship("ProductDB")

# DOČASNÉ: Vymaže starú štruktúru a vytvorí novú (vyrieši chybu s chýbajúcimi stĺpcami)
# POZNÁMKA: Po úspešnom deployi tento riadok (drop_all) môžete zmazať, aby vám dáta ostávali.
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "matus123")
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávne meno alebo heslo",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

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
    total_price = sum(item.product.price * item.quantity for item in cart_items if item.product)
    cart_count = db.query(CartItemDB).count()
    return templates.TemplateResponse(request, "cart.html", {
        "cart_items": cart_items,
        "total_price": total_price,
        "cart_count": cart_count
    })

@app.post("/cart/add/{product_id}")
def add_to_cart(product_id: int, db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produkt neexistuje")
    
    cart_item = db.query(CartItemDB).filter(CartItemDB.product_id == product_id).first()
    if cart_item:
        cart_item.quantity += 1
    else:
        cart_item = CartItemDB(product_id=product_id, quantity=1)
        db.add(cart_item)
    
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

# --- ADMIN CESTY ---

@app.get("/admin")
def admin_page(request: Request, username: str = Depends(verify_credentials), db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    cart_count = db.query(CartItemDB).count()
    return templates.TemplateResponse(request, "index.html", {
        "products": products, 
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
    username: str = Depends(verify_credentials),
    db: Session = Depends(get_db)
):
    # Ochrana proti XSS a čistenie vstupov
    clean_name = html.escape(name.strip().lower(), quote=True)
    clean_category = html.escape(category.strip().lower(), quote=True)

    # Kontrola duplicity (názov + kategória)
    existing_product
