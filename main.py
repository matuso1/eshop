import os
import sqlite3
import json
from fastapi import FastAPI, Request, Form, Cookie
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

def init_db():
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL,
                discount REAL DEFAULT 0,
                image_url TEXT
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

init_db()

@app.get("/")
def read_root(request: Request, cart: str = Cookie(None)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, price, stock, discount, image_url FROM products")
        products = cursor.fetchall()
    
    cart_items = json.loads(cart) if cart else {}
    cart_count = sum(cart_items.values())
    
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"products": products, "cart_count": cart_count}
    )

@app.post("/cart/add/{product_id}")
def add_to_cart(product_id: int, cart: str = Cookie(None)):
    with sqlite3.connect("database.db") as conn:
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
            response.set_cookie(key="cart", value=json.dumps(cart_items), path="/")
        else:
            response = RedirectResponse(url="/", status_code=303)
            
    return response

@app.get("/cart")
def view_cart(request: Request, cart: str = Cookie(None), applied_coupon: str = Cookie(None)):
    cart_items = json.loads(cart) if cart else {}
    
    products_in_cart = []
    subtotal = 0.0
    
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        for str_id, quantity in cart_items.items():
            cursor.execute("SELECT id, name, price, stock, discount, image_url FROM products WHERE id = ?", (int(str_id),))
            row = cursor.fetchone()
            if row:
                prod_id, name, price, stock, discount, image_url = row
                final_item_price = price * (1.0 - discount / 100.0)
                item_total = final_item_price * quantity
                subtotal += item_total
                
                products_in_cart.append({
                    "id": prod_id,
                    "name": name,
                    "price": price,
                    "discount": discount,
                    "final_item_price": final_item_price,
                    "quantity": quantity,
                    "item_total": item_total,
                    "image_url": image_url
                })
                
        coupon_discount = 0.0
        if applied_coupon:
            cursor.execute("SELECT discount_percent FROM coupons WHERE code = ?", (applied_coupon.upper(),))
            row = cursor.fetchone()
            if row:
                coupon_discount = float(row[0])
    
    total = subtotal * (1.0 - coupon_discount / 100.0)
    cart_count = sum(cart_items.values())
    
    return templates.TemplateResponse(
        request=request,
        name="cart.html",
        context={
            "products_in_cart": products_in_cart,
            "subtotal": subtotal,
            "coupon_discount": coupon_discount,
            "applied_coupon": applied_coupon,
            "total": total,
            "cart_count": cart_count
        }
    )

@app.post("/cart/apply-coupon")
def apply_coupon(coupon_code: str = Form(...)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT discount_percent FROM coupons WHERE code = ?", (coupon_code.strip().upper(),))
        row = cursor.fetchone()
    
    response = RedirectResponse(url="/cart", status_code=303)
    if row:
        response.set_cookie(key="applied_coupon", value=coupon_code.strip().upper(), path="/")
    else:
        response.delete_cookie(key="applied_coupon", path="/")
    return response

@app.get("/cart/remove-coupon")
def remove_coupon():
    response = RedirectResponse(url="/cart", status_code=303)
    response.delete_cookie(key="applied_coupon", path="/")
    return response

@app.get("/cart/clear")
def clear_cart(cart: str = Cookie(None)):
    if cart:
        try:
            cart_items = json.loads(cart)
            with sqlite3.connect("database.db") as conn:
                cursor = conn.cursor()
                for str_id, quantity in cart_items.items():
                    cursor.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (quantity, int(str_id)))
                conn.commit()
        except Exception:
            pass

    response = RedirectResponse(url="/cart", status_code=303)
    response.delete_cookie(key="cart", path="/")
    response.delete_cookie(key="applied_coupon", path="/")
    return response

# --- OPRAVENÉ PRIHLÁSENIE S HTTPS COOKIE PODPOROU ---

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == "admin" and password == "matus123":
        response = RedirectResponse(url="/admin", status_code=303)
        # Nastavíme cookie tak, aby prešla cez Render HTTPS proxy bez zablokovania
        is_secure = request.url.scheme == "https"
        response.set_cookie(
            key="admin_logged", 
            value="true", 
            path="/", 
            secure=is_secure, 
            httponly=False, 
            samesite="lax"
        )
        return response
    else:
        return RedirectResponse(url="/login", status_code=303)

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="admin_logged", path="/")
    return response

@app.get("/admin")
def admin_page(request: Request, admin_logged: str = Cookie(None)):
    if admin_logged != "true":
        return RedirectResponse(url="/login", status_code=303)
        
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, price, stock, discount, image_url FROM products")
        products = cursor.fetchall()
        cursor.execute("SELECT id, code, discount_percent FROM coupons")
        coupons = cursor.fetchall()
    
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"products": products, "coupons": coupons}
    )

@app.post("/admin/restock/{product_id}")
def restock_product(product_id: int, admin_logged: str = Cookie(None)):
    if admin_logged != "true":
        return RedirectResponse(url="/login", status_code=303)
        
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET stock = stock + 1 WHERE id = ?", (product_id,))
        conn.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/add-product")
def add_product(
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    discount: float = Form(0),
    image_url: str = Form(""),
    admin_logged: str = Cookie(None)
):
    if admin_logged != "true":
        return RedirectResponse(url="/login", status_code=303)
        
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO products (name, price, stock, discount, image_url) VALUES (?, ?, ?, ?, ?)",
            (name.strip(), price, stock, discount, image_url.strip())
        )
        conn.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete-product/{product_id}")
def delete_product(product_id: int, admin_logged: str = Cookie(None)):
    if admin_logged != "true":
        return RedirectResponse(url="/login", status_code=303)
        
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/add-coupon")
def add_coupon(
    code: str,
    discount_percent: float,
    admin_logged: str = Cookie(None)
):
    if admin_logged != "true":
        return RedirectResponse(url="/login", status_code=303)
        
    with sqlite3.connect("database.db") as loc_conn:
        cursor = loc_conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO coupons (code, discount_percent) VALUES (?, ?)",
                (code.strip().upper(), discount_percent)
            )
            loc_conn.commit()
        except sqlite3.IntegrityError:
            pass
    return RedirectResponse(url="/admin", status_code=303)
