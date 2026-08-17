"""Cruce entre la marca que escribe la tienda y marcas_grupo.csv.

El scraper devuelve "Vogue Eyewear" o "Dolce&Gabbana"; la tabla guarda slugs
("vogue", "dolce-gabbana"). Sin normalizar, el cruce falla y `grupo` se queda
vacío en buena parte de las filas.

    from marcas import asignar_grupo
    df["grupo"] = asignar_grupo(df["marca"])
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
TABLA = RAIZ / "marcas_grupo.csv"

# Coletillas comerciales que no distinguen marca: "Vogue Eyewear" == "Vogue".
RUIDO = re.compile(r"\b(eyewear|optics?|kids|bio-?based|by|collection|coleccion)\b")

# Grafías que la normalización mecánica no resuelve. "D&G" -> "d-g" no se parece
# a "dolce-gabbana", y son 220 fichas de General Óptica.
ALIAS = {
    "d-g": "dolce-gabbana",
    "tiffany-co": "tiffany",
    "nuance-audio": "nuance",
    "nanovista": "nano-vista",
    "ch": "carolina-herrera",
}


def normalizar(s) -> str | None:
    """'Vogue Eyewear' -> 'vogue'; 'Dolce&Gabbana' -> 'dolce-gabbana'."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " ").replace("_", " ")
    s = RUIDO.sub(" ", s)
    k = re.sub(r"[^a-z0-9]+", "-", s).strip("-") or None
    return ALIAS.get(k, k)


def _buscar(clave: str | None, mapa: dict[str, str]) -> str | None:
    """Prueba prefijos de token cada vez más cortos, para no enumerar submarcas:
    'carolina-herrera-new-york' -> 'carolina-herrera', 'nike-jr' -> 'nike',
    'lozza-x-luis-figo' -> 'lozza'.

    Corta por guiones y no por caracteres para que 'ray-ban' no case con
    cualquier cosa que empiece por 'ray'.
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
    """{clave_normalizada: grupo}. Con solo_verificadas descarta las filas cuyo
    estado no sea 'verificado'."""
    g = pd.read_csv(TABLA)
    if solo_verificadas:
        g = g[g["estado"] == "verificado"]
    g = g[g["grupo"].notna() & (g["grupo"] != "PENDIENTE")]
    return dict(zip(g["marca"].map(normalizar), g["grupo"]))


def asignar_grupo(marcas: pd.Series, solo_verificadas: bool = False) -> pd.Series:
    """Marcas comerciales -> grupos propietarios.

    Lo que no cruza queda a NaN a propósito: un hueco visible es preferible a una
    categoría 'otros' que esconda un fallo de normalización.
    """
    mapa = cargar_mapa(solo_verificadas)
    return marcas.map(normalizar).map(lambda k: _buscar(k, mapa))


def sin_cruzar(marcas: pd.Series) -> pd.DataFrame:
    """Marcas del dataset que no están en la tabla, con su recuento. Conviene
    ejecutarlo tras cada scrapeo."""
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
    print(f"{csv}: {len(df)} filas · {df['marca'].nunique()} marcas")
    print(f"con grupo asignado: {df['grupo'].notna().sum()} ({100*df['grupo'].notna().mean():.1f} %)")
    print()
    print(df["grupo"].value_counts(dropna=False).to_string())
    falta = sin_cruzar(df["marca"])
    if len(falta):
        print("\nSIN CRUZAR - verificar y anadir a marcas_grupo.csv:")
        print(falta.to_string(index=False))
