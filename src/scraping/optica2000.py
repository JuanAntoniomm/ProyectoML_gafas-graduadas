"""
optica2000.py
=============

Scraper de gafas graduadas de Óptica 2000 (Grandvisión Spain / EssilorLuxottica).

Por qué esta tienda se rastrea con requests y no con navegador:
    Óptica 2000 renderiza en servidor. El HTML que devuelve una petición normal
    ya trae precio, atributos y medidas. No hace falta Selenium. Comprobado el
    1 ago 2026.

Cumplimiento (robots.txt comprobado el 1 ago 2026):
    Para User-agent: * solo prohíbe /cancela-tu-cita y /reprograma-tu-cita.
    Categorías y fichas están permitidas. No declara Crawl-delay para agentes
    genéricos, pero aquí se usa 1 segundo por educación.

Uso:
    python src/scraping/optica2000.py enumerar     # sitemap -> cola
    python src/scraping/optica2000.py rastrear     # cola -> base de datos
    python src/scraping/optica2000.py rastrear --limite 50    # prueba corta

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

# Identificarse honestamente. Un scraper que se hace pasar por Chrome es lo
# primero que un revisor técnico te va a criticar.
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
    """Saca las URLs de ficha del sitemap.

    Se enumera desde el sitemap y no desde las páginas de categoría porque es
    la vía que el propio sitio publica para ser rastreado, y porque las
    categorías paginan de 24 en 24 (más peticiones para el mismo resultado).
    """
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
    """Formato de pantalla español: '169,90 €' -> 169.9 · '123 mm' -> 123.0

    Punto = millares, coma = decimal. Para texto visible de la página.
    """
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
    """Formato máquina: '125.250000' -> 125.25

    El punto es el separador DECIMAL. Es lo que usa el JSON-LD de schema.org.
    Pasarlo por _num() lo convertiría en 125.250 €. Es un fallo silencioso:
    no revienta, solo multiplica los precios por mil.
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
    """Extrae los campos de una ficha.

    Estrategia en dos pasos:
      1. JSON-LD si existe (estable, con esquema).
      2. Etiquetas de texto en español si no (frágil ante rediseños, pero es
         lo que publica esta ficha).

    El HTML crudo queda guardado en la base de datos, así que si este parser
    falla se corrige y se reparsea sin volver a rastrear.
    """
    sopa = BeautifulSoup(html, "html.parser")
    # Todas las claves se declaran de entrada, aunque queden a None. Si un campo
    # solo aparece cuando existe, el CSV acaba con columnas distintas según la
    # ficha y el DataFrame se llena de NaN sin que se sepa por qué.
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
            # OJO: NO usar d.setdefault(). Todas las claves están declaradas de
            # entrada con valor None, y setdefault solo escribe si la clave NO
            # EXISTE — no si vale None. Con setdefault este bloque entero no
            # hacía nada. Mismo error que el `campo not in d` de más abajo.
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
    # Fuera scripts y estilos, pero SOLO AHORA: el bloque JSON-LD de arriba vive
    # dentro de un <script>, así que eliminarlos antes lo dejaría inservible.
    # Óptica 2000 sirve en su bundle de JavaScript todas las cadenas de interfaz
    # posibles ("Añadir al carrito", "Este producto no está disponible"...), de
    # modo que buscarlas sin limpiar da positivo en el 100 % de las fichas.
    for etiqueta in sopa(["script", "style", "noscript"]):
        etiqueta.decompose()

    texto = sopa.get_text("\n", strip=True)
    lineas = [l for l in texto.split("\n") if l]

    if not d.get("nombre"):
        h1 = sopa.find("h1")
        d["nombre"] = h1.get_text(strip=True) if h1 else None

    # Etiqueta y valor van en líneas consecutivas.
    # OJO: la condición es `d.get(campo) is None`, no `campo not in d`. Todas las
    # claves existen desde el principio (puestas a None), así que comprobar la
    # pertenencia no serviría de nada y no se extraería ningún atributo.
    for i, linea in enumerate(lineas[:-1]):
        campo = ETIQUETAS.get(linea.strip())
        if campo and d.get(campo) is None:
            valor = lineas[i + 1].strip()
            d[campo] = _num(valor) if campo.startswith(("ancho", "largo")) else valor

    # --- Precios ---
    # En la ficha real los trozos van en nodos de texto SEPARADOS:
    #     "ahora:" / "38 €" / "antes:" / "76 €" / "-50%" / "OUTLET"
    # Por eso se aplana el texto antes de buscar: así "ahora:" y su importe
    # quedan contiguos aunque en el DOM estén en elementos distintos.
    plano = re.sub(r"\s+", " ", texto)

    # Fuera la línea de financiación ANTES de buscar precios. Si se deja,
    # "o 3 x 56,33 € sin intereses" puede colarse como precio del producto.
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

    # PVP = el target decidido para el modelo (ver decisiones_mlgafas.md, D5bis).
    # Si hay oferta, el PVP es el precio tachado; si no, el precio a secas es ya
    # el de catálogo. Se calcula aquí para que el CSV traiga el target listo y
    # nadie tenga que reconstruirlo a mano en el notebook.
    d["pvp"] = d["precio_anterior"] if d["en_oferta"] else d["precio_actual"]

    # OUTLET: hay que acotarlo al bloque de precio.
    # "OUTLET" es también una entrada del menú de navegación, así que buscarlo en
    # toda la página lo daba TRUE en las 12 fichas de una muestra real — un campo
    # constante, inútil y engañoso. Solo cuenta si hay descuento y la etiqueta
    # aparece pegada al precio.
    d["outlet"] = False
    if ahora_m:
        ventana = plano_precios[ahora_m.start(): ahora_m.start() + 120]
        d["outlet"] = "OUTLET" in ventana

    # Sello de que el precio es de la montura sola, no de un pack
    d["precio_solo_montura"] = bool(
        re.search(r"solo\s+(a\s+la|la)?\s*montura", plano, re.I)
    )

    # Producto descatalogado o sin stock: la ficha responde 200 y tiene marca y
    # modelo, pero no trae ni precio ni atributos. El sitemap las sigue listando.
    # Detectado en la primera tanda de 80 fichas (1 de 80).
    d["disponible"] = "Este producto no está disponible" not in plano

    # Canal de venta. Son estados mutuamente excluyentes, verificado en la web:
    #   comprable online -> "Entrega estimada ..." + "Añadir al carrito"
    #   solo en tienda   -> "Encontrar una tienda", sin carrito ni entrega
    # No es lo mismo que estar agotado: el producto existe, pero no se vende por
    # web. Afecta al 25 % del catálogo y no se reparte por igual entre marcas.
    d["venta_online"] = bool(re.search(r"A[ñn]adir al carrito", plano, re.I))

    # --- Marca y modelo, desde las migas de pan ---
    # NO usar el enlace a /gafas-graduadas/{marca}: solo existe para las 9 marcas
    # del menú de navegación. Arnette, DbyD, Miraflex y el resto del catálogo no
    # tienen página de categoría, así que ese método deja `marca` a None en buena
    # parte de las fichas — y marca es la variable más importante del modelo.
    #
    # La estructura correcta es siempre la misma (verificada en 8 marcas reales
    # el 2 ago 2026, incluidas las que no tienen categoría propia):
    #
    #     <ul class="breadcrumbs">
    #       <li>GAFAS GRADUADAS</li>
    #       <li>Armani Exchange</li>                       <- marca
    #       <li class="...current-page-text">AX3077 8001</li>  <- modelo
    #     </ul>
    #
    # OJO: hay que coger los <li> HIJOS DIRECTOS de ese <ul>. Los <li>
    # envoltorios y los <a> internos también llevan "breadcrumb" en su clase; si
    # se recorren todos los elementos que casan, el último con texto acaba siendo
    # el de la marca y `modelo` sale mal (fallo real detectado en la primera
    # tanda de 20 fichas).
    #
    # Ventaja añadida: la marca sale con su grafía correcta — "Dolce&Gabbana",
    # "DbyD" — que el respaldo por slug convertiría en "Dolcegabbana".
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
    """Comprueba el parser contra fichas sintéticas que reproducen lo observado
    en la web el 1 ago 2026. No toca la red.

        python src/scraping/optica2000.py autotest
    """
    # IMPORTANTE: los bloques de precio van en nodos de texto SEPARADOS, tal y
    # como se observó en la ficha real (nodos 178-183 de
    # /gafas-graduadas/rayban-0ry9078v-3950-48-16/8056597941723 el 1 ago 2026).
    # Un fixture con "ahora: 38 € antes: 76 €" en una sola línea pasaría el test
    # sin comprobar el caso que de verdad ocurre.
    base = (
        "<html><body>"
        # El menú de navegación lleva OUTLET en TODAS las páginas. Va en el
        # fixture a propósito: sin él, el test no detecta el falso positivo.
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
    # 169 y no 56,33: la línea de financiación se elimina antes de buscar
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
    # El "-10% de descuento" de la newsletter no debe contaminar nada
    assert con["descuento_pct"] == 50.0

    assert set(sin) == set(con), "las dos fichas deben dar las mismas columnas"

    # --- Marca y modelo, con los cuatro casos reales observados ---
    # Incluye marcas SIN página de categoría (Arnette, DbyD, Miraflex), que es
    # justo donde fallaba el método anterior basado en el enlace de marca.
    # Reproduce el maquetado REAL de las migas de pan, con los <li> envoltorios
    # y los <a> internos que también llevan "breadcrumb" en la clase. Sin ellos,
    # el test no detecta el fallo de quedarse con la marca en vez del modelo.
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
        # Orden barajado pero REPRODUCIBLE (semilla fija). El sitemap va
        # alfabético, así que sin esto una tanda corta son todas de la misma
        # marca: las 80 primeras fichas fueron las 80 de Armani Exchange.
        # Barajando, cualquier interrupción deja una muestra representativa
        # de todo el catálogo en vez de la mitad del abecedario.
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
                    # Descatalogado o sin stock. La ficha responde 200 y tiene
                    # marca y modelo, pero ni precio ni atributos. No es un fallo
                    # del scraper: se aparta para que no ensucie el dataset.
                    cola.guardar_error(con, url, "sin precio (no disponible)")
                    no_disp += 1
                else:
                    # Escribir primero, marcar como hecho después: guardar_ok lo
                    # hace en una sola transacción.
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
