import os
import sqlite3
import json
from fastapi import FastAPI, Request, Cookie
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# Session middleware je povinný pre OAuth, aby si pamätal stav prihlásenia
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "super-tajny-kluc"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Nastavenie Google OAuth (údaje si ťahá z premenných prostredia Renderu, prípadne doplňte)
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID', ''),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', ''),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

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

# --- GOOGLE OAUTH AUTENTIFIKÁCIA ---

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/auth/google")
async def login_google(request: Request):
    # Dynamicky zistí aktuálnu URL (funguje lokálne aj na Renderi)
    redirect_uri = request.url_for('auth_google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    if user_info:
        # Tu si môžete prípadne overiť, či je to váš email, napr. user_info.get('email') == 'vas.email@gmail.com'
        request.session['user'] = user_info
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin")
def admin_page(request: Request):
    user = request.session.get('user')
    if not user:
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
        context={"products": products, "coupons": coupons, "user": user}
    )

@app.post("/admin/restock/{product_id}")
def restock_product(product_id: int, request: Request):
    if not request.session.get('user'):
        return RedirectResponse(url="/login", status_code=303)
        
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET stock = stock + 1 WHERE id = ?", (product_id,))
        conn.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/add-product")
def add_product(
    request: Request,
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    discount: float = Form(0),
    image_url: str = Form("")
):
    if not request.session.get('user'):
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
def delete_product(product_id: int, request: Request):
    if not request.session.get('user'):
        return RedirectResponse(url="/login", status_code=303)
        
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE
