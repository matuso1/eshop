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
    conn.commit()
    conn.close()

init_db()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "admin" or credentials.password != "matus123":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávne prihlasovacie údaje",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Hlavná stránka (zoznam produktov pre zákazníka)
@app.get("/")
def read_root(request: Request, cart: str = Cookie(None)):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, stock, discount FROM products")
    products = cursor.fetchall()
    conn.close()
    
    # Spočítaj koľko položiek je v košíku
    cart_items = json.loads(cart) if cart else {}
    cart_count = sum(cart_items.values())
    
    return templates.TemplateResponse(
        request, 
        "index.html", 
        context={"products": products, "cart_count": cart_count}
    )

# Pridanie produktu do košíka (pomocou cookie)
@app.post("/cart/add/{product_id}")
def add_to_cart(product_id: int, cart: str = Cookie(None)):
    cart_items = json.loads(cart) if cart else {}
    
    # Zvýš množstvo v košíku
    str_id = str(product_id)
    cart_items[str_id] = cart_items.get(str_id, 0) + 1
    
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="cart", value=json.dumps(cart_items))
    return response

# Zobrazenie košíka a aplikovanie kupónu
@app.get("/cart")
def view_cart(request: Request, cart: str = Cookie(None), applied_coupon: str = Cookie(None)):
    cart_items = json.loads(cart) if cart else {}
    
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    products_in_cart = []
    subtotal = 0
    
    for str_id, quantity in cart_items.items():
        cursor.execute("SELECT id, name, price, stock, discount FROM products WHERE id = ?", (int(str_id),))
        row = cursor.fetchone()
        if row:
            prod_id, name, price, stock, discount = row
            final_item_price = price * (1 - discount / 100)
            item_total = final_item_price * quantity
            subtotal += item_total
            
            products_in_cart.append({
                "id": prod_id,
                "name": name,
                "price": price,
                "discount": discount,
                "final_item_price": final_item_price,
                "quantity": quantity,
                "item_total": item_total
            })
            
    # Overenie kupónu
    coupon_discount = 0
    if applied_coupon:
        cursor.execute("SELECT discount_percent FROM coupons WHERE code = ?", (applied_coupon.upper(),))
        row = cursor.fetchone()
        if row:
            coupon_discount = row[0]
            
    conn.close()
    
    total = subtotal * (1 - coupon_discount / 100)
    cart_count = sum(cart_items.values())
    
    return templates.TemplateResponse(
        request,
        "cart.html",
        context={
            "products_in_cart": products_in_cart,
            "subtotal": subtotal,
            "coupon_discount": coupon_discount,
            "applied_coupon": applied_coupon,
            "total": total,
            "cart_count": cart_count
        }
    )

# Aplikovanie kupónu v košíku
@app.post("/cart/apply-coupon")
def apply_coupon(coupon_code: str = Form(...)):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT discount_percent FROM coupons WHERE code = ?", (coupon_code.strip().upper(),))
    row = cursor.fetchone()
    conn.close()
    
    response = RedirectResponse(url="/cart", status_code=303)
    if row:
        response.set_cookie(key="applied_coupon", value=coupon_code.strip().upper())
    else:
        response.delete_cookie(key="applied_coupon")
    return response

@app.get("/cart/remove-coupon")
def remove_coupon():
    response = RedirectResponse(url="/cart", status_code=303)
    response.delete_cookie(key="applied_coupon")
    return response

# Vyprázdnenie košíka
@app.get("/cart/clear")
def clear_cart():
    response = RedirectResponse(url="/cart", status_code=303)
    response.delete_cookie(key="cart")
    response.delete_cookie(key="applied_coupon")
    return response

# Administrácia
@app.get("/admin")
def admin_page(request: Request, username: str = Depends(verify_credentials)):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, stock, discount FROM products")
    products = cursor.fetchall()
    cursor.execute("SELECT id, code, discount_percent FROM coupons")
    coupons = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(request, "admin.html", context={"products": products, "coupons": coupons})

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

@app.post("/admin/add-coupon")
def add_coupon(
    code: str = Form(...),
    discount_percent: float = Form(...),
    username: str = Depends(verify_credentials)
):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO coupons (code, discount_percent) VALUES (?, ?)",
            (code.strip().upper
