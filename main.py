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

def verify_admin_optional(request: Request) -> bool:
    """Overí, či je prihlásený admin (pre zobrazenie admin panela). Vráti True/False."""
    auth = request.headers.get("authorization")
    if not auth:
        return False
    try:
        import base64
        scheme, credentials = auth.split()
        if scheme.lower() == 'basic':
            decoded = base64.b64decode(credentials).decode("utf-8")
            username, password = decoded.split(":", 1)
            return secrets.compare_digest(username, ADMIN_USER) and secrets.compare_digest(password, ADMIN_PASS)
    except Exception:
        pass
    return False

# -------------------------------------------------------------------
# 3. DATABÁZOVÉ MODELY
# -------------------------------------------------------------------
class ProductDB(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    category = Column(String, default="Všeobecné")
    image_url = Column(String, default="https://picsum.photos/200/300")
    stock = Column(Integer, default=10)
    description = Column(String, default="")


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
    is_admin = verify_admin_optional(request)
    coupons = db.query(CouponDB).all() if is_admin else []
    return templates.TemplateResponse(
        request, 
        "index.html", 
        {
            "products": products, 
            "is_admin": is_admin, 
            "cart_count": 0, 
            "coupons": coupons
        }
    )


@app.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(HTTPBasic()),
    db: Session = Depends(get_db)
):
    # HTTP Basic overenie priamo pre /admin endpoint
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Neplatné prihlasovacie údaje",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    products = db.query(ProductDB).all()
    coupons = db.query(CouponDB).all()
    return templates.TemplateResponse(
        request, 
        "index.html", 
        {
            "products": products, 
            "is_admin": True, 
            "cart_count": 0, 
            "coupons": coupons
        }
    )


@app.get("/cart", response_class=HTMLResponse)
def cart_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "cart.html", {"cart_items": [], "cart_count": 0})


@app.post("/cart/add/{product_id}")
def add_to_cart(product_id: int):
    # Tu môžete neskôr doplniť logiku košíka (session/cookie)
    return RedirectResponse(url="/", status_code=303)


@app.post("/admin/add-product")
def add_product(
    name: str = Form(...),
    price: float = Form(...),
    category: str = Form(...),
    image_url: str = Form(...),
    stock: int = Form(...),
    description: str = Form(...),
    credentials: HTTPBasicCredentials = Depends(HTTPBasic()),
    db: Session = Depends(get_db)
):
    new_product = ProductDB(
        name=name, 
        price=price, 
        category=category, 
        image_url=image_url, 
        stock=stock, 
        description=description
    )
    db.add(new_product)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/admin/delete-product/{product_id}")
@app.get("/admin/delete-product/{product_id}")
def delete_product(
    product_id: int,
    credentials: HTTPBasicCredentials = Depends(HTTPBasic()),
    db: Session = Depends(get_db)
):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/admin/add-coupon")
def add_coupon(
    code: str = Form(...),
    discount_percent: float = Form(...),
    credentials: HTTPBasicCredentials = Depends(HTTPBasic()),
    db: Session = Depends(get_db)
):
    new_coupon = CouponDB(code=code.upper(), discount_percent=discount_percent)
    db.add(new_coupon)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/admin/delete-coupon/{coupon_id}")
@app.get("/admin/delete-coupon/{coupon_id}")
def delete_coupon(
    coupon_id: int,
    credentials: HTTPBasicCredentials = Depends(HTTPBasic()),
    db: Session = Depends(get_db)
):
    coupon = db.query(CouponDB).filter(CouponDB.id == coupon_id).first()
    if coupon:
        db.delete(coupon)
        db.commit()
    return RedirectResponse(url="/", status_code=303)
