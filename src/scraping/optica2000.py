"""Scraper de gafas graduadas de Óptica 2000 (Grandvisión / EssilorLuxottica).

Renderiza en servidor, así que basta requests: el HTML de una petición normal ya
trae precio, atributos y medidas.

robots.txt (1 ago 2026): para User-agent * solo prohíbe /cancela-tu-cita y
/reprograma-tu-cita. No declara Crawl-delay; se usa 1 s.

    python src/scraping/optica2000.py enumerar     # sitemap -> cola
    python src/scraping/optica2000.py rastrear     # cola -> base de datos
    python src/scraping/optica2000.py rastrear --limite 50

Se puede parar con Ctrl+C y relanzar: continúa por donde iba.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cola  # noqa: E402

TIENDA = "optica2000"
BASE = "https://www.optica2000.com"
SITEMAP = f"{BASE}/sitemap.xml"
ESPERA = 1.0          # segundos entre peticiones
TIMEOUT = 30

CABECERAS = {
    "User-Agent": (
        "ProyectoML-gafas/1.0 (proyecto académico de análisis de precios; "
        "contacto: juanantonio00m.moreno@gmail.com)"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}

# Las fichas cuelgan de /gafas-graduadas/{slug}/{EAN de 13 dígitos}
PATRON_FICHA = re.compile(r"/gafas-graduadas/[^/]+/(\d{8,})$")


# ---------------------------------------------------------------------------
# Enumeración
# ---------------------------------------------------------------------------
def enumerar() -> list[str]:
    """URLs de ficha del sitemap. Se enumera de ahí y no de las categorías
    porque es la vía que el sitio publica para ser rastreado, y porque las
    categorías paginan de 24 en 24."""
    r = requests.get(SITEMAP, headers=CABECERAS, timeout=TIMEOUT)
    r.raise_for_status()
    urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
    fichas = sorted({u for u in urls if PATRON_FICHA.search(u)})
    print(f"Sitemap: {len(urls)} URLs · {len(fichas)} fichas de graduadas")
    return fichas


# ---------------------------------------------------------------------------
# Parseo
# ---------------------------------------------------------------------------
def _num(txt: str | None) -> float | None:
    """Formato español: punto = millares, coma = decimal.
    '169,90 €' -> 169.9 · '123 mm' -> 123.0"""
    if not txt:
        return None
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d+))?", txt.replace("\xa0", " "))
    if not m:
        return None
    entero = m.group(1).replace(".", "")
    dec = m.group(2) or "0"
    try:
        return float(f"{entero}.{dec}")
    except ValueError:
        return None


def _num_maquina(v) -> float | None:
    """Formato del JSON-LD de schema.org: el punto es decimal.
    '125.250000' -> 125.25

    Pasarlo por _num() daría 125.250 €: no revienta, solo multiplica por mil.
    """
    if v is None:
        return None
    try:
        return round(float(str(v).strip()), 2)
    except (TypeError, ValueError):
        return None


ETIQUETAS = {
    "Frente de color": "color",
    "Material de la montura": "material_montura",
    "Forma de la montura": "forma",
    "Tipo de montura": "tipo_montura",
    "Género": "genero",
    "Ancho de la montura": "ancho_montura",
    "Ancho del puente": "ancho_puente",
    "Ancho de la lente": "ancho_lente",
    "Longitud de varilla": "largo_varilla",
}


def parsear(html: str, url: str) -> dict:
    """Extrae los campos de una ficha: primero JSON-LD si lo hay, y si no las
    etiquetas de texto en español."""
    sopa = BeautifulSoup(html, "html.parser")
    # Todas las claves declaradas de entrada aunque queden a None: si un campo
    # solo apareciera cuando existe, el CSV tendría columnas distintas según la
    # ficha.
    d: dict = {
        "url": url, "tienda": TIENDA, "ean": None, "nombre": None, "marca": None,
        "mpn": None, "color": None, "material_montura": None, "forma": None,
        "tipo_montura": None, "genero": None, "ancho_montura": None,
        "ancho_puente": None, "ancho_lente": None, "largo_varilla": None,
        "modelo": None, "precio_actual": None, "precio_anterior": None,
        "pvp": None, "en_oferta": False, "descuento_pct": None, "outlet": False,
        "precio_solo_montura": False, "disponible": True, "venta_online": False,
    }

    m = PATRON_FICHA.search(url)
    d["ean"] = m.group(1) if m else None

    # --- 1. JSON-LD ---
    for s in sopa.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "{}")
        except json.JSONDecodeError:
            continue
        for obj in (data if isinstance(data, list) else [data]):
            if not isinstance(obj, dict) or obj.get("@type") != "Product":
                continue
            # No sirve d.setdefault(): las claves ya existen con valor None y
            # setdefault solo escribe si faltan.
            def poner(clave, valor):
                if d.get(clave) is None and valor is not None:
                    d[clave] = valor

            poner("nombre", obj.get("name"))
            marca = obj.get("brand")
            poner("marca", marca.get("name") if isinstance(marca, dict) else marca)
            poner("mpn", obj.get("mpn"))
            poner("ean", obj.get("gtin13"))
            ofertas = obj.get("offers") or {}
            if isinstance(ofertas, dict):
                # JSON-LD: punto decimal, NO formato español
                poner("precio_actual", _num_maquina(ofertas.get("price")))

    # --- 2. Texto ---
    # Los scripts se quitan aquí y no antes, porque el JSON-LD vive dentro de
    # uno. Hay que quitarlos: el bundle de JS trae todas las cadenas de interfaz
    # posibles ("Añadir al carrito", "Este producto no está disponible"), así que
    # buscarlas sin limpiar da positivo en el 100 % de las fichas.
    for etiqueta in sopa(["script", "style", "noscript"]):
        etiqueta.decompose()

    texto = sopa.get_text("\n", strip=True)
    lineas = [l for l in texto.split("\n") if l]

    if not d.get("nombre"):
        h1 = sopa.find("h1")
        d["nombre"] = h1.get_text(strip=True) if h1 else None

    # Etiqueta y valor van en líneas consecutivas.
    for i, linea in enumerate(lineas[:-1]):
        campo = ETIQUETAS.get(linea.strip())
        if campo and d.get(campo) is None:
            valor = lineas[i + 1].strip()
            d[campo] = _num(valor) if campo.startswith(("ancho", "largo")) else valor

    # --- Precios ---
    # En la ficha los trozos van en nodos separados ("ahora:" / "38 €" /
    # "antes:" / "76 €"), así que se aplana el texto para que queden contiguos.
    plano = re.sub(r"\s+", " ", texto)

    # La financiación fuera antes de buscar precios: "o 3 x 56,33 € sin
    # intereses" se colaría como precio del producto.
    plano_precios = re.sub(
        r"o?\s*\d+\s*x\s*[\d.,]+\s*€\s*sin\s+intereses", " ", plano, flags=re.I
    )

    ahora_m = re.search(r"ahora:\s*([\d.,]+)\s*€", plano_precios, re.I)
    antes_m = re.search(r"antes:\s*([\d.,]+)\s*€", plano_precios, re.I)
    if ahora_m and antes_m:
        d["precio_actual"] = _num(ahora_m.group(1))
        d["precio_anterior"] = _num(antes_m.group(1))
    elif d.get("precio_actual") is None:
        m2 = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?)\s*€", plano_precios)
        if m2:
            d["precio_actual"] = _num(m2.group(1))

    d["en_oferta"] = d.get("precio_anterior") is not None
    if d["en_oferta"] and d.get("precio_actual"):
        d["descuento_pct"] = round(100 * (1 - d["precio_actual"] / d["precio_anterior"]), 2)

    # Target del modelo: con oferta, el PVP es el precio tachado; sin ella, el
    # precio a secas ya es el de catálogo.
    d["pvp"] = d["precio_anterior"] if d["en_oferta"] else d["precio_actual"]

    # "OUTLET" es también una entrada del menú, así que buscarlo en toda la
    # página lo daba True en el 100 % de las fichas. Solo cuenta pegado al precio.
    d["outlet"] = False
    if ahora_m:
        ventana = plano_precios[ahora_m.start(): ahora_m.start() + 120]
        d["outlet"] = "OUTLET" in ventana

    # Sello de que el precio es de la montura sola, no de un pack
    d["precio_solo_montura"] = bool(
        re.search(r"solo\s+(a\s+la|la)?\s*montura", plano, re.I)
    )

    # Descatalogado o sin stock: la ficha responde 200 y tiene marca y modelo,
    # pero ni precio ni atributos. El sitemap las sigue listando.
    d["disponible"] = "Este producto no está disponible" not in plano

    # Distinto de estar agotado: el producto existe pero no se vende por web,
    # solo en tienda. Afecta al 25 % del catálogo, repartido de forma desigual
    # entre marcas.
    d["venta_online"] = bool(re.search(r"A[ñn]adir al carrito", plano, re.I))

    # --- Marca y modelo, desde las migas de pan ---
    #     <ul class="breadcrumbs">
    #       <li>GAFAS GRADUADAS</li>
    #       <li>Armani Exchange</li>                           <- marca
    #       <li class="...current-page-text">AX3077 8001</li>  <- modelo
    #
    # Hay que coger los <li> hijos DIRECTOS: los envoltorios y los <a> internos
    # también llevan "breadcrumb" en la clase, y recorriéndolos todos el modelo
    # sale con el nombre de la marca.
    #
    # No sirve el enlace a /gafas-graduadas/{marca}: solo existe para las 9
    # marcas del menú, así que Arnette, DbyD y el resto quedarían sin marca.
    # Además las migas dan la grafía correcta ("Dolce&Gabbana"), que el respaldo
    # por slug convertiría en "Dolcegabbana".
    migas: list[str] = []
    ul = sopa.find("ul", class_=re.compile("breadcrumb", re.I))
    if ul:
        migas = [li.get_text(strip=True) for li in ul.find_all("li", recursive=False)]
        migas = [m for m in migas if m]

    if len(migas) >= 2:
        d["modelo"] = migas[-1]
        d["marca"] = d.get("marca") or migas[-2]
    elif migas:
        d["modelo"] = migas[-1]

    # Respaldos, por si cambia el maquetado
    if not d.get("marca"):
        h1 = (d.get("nombre") or "").strip()
        if h1 and d.get("modelo") and h1.endswith(d["modelo"]):
            d["marca"] = h1[: -len(d["modelo"])].strip() or None
        elif h1:
            # Prefijo del slug hasta el primer trozo con 3+ dígitos
            slug = url.rstrip("/").split("/")[-2] if "/" in url else ""
            marca = []
            for p in slug.split("-"):
                if re.search(r"\d{3,}", p):
                    break
                marca.append(p)
            d["marca"] = " ".join(marca).title() or None

    return d


# ---------------------------------------------------------------------------
# Comprobaciones del parser
# ---------------------------------------------------------------------------
def autotest() -> None:
    """Comprueba el parser contra fichas sintéticas copiadas del maquetado real.
    No toca la red.

        python src/scraping/optica2000.py autotest
    """
    # Los precios van en nodos separados, como en la ficha real. Un fixture con
    # "ahora: 38 € antes: 76 €" en una sola línea pasaría el test sin comprobar
    # el caso que de verdad ocurre.
    base = (
        "<html><body>"
        # El OUTLET del menú va aquí a propósito: sin él el test no detecta el
        # falso positivo.
        "<nav><a>GAFAS DE SOL</a><a>OUTLET</a><a>PROMOCIONES</a></nav>"
        "<h1>Ray-Ban 0RX6448 3094</h1>"
        "<div>0.0</div><div>No se encontraron reviews para este producto</div>"
        "{precio}"
        "<div>o 3 x 56,33 € sin intereses</div>"
        "<div>Rosa</div><div>Entrega estimada jue 6 ago - lun 10 ago</div>"
        "<div>Añadir al carrito</div>"
        "<div>El precio indicado se corresponde solo a la montura. Pide cita "
        "para consultar el precio final con tu graduación</div>"
        "<div>Frente de color</div><div>Rosa</div>"
        "<div>Material de la montura</div><div>Metal</div>"
        "<div>Forma de la montura</div><div>Hexagonal</div>"
        "<div>Tipo de montura</div><div>Aro Completo</div>"
        "<div>Género</div><div>Unisex, Hombre, Mujer</div>"
        "<div>Ancho de la montura</div><div>123 mm</div>"
        "<div>Ancho del puente</div><div>21 mm</div>"
        "<div>Ancho de la lente</div><div>51 mm</div>"
        "<div>Longitud de varilla</div><div>145 mm</div>"
        "<div>Suscríbete a la Newsletter y recibe un -10% de descuento</div>"
        "</body></html>"
    )
    sin = parsear(base.format(precio="<div>169 €</div>"),
                  "https://x/gafas-graduadas/y/8056597266673")
    con = parsear(
        base.format(precio="<div>ahora:</div><div>38 €</div>"
                           "<div>antes:</div><div>76 €</div>"
                           "<div>-50%</div><div>OUTLET</div>"),
        "https://x/gafas-graduadas/y/8056597941723")

    assert _num("1.234,50 €") == 1234.50, "formato español mal parseado"
    assert _num_maquina("125.250000") == 125.25, "formato máquina mal parseado"

    assert sin["ean"] == "8056597266673"
    # 169 y no 56,33, que es la cuota de financiación
    assert sin["precio_actual"] == 169.0, f"cogió la financiación: {sin['precio_actual']}"
    assert sin["precio_anterior"] is None
    assert sin["en_oferta"] is False and sin["descuento_pct"] is None
    assert sin["outlet"] is False
    assert sin["color"] == "Rosa" and sin["material_montura"] == "Metal"
    assert sin["forma"] == "Hexagonal" and sin["tipo_montura"] == "Aro Completo"
    assert sin["genero"] == "Unisex, Hombre, Mujer"
    assert sin["ancho_lente"] == 51.0 and sin["ancho_puente"] == 21.0
    assert sin["ancho_montura"] == 123.0 and sin["largo_varilla"] == 145.0
    assert sin["precio_solo_montura"] is True

    assert con["precio_actual"] == 38.0 and con["precio_anterior"] == 76.0
    assert con["en_oferta"] is True and con["descuento_pct"] == 50.0
    assert con["outlet"] is True
    # 50 y no 10: el "-10% de descuento" de la newsletter no contamina
    assert con["descuento_pct"] == 50.0

    assert set(sin) == set(con), "las dos fichas deben dar las mismas columnas"

    # Marca y modelo. Incluye marcas sin página de categoría (Arnette, DbyD,
    # Nanovista) y reproduce los <li> envoltorios y los <a> internos del
    # maquetado real; sin ellos el test no detecta que el modelo salga con el
    # nombre de la marca.
    casos = [
        ("Armani Exchange AX3077 8001", "Armani Exchange", "AX3077 8001"),
        ("Arnette 0AN7183 2718", "Arnette", "0AN7183 2718"),
        ("DbyD DB1159 2", "DbyD", "DB1159 2"),
        ("Dolce&Gabbana DG3421 3200", "Dolce&Gabbana", "DG3421 3200"),
        ("Nanovista CAMPER NAO3040146 1", "Nanovista", "CAMPER NAO3040146 1"),
    ]
    for h1, marca_esp, modelo_esp in casos:
        html = (
            "<html><body><nav><a>OUTLET</a></nav>"
            '<ul class="breadcrumbs">'
            '<li class="breadcrumbs__link-wrapper"><a class="breadcrumbs__link">'
            "GAFAS GRADUADAS</a></li>"
            f'<li class="breadcrumbs__link-wrapper"><a class="breadcrumbs__link">'
            f"{marca_esp}</a></li>"
            f'<li class="breadcrumbs__current-page-text">{modelo_esp}</li>'
            "</ul>"
            f"<h1>{h1}</h1><div>105 €</div>"
            "<div>Material de la montura</div><div>Metal</div></body></html>"
        )
        r = parsear(html, "https://x/gafas-graduadas/slug-ax3077-8001/8000000000001")
        assert r["marca"] == marca_esp, f"marca: {r['marca']!r} != {marca_esp!r}"
        assert r["modelo"] == modelo_esp, f"modelo: {r['modelo']!r} != {modelo_esp!r}"

    # Sin migas de pan: se recurre al prefijo del slug de la URL
    r = parsear("<html><body><h1>Ray-Ban 0RX6448 3094</h1><div>169 €</div></body></html>",
                "https://x/gafas-graduadas/ray-ban-0rx6448-3094-51-21/8056597266673")
    assert r["marca"] == "Ray Ban", f"fallback de slug: {r['marca']!r}"

    print(f"autotest OK · {len(sin)} columnas por ficha · marca verificada en "
          f"{len(casos)} casos reales + fallback")


# ---------------------------------------------------------------------------
# Rastreo
# ---------------------------------------------------------------------------
def rastrear(limite: int | None = None, mezclar: bool = False) -> None:
    con = cola.abrir("scrape.db")
    urls = cola.pendientes(con, TIENDA)
    if mezclar:
        # Barajado con semilla fija, para que sea reproducible. El sitemap va
        # alfabético: sin esto las 80 primeras fichas fueron las 80 de Armani
        # Exchange, y una interrupción deja media muestra del abecedario.
        random.Random(42).shuffle(urls)
    if limite:
        urls = urls[:limite]
    if not urls:
        print("Nada pendiente. Ejecuta 'enumerar' primero o ya está todo hecho.")
        return

    print(f"{len(urls)} fichas pendientes · espera {ESPERA}s "
          f"· estimado {len(urls) * ESPERA / 60:.0f} min")
    sesion = requests.Session()
    sesion.headers.update(CABECERAS)
    ok = fallos = no_disp = 0

    try:
        for i, url in enumerate(urls, 1):
            try:
                r = sesion.get(url, timeout=TIMEOUT)
                r.raise_for_status()
                d = parsear(r.text, url)
                if d.get("precio_actual") is None:
                    # Descatalogado o sin stock: no es un fallo del scraper, se
                    # aparta para que no ensucie el dataset.
                    cola.guardar_error(con, url, "sin precio (no disponible)")
                    no_disp += 1
                else:
                    cola.guardar_ok(con, url, r.text, d.get("ean"))
                    ok += 1
            except Exception as e:                      # noqa: BLE001
                cola.guardar_error(con, url, f"{type(e).__name__}: {e}")
                fallos += 1
            if i % 25 == 0 or i == len(urls):
                print(f"  {i}/{len(urls)}  ok={ok} no_disponibles={no_disp} "
                      f"fallos={fallos}", flush=True)
            time.sleep(ESPERA)
    except KeyboardInterrupt:
        print(f"\nInterrumpido. {ok} hechas en esta tanda. "
              f"Relanza el mismo comando para continuar.")
    finally:
        con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Scraper de Óptica 2000")
    p.add_argument("accion", choices=["enumerar", "rastrear", "autotest"])
    p.add_argument("--limite", type=int, default=None,
                   help="Rastrear solo N fichas (para probar)")
    p.add_argument("--mezclar", action="store_true",
                   help="Orden barajado reproducible: una tanda corta cubre "
                        "varias marcas en vez de solo las primeras del abecedario")
    a = p.parse_args()

    if a.accion == "autotest":
        autotest()
    elif a.accion == "enumerar":
        con = cola.abrir("scrape.db")
        nuevas = cola.encolar(con, enumerar(), TIENDA)
        print(f"Encoladas {nuevas} URLs nuevas.")
        con.close()
    else:
        rastrear(a.limite, a.mezclar)
