import os
import sqlite3
from fastapi import FastAPI, Depends, HTTPException, Request, Form, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

app = FastAPI()
security = HTTPBasic()

# Nastavenie šablón (absolútna cesta pre Render)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Inicializácia SQLite databázy so stĺpcom pre zľavy
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL,
            discount REAL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Overenie admina (Meno: admin, Heslo: matus123)
def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "admin" or credentials.password != "matus123":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávne prihlasovacie údaje",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Hlavná stránka e-shopu
@app.get("/")
def read_root(request: Request):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, stock, discount FROM products")
    products = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(request, "index.html", context={"products": products})

# Stránka administrácie (vyžaduje prihlásenie)
@app.get("/admin")
def admin_page(request: Request, username: str = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "admin.html")

# Spracowanie pridania produktu vrátane zľavy
@app.post("/admin/add-product")
def add_product(
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    discount: float = Form(0.0),
    username: str = Depends(verify_credentials)
):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, price, stock, discount) VALUES (?, ?, ?, ?)",
        (name, price, stock, discount)
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)
