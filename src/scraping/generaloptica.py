"""Scraper de gafas graduadas de General Óptica (Grupo De Rigo).

Necesita Selenium, al contrario que el de Óptica 2000: aquí el catálogo se
renderiza con JavaScript y una petición con requests devuelve la página vacía.

robots.txt: declara `Crawl-delay: 30` para User-agent *, y se respeta. Son unas
15 horas de rastreo. Las fichas de producto no están prohibidas; solo la ruta
interna /catalog/product/view/.

Sobre el sitemap: trae 4.938 URLs de graduadas y la categoría navegable declaraba
1.770 artículos, lo que hacía pensar que la diferencia era producto
descatalogado. El rastreo lo desmintió: salieron 4.825 fichas con precio, así que
solo unas 113 estaban de baja. El sitemap era el universo bueno. Las fichas sin
precio se marcan como error, que es la forma barata de filtrarlas.

    python src/scraping/generaloptica.py enumerar
    python src/scraping/generaloptica.py rastrear
    python src/scraping/generaloptica.py rastrear --limite 5 --espera 5

Se para con Ctrl+C y continúa al relanzarlo. Conviene lanzarlo como script suelto
y no desde un notebook, que muere al cerrar el portátil.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cola  # noqa: E402

TIENDA = "generaloptica"
BASE = "https://www.generaloptica.es"
SITEMAPS = [f"{BASE}/es/sitemap_es_es_{n}.xml" for n in ("001", "002", "003", "004")]
ESPERA = 30.0          # Crawl-delay declarado en su robots.txt. NO bajarlo.
TIMEOUT = 45

CABECERAS = {
    "User-Agent": (
        "ProyectoML-gafas/1.0 (proyecto académico de análisis de precios; "
        "contacto: juanantonio00m.moreno@gmail.com)"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}

PATRON_FICHA = re.compile(r"/es/gafas-graduadas-[^/]+\.html$")


# ---------------------------------------------------------------------------
# Enumeración (el sitemap sí se sirve como XML plano, no necesita navegador)
# ---------------------------------------------------------------------------
def enumerar() -> list[str]:
    urls: list[str] = []
    for sm in SITEMAPS:
        r = requests.get(sm, headers=CABECERAS, timeout=TIMEOUT)
        r.raise_for_status()
        urls += re.findall(r"<loc>([^<]+)</loc>", r.text)
        time.sleep(ESPERA)
    fichas = sorted({u for u in urls if PATRON_FICHA.search(u)})
    print(f"Sitemap: {len(urls)} URLs · {len(fichas)} fichas de graduadas")
    print("Las que estén descatalogadas se filtrarán solas al no tener precio.")
    return fichas


# ---------------------------------------------------------------------------
# Navegador
# ---------------------------------------------------------------------------
def crear_driver():
    """Chrome headless. Requiere `pip install selenium` y tener Chrome instalado;
    Selenium 4.6+ descarga el driver solo."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--disable-gpu")
    o.add_argument("--window-size=1400,1000")
    o.add_argument("--blink-settings=imagesEnabled=false")   # sin imágenes: más rápido
    o.add_argument(f"--user-agent={CABECERAS['User-Agent']}")
    o.add_argument("--lang=es-ES")
    d = webdriver.Chrome(options=o)
    d.set_page_load_timeout(TIMEOUT)
    return d


# ---------------------------------------------------------------------------
# Parseo
# ---------------------------------------------------------------------------
def _num_es(txt: str | None) -> float | None:
    """Formato español, para lo que se lee del DOM visible: punto = millares,
    coma = decimal. '1.234,50 €' -> 1234.5"""
    if not txt:
        return None
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d+))?", str(txt).replace("\xa0", " "))
    if not m:
        return None
    try:
        return float(f"{m.group(1).replace('.', '')}.{m.group(2) or '0'}")
    except ValueError:
        return None


def _num_maquina(v) -> float | None:
    """Formato del JSON-LD (offers.price), donde el punto es decimal.
    '125.250000' -> 125.25

    Confundirlo con el formato español convierte 125,25 € en 125.250 €.
    """
    if v is None:
        return None
    try:
        return round(float(str(v).strip()), 2)
    except (TypeError, ValueError):
        return None


# JavaScript que se ejecuta dentro de la ficha ya renderizada.
# Devuelve el JSON-LD de producto y el precio tachado, que solo está en el DOM.
JS_EXTRAER = r"""
const out = {url: location.href};
for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
  try {
    const data = JSON.parse(s.textContent);
    for (const o of (Array.isArray(data) ? data : [data])) {
      if (o && o['@type'] === 'Product') { out.jsonld = o; }
    }
  } catch (e) {}
}
const old = document.querySelector('.old-price .price, .old-price, [class*="old-price"]');
out.precio_anterior_txt = old ? old.textContent.trim() : null;
const t = document.body.innerText.replace(/\s+/g, ' ');
out.solo_montura = /solo\s+(la\s+)?montura|precio solo montura|solo incluye la montura/i.test(t);
const cal = t.match(/Calibre\s*([\d]{2})\s*x\s*([\d]{2})/i);
if (cal) { out.ancho_lente = +cal[1]; out.ancho_puente = +cal[2]; }
return JSON.stringify(out);
"""


def parsear(payload_json: str) -> dict:
    """Convierte lo que devolvió el navegador en campos limpios."""
    raw = json.loads(payload_json)
    ld = raw.get("jsonld") or {}
    d: dict = {"url": raw.get("url"), "tienda": TIENDA}

    d["nombre"] = ld.get("name")
    marca = ld.get("brand")
    d["marca"] = marca.get("name") if isinstance(marca, dict) else marca
    d["ean"] = ld.get("gtin13")
    d["sku"] = ld.get("sku")
    d["mpn"] = ld.get("mpn")
    d["color"] = ld.get("color")
    d["genero"] = ld.get("audience")
    d["material_montura"] = ld.get("material")

    ofertas = ld.get("offers") or {}
    if isinstance(ofertas, dict):
        d["precio_actual"] = _num_maquina(ofertas.get("price"))   # JSON-LD: punto decimal
        d["disponibilidad"] = ofertas.get("availability")

    d["precio_anterior"] = _num_es(raw.get("precio_anterior_txt"))   # DOM: formato español
    d["ancho_lente"] = raw.get("ancho_lente")
    d["ancho_puente"] = raw.get("ancho_puente")
    d["precio_solo_montura"] = bool(raw.get("solo_montura"))

    # El calibre también viene en el nombre: "... Talla: 51x21"
    if d["ancho_lente"] is None and d.get("nombre"):
        m = re.search(r"Talla:\s*(\d{2})\s*x\s*(\d{2})", d["nombre"], re.I)
        if m:
            d["ancho_lente"], d["ancho_puente"] = int(m.group(1)), int(m.group(2))

    d["en_oferta"] = d.get("precio_anterior") is not None
    d["descuento_pct"] = None
    if d["en_oferta"] and d.get("precio_actual"):
        d["descuento_pct"] = round(100 * (1 - d["precio_actual"] / d["precio_anterior"]), 2)

    # Target del modelo. Importa sobre todo aquí: esta tienda tenía una campaña
    # del 25 % a catálogo completo, así que `precio_actual` es la promoción de la
    # semana y el de catálogo es el tachado. Si la campaña acaba a mitad del
    # rastreo, `precio_anterior` desaparece y `precio_actual` ya es el PVP.
    d["pvp"] = d["precio_anterior"] if d["en_oferta"] else d.get("precio_actual")

    return d


# ---------------------------------------------------------------------------
# Rastreo
# ---------------------------------------------------------------------------
def rastrear(limite: int | None = None, espera: float = ESPERA) -> None:
    if espera < ESPERA:
        print(f"AVISO: su robots.txt pide Crawl-delay: {ESPERA:.0f}s y vas a usar "
              f"{espera:.0f}s. Solo para pruebas cortas.")

    con = cola.abrir("scrape.db")
    urls = cola.pendientes(con, TIENDA)
    if limite:
        urls = urls[:limite]
    if not urls:
        print("Nada pendiente. Ejecuta 'enumerar' primero o ya está todo hecho.")
        return

    horas = len(urls) * espera / 3600
    print(f"{len(urls)} fichas pendientes · espera {espera:.0f}s · "
          f"estimado {horas:.1f} h")
    print("Se puede parar con Ctrl+C y continuar relanzando el mismo comando.\n")

    driver = crear_driver()
    ok = fallos = sin_precio = 0
    try:
        for i, url in enumerate(urls, 1):
            try:
                driver.get(url)
                payload = driver.execute_script(JS_EXTRAER)
                d = parsear(payload)
                if d.get("precio_actual") is None:
                    # Descatalogado o sin stock: no es un fallo del scraper.
                    cola.guardar_error(con, url, "sin precio (descatalogado?)")
                    sin_precio += 1
                else:
                    cola.guardar_ok(con, url, payload, d.get("ean"))
                    ok += 1
            except Exception as e:                      # noqa: BLE001
                cola.guardar_error(con, url, f"{type(e).__name__}: {e}")
                fallos += 1
            if i % 10 == 0 or i == len(urls):
                print(f"  {i}/{len(urls)}  ok={ok} sin_precio={sin_precio} "
                      f"fallos={fallos}", flush=True)
            time.sleep(espera)
    except KeyboardInterrupt:
        print(f"\nInterrumpido. {ok} hechas en esta tanda. "
              f"Relanza el mismo comando para continuar.")
    finally:
        driver.quit()
        con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Scraper de General Óptica")
    p.add_argument("accion", choices=["enumerar", "rastrear"])
    p.add_argument("--limite", type=int, default=None)
    p.add_argument("--espera", type=float, default=ESPERA,
                   help=f"Segundos entre peticiones (por defecto {ESPERA:.0f}, su crawl-delay)")
    a = p.parse_args()

    if a.accion == "enumerar":
        con = cola.abrir("scrape.db")
        nuevas = cola.encolar(con, enumerar(), TIENDA)
        print(f"Encoladas {nuevas} URLs nuevas.")
        con.close()
    else:
        rastrear(a.limite, a.espera)
