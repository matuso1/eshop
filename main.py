from fastapi import FastAPI, Depends, Request, Form, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os
import secrets

# Načítanie databázového URL z Render Environment Group (eshop-dc)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Fallback pre lokálne testovanie, ak nie je nastavene v env
    DATABASE_URL = "sqlite:///./shop.db"

# Oprava pre niektoré staršie SQLAlchemy dialekty PostgreSQL (postgres:// -> postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Definícia databázovej tabuľky (SQLAlchemy ORM - chráni pred SQL Injection)
class ProductDB(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    description = Column(String)

# Vytvorenie tabuliek v databáze
Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

# Dependency na získanie databázovej session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Overenie prihlasovacích údajov do administrácie
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

# Hlavná stránka - zoznam produktov (Chránené pred SQLi cez ORM, pred XSS cez Jinja2)
@app.get("/")
def read_root(request: Request, db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    return templates.TemplateResponse("index.html", {"request": request, "products": products})

# Administračné rozhranie - pridanie produktu (Chránené heslom)
@app.post("/admin/add-product")
def add_product(
    name: str = Form(...),
    price: float = Form(...),
    description: str = Form(...),
    username: str = Depends(verify_credentials),
    db: Session = Depends(get_db)
):
    # Bezpečný zápis cez ORM (žiadne surové SQL reťazce)
    new_product = ProductDB(name=name, price=price, description=description)
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

# Administračné rozhranie - zmazanie produktu (Chránené heslom)
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
