from fastapi import FastAPI, Depends, Request, Form, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os
import secrets

# Načítanie databázového URL z Render Environment Group
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./shop.db"

# Oprava pre postgres:// na postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Vytvorenie engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ProductDB(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    description = Column(String)

# 🛠️ DOČASNÁ OPRAVA: Zmaže starú tabuľku a vytvorí novú so stĺpcom description
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

@app.get("/")
def read_root(request: Request, db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    return templates.TemplateResponse("index.html", {"request": request, "products": products})

@app.post("/admin/add-product")
def add_product(
    name: str = Form(...),
    price: float = Form(...),
    description: str = Form(...),
    username: str = Depends(verify_credentials),
    db: Session = Depends(get_db)
):
    new_product = ProductDB(name=name, price=price, description=description)
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/delete-product/{product_id}")
def delete_product(
    product_id: int,
    username: str = Depends(verify_credentials),
    db: Session = Depends(get_db)
):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()
    
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
