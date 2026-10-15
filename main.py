from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import sqlite3
import secrets

app = FastAPI()
security = HTTPBasic()

# Inicializácia Jinja2 šablón
templates = Jinja2Templates(directory="templates")

# Nastavenie administrátorského hesla
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "matus123"

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávne meno alebo heslo",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Inicializácia SQLite databázy
def init_db():
    conn = sqlite3.connect("obchod.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produkty (
            nazov TEXT PRIMARY KEY,
            cena REAL,
            kategoria TEXT,
            pocet INTEGER,
            obrazok TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kosik (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nazov TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stav (
            kluc TEXT PRIMARY KEY,
            hodnota TEXT
        )
    """)
    
    # Predvolené dáta, ak je tabuľka prázdna
    cursor.execute("SELECT COUNT(*) FROM produkty")
    if cursor.fetchone()[0] == 0:
        počiatočné_produkty = [
            ("jablko", 0.50, "ovocie", 10, "https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?w=300"),
            ("hruska", 0.70, "ovocie", 5, "https://images.unsplash.com/photo-1514756318811-9ae71b12b59c?w=300"),
            ("banan", 0.40, "ovocie", 7, "https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?w=300"),
            ("mango", 1.50, "ovocie", 11, "https://images.unsplash.com/photo-1553279768-865429fa0078?w=300"),
            ("mlieko", 1.20, "mliecne", 2, "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=300"),
            ("jogurt", 0.80, "mliecne", 15, "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=300"),
            ("cukor", 1.10, "ostatne", 18, "https://images.unsplash.com/photo-1581441363689-1f3fef4c08cb?w=300"),
            ("cokolada", 1.30, "ostatne", 9, "https://images.unsplash.com/photo-1511381939415-e44015466834?w=300"),
        ]
        cursor.executemany("INSERT INTO produkty VALUES (?, ?, ?, ?, ?)", počiatočné_produkty)
        
    conn.commit()
    conn.close()

init_db()

kupony = {
    "malazlava": 10,
    "strednazlava": 20,
    "megazlava": 50
}

def zoskup_sklad_podla_kategorii():
    conn = sqlite3.connect("obchod.db")
    cursor = conn.cursor()
    cursor.execute("SELECT nazov, cena, kategoria, pocet, obrazok FROM produkty")
    rows = cursor.fetchall()
    conn.close()

    sklad = {}
    for r in rows:
        sklad[r[0]] = {"cena": r[1], "kategoria": r[2], "pocet": r[3], "obrazok": r[4]}

    kategorie = {}
    for nazov, info in sklad.items():
        kat = info["kategoria"]
        if kat not in kategorie:
            kategorie[kat] = {}
        kategorie[kat][nazov] = info
    return sklad, kategorie

def prepocitaj_nakup():
    conn = sqlite3.connect("obchod.db")
    cursor = conn.cursor()
    cursor.execute("SELECT nazov FROM kosik")
    nakupny_kosik = [row[0] for row in cursor.fetchall()]
    
    cursor.execute("SELECT hodnota FROM stav WHERE kluc='platna_zlava'")
    res = cursor.fetchone()
    platna_zlava = float(res[0]) if res else 0.0
    conn.close()

    sklad, _ = zoskup_sklad_podla_kategorii()
    medzisucet = 0.0
    polozky_v_kosiku = []

    for polozka in nakupny_kosik:
        if polozka in sklad:
            cena = sklad[polozka]["cena"]
            medzisucet += cena
            kat = sklad[polozka]["kategoria"]
            polozky_v_kosiku.append({"nazov": polozka, "cena": cena, "kategoria": kat})

    hodnota_zlavy = medzisucet * (platna_zlava / 100) if platna_zlava > 0 else 0.0
    celkova_cena = medzisucet - hodnota_zlavy

    return {
        "polozky": polozky_v_kosiku,
        "medzisucet": round(medzisucet, 2),
        "hodnota_zlavy": round(hodnota_zlavy, 2),
        "celkova_cena": round(celkova_cena, 2),
        "platna_zlava": int(platna_zlava)
    }

@app.get("/", response_class=HTMLResponse)
async def domov(request: Request):
    sklad, sklad_kategorie = zoskup_sklad_podla_kategorii()
    vysledky = prepocitaj_nakup()
    
    conn = sqlite3.connect("obchod.db")
    cursor = conn.cursor()
    cursor.execute("SELECT hodnota FROM stav WHERE kluc='vypredane'")
    vyp_row = cursor.fetchone()
    vypredane_polozky = vyp_row[0].split(",") if vyp_row and vyp_row[0] else []

    cursor.execute("SELECT hodnota FROM stav WHERE kluc='uplatneny_kupon'")
    kup_row = cursor.fetchone()
    uplatneny_kupon_kod = kup_row[0] if kup_row else ""
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "sklad": sklad,
            "sklad_kategorie": sklad_kategorie,
            "kosik_polozky": vysledky["polozky"],
            "medzisucet": vysledky["medzisucet"],
            "hodnota_zlavy": vysledky["hodnota_zlavy"],
            "celkova_cena": vysledky["celkova_cena"],
            "platna_zlava": vysledky["platna_zlava"],
            "vypredane_polozky": vypredane_polozky,
            "uplatneny_kupon": uplatneny_kupon_kod
        }
    )

@app.post("/pridat")
async def pridat_do_kosika(produkt: str = Form(...)):
    conn = sqlite3.connect("obchod.db")
    cursor = conn.cursor()
    cursor.execute("SELECT pocet FROM produkty WHERE nazov = ?", (produkt,))
    row = cursor.fetchone()
    
    if row and row[0] > 0:
        cursor.execute("UPDATE produkty SET pocet = pocet - 1 WHERE nazov = ?", (produkt,))
        cursor.execute("INSERT INTO kosik (nazov) VALUES (?)", (produkt,))
    else:
        cursor.execute("SELECT hodnota FROM stav WHERE kluc='vypredane'")
        vyp_row = cursor.fetchone()
        vypredane = vyp_row[0].split(",") if vyp_row and vyp_row[0] else []
        if produkt not in vypredane:
            vypredane.append(produkt)
            cursor.execute("INSERT OR REPLACE INTO stav (kluc, hodnota) VALUES ('vypredane', ?)", (",".join(vypredane),))
            
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/kupon")
async def aplikuj_kupon(kod: str = Form(...)):
    kod_clean = kod.strip()
    conn = sqlite3.connect("obchod.db")
    cursor = conn.cursor()
    
    if kod_clean in kupony:
        zlava = kupony[kod_clean]
        cursor.execute("INSERT OR REPLACE INTO stav (kluc, hodnota) VALUES ('platna_zlava', ?)", (str(zlava),))
        cursor.execute("INSERT OR REPLACE INTO stav (kluc, hodnota) VALUES ('uplatneny_kupon', ?)", (kod_clean,))
    else:
        cursor.execute("INSERT OR REPLACE INTO stav (kluc, hodnota) VALUES ('platna_zlava', '0')",)
        cursor.execute("INSERT OR REPLACE INTO stav (kluc, hodnota) VALUES ('uplatneny_kupon', 'NEPLATNY')",)
        
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin", response_class=HTMLResponse)
async def admin_stranka(request: Request, username: str = Depends(verify_admin)):
    _, sklad_kategorie = zoskup_sklad_podla_kategorii()
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"sklad_kategorie": sklad_kategorie}
    )

@app.post("/admin/doplnit")
async def doplnit_sklad(produkt: str = Form(...), pocet: int = Form(...), username: str = Depends(verify_admin)):
    if pocet > 0:
        conn = sqlite3.connect("obchod.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE produkty SET pocet = pocet + ? WHERE nazov = ?", (pocet, produkt))
        conn.commit()
        conn.close()
    return RedirectResponse(url="/admin", status_code=303)
