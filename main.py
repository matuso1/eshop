import os
import sqlite3
from fastapi import FastAPI, Depends, HTTPException, Request, Form, status, Cookie
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import json

app = FastAPI()
security = HTTPBasic()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_percent REAL NOT NULL
        )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        default_products = [
            ("Jablko", 0.50, 10, 0),
            ("Banán", 1.20, 15, 5),
            ("Tričko", 19.99, 5, 10)
        ]
        cursor.executemany("INSERT INTO products (name, price, stock, discount) VALUES (?, ?, ?, ?)", default_products)

    conn.commit()
    conn.close()

init_db()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "admin" or credentials.password != "matus123":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávne prihlasovacie údaje",
            headers={"WWW-Authenticate": "Basic"}
        )
    return credentials.username

@app.get("/")
def read_root(request: Request, cart: str = Cookie(None)):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, stock, discount FROM products")
    products = cursor.fetchall()
    conn.close()
    
    cart_items = json.loads(cart) if cart else {}
    cart_count = sum(cart_items.values())
    
    return templates.TemplateResponse(
        request, 
        "index.html", 
        context={"products": products, "cart_count": cart_count}
    )

@app.post("/cart/add/{product_id}")
def add_to_cart(product_id: int, cart: str = Cookie(None)):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    
    if row and row[0] > 0:
        cursor.execute("UPDATE products SET stock = stock - 1 WHERE id = ?", (product_id,))
        conn.commit()
        
        cart_items = json.loads(cart) if cart else {}
        str_id = str(product_id)
        cart_items[str_id] = cart_items.get(str_id, 0) + 1
        
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="cart", value=json.dumps(cart_items))
    else:
        response = RedirectResponse(url="/", status_code=303)
        
    conn.close()
    return response

@app.get("/cart")
def view_cart(request: Request, cart: str = Cookie(None), applied_coupon: str = Cookie(None)):
    cart_items = json.loads(cart) if cart else {}
    
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    products_in_cart = []
    subtotal = 0
