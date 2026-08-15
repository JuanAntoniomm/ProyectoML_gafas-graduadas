"""
marcas.py
=========

Une lo que escupe el scraper con la tabla de grupos propietarios.

El problema que resuelve:
    El scraper devuelve la marca tal y como la escribe la tienda —"Vogue Eyewear",
    "Dolce&Gabbana", "Polo Ralph Lauren"— y `marcas_grupo.csv` la guarda en forma
    de slug —"vogue", "dolce-gabbana", "polo-ralph-lauren"—. Sin normalizar, el
    cruce falla y `grupo_licenciante`, que es la variable central del proyecto,
    se queda vacía en buena parte de las filas.

Verificado el 2 ago 2026 sobre 119 fichas reales de Óptica 2000: cruzan 19 de
las 20 marcas presentes.

Uso:
    from marcas import normalizar, cargar_mapa, asignar_grupo
    df["grupo"] = asignar_grupo(df["marca"])
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
TABLA = RAIZ / "marcas_grupo.csv"

# Palabras que las tiendas añaden al nombre comercial y que no distinguen marca.
# "Vogue Eyewear" y "Vogue" son la misma marca; "Ray-Ban Optics Kids Bio-Based"
# sigue siendo Ray-Ban.
RUIDO = re.compile(r"\b(eyewear|optics?|kids|bio-?based|by|collection|coleccion)\b")

# Abreviaturas y grafías alternativas que la normalización mecánica no resuelve.
# El caso grave fue "D&G": al sustituir "&" por espacio queda "d-g", que no se
# parece a "dolce-gabbana" — y son 220 fichas de General Óptica, la cuarta marca
# más frecuente del catálogo.
ALIAS = {
    "d-g": "dolce-gabbana",
    "tiffany-co": "tiffany",
    "nuance-audio": "nuance",
    "nanovista": "nano-vista",
    "ch": "carolina-herrera",
}


def normalizar(s) -> str | None:
    """Nombre comercial -> clave canónica.

        'Vogue Eyewear'     -> 'vogue'
        'Dolce&Gabbana'     -> 'dolce-gabbana'
        'Polo Ralph Lauren' -> 'polo-ralph-lauren'
        'Óptica X'          -> 'optica-x'
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " ").replace("_", " ")
    s = RUIDO.sub(" ", s)
    k = re.sub(r"[^a-z0-9]+", "-", s).strip("-") or None
    return ALIAS.get(k, k)


def _buscar(clave: str | None, mapa: dict[str, str]) -> str | None:
    """Busca la clave y, si no está, prueba con prefijos de token cada vez más
    cortos. Resuelve las submarcas y ediciones especiales sin tener que
    enumerarlas una a una:

        'carolina-herrera-new-york' -> 'carolina-herrera'
        'lozza-x-luis-figo'         -> 'lozza'
        'yalea-x-frida-kahlo'       -> 'yalea'
        'nike-jr'                   -> 'nike'
        'boss-orange'               -> 'boss'
        'silhouette-aire'           -> 'silhouette'

    Se corta por guiones, no por caracteres, para que 'ray-ban' no case con
    cualquier cosa que empiece por 'ray'. Si ningún prefijo está en la tabla
    devuelve None: es preferible un hueco visible a una asignación inventada.
    """
    if not clave:
        return None
    partes = clave.split("-")
    for n in range(len(partes), 0, -1):
        g = mapa.get("-".join(partes[:n]))
        if g:
            return g
    return None


def cargar_mapa(solo_verificadas: bool = False) -> dict[str, str]:
    """Devuelve {clave_normalizada: grupo} desde marcas_grupo.csv.

    Con `solo_verificadas=True` descarta las filas cuyo estado no sea
    'verificado', por si quieres construir la variable únicamente con
    asignaciones respaldadas por fuente primaria.
    """
    g = pd.read_csv(TABLA)
    if solo_verificadas:
        g = g[g["estado"] == "verificado"]
    g = g[g["grupo"].notna() & (g["grupo"] != "PENDIENTE")]
    return dict(zip(g["marca"].map(normalizar), g["grupo"]))


def asignar_grupo(marcas: pd.Series, solo_verificadas: bool = False) -> pd.Series:
    """Serie de marcas comerciales -> serie de grupos propietarios.

    Las marcas que no cruzan quedan a NaN a propósito: es preferible un hueco
    visible que una categoría 'otros' que esconda un fallo de normalización.
    """
    mapa = cargar_mapa(solo_verificadas)
    return marcas.map(normalizar).map(lambda k: _buscar(k, mapa))


def sin_cruzar(marcas: pd.Series) -> pd.DataFrame:
    """Marcas del dataset que NO están en la tabla, con su recuento.

    Ejecutarlo después de cada scrapeo: si aparece algo, hay que verificar a qué
    grupo pertenece y añadirlo a marcas_grupo.csv con su fuente.
    """
    mapa = cargar_mapa()
    d = pd.DataFrame({"marca": marcas})
    d["clave"] = d["marca"].map(normalizar)
    d = d[d["clave"].notna() & d["clave"].map(lambda k: _buscar(k, mapa) is None)]
    return (d.groupby(["marca", "clave"]).size()
            .rename("n").reset_index().sort_values("n", ascending=False))


if __name__ == "__main__":
    import sys
    csv = sys.argv[1] if len(sys.argv) > 1 else "data/raw/optica2000_graduadas.csv"
    df = pd.read_csv(RAIZ / csv)
    df["grupo"] = asignar_grupo(df["marca"])
    n = len(df)
    print(f"{csv}: {n} filas · {df['marca'].nunique()} marcas")
    print(f"con grupo asignado: {df['grupo'].notna().sum()} ({100*df['grupo'].notna().mean():.1f} %)")
    print()
    print(df["grupo"].value_counts(dropna=False).to_string())
    falta = sin_cruzar(df["marca"])
    if len(falta):
        print("\nSIN CRUZAR — verificar y añadir a marcas_grupo.csv:")
        print(falta.to_string(index=False))
