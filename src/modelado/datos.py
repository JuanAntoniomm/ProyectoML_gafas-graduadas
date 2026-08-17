"""Carga y fusión del dataset.

Lo importan el entrenamiento, los notebooks y la app, para que los tres partan de
los mismos datos, las mismas features y el mismo split.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "scraping"))
from marcas import asignar_grupo  # noqa: E402

SEMILLA = 42
TARGET = "pvp"

# Intersección de lo que publican las dos tiendas. Perder forma, tipo de montura,
# longitud de varilla y talla costó 0,09 € de MAE (notebook 02).
NUM = ["ancho_lente", "ancho_puente"]
CAT = ["marca", "grupo", "tienda", "material_montura", "color", "genero"]
FEATURES = NUM + CAT


def cargar() -> pd.DataFrame:
    """Fusiona los catálogos de las dos tiendas y añade el grupo propietario."""
    o2 = pd.read_csv(RAIZ / "data/raw/optica2000_graduadas.csv", dtype={"ean": str})
    go = pd.read_csv(RAIZ / "data/raw/generaloptica_graduadas.csv", dtype={"ean": str})
    go["ean"] = go["ean"].str.split(".").str[0]

    # Cada tienda codifica la disponibilidad con distinto nombre y formato.
    o2["en_stock"] = o2["disponible"].astype(bool)
    go["en_stock"] = (go["disponibilidad"].str.split("/").str[-1]
                      .isin(["InStock", "InStoreOnly", "OnlineOnly"]))

    comunes = sorted((set(o2.columns) & set(go.columns)) | {"en_stock"})
    d = pd.concat([o2[comunes], go[comunes]], ignore_index=True)
    d["grupo"] = asignar_grupo(d["marca"]).fillna("desconocido")
    return d[d[TARGET].notna()].reset_index(drop=True)


def separar(d: pd.DataFrame, test_size: float = 0.2):
    sin_ean = pd.Series("sin-ean-" + d.index.astype(str), index=d.index)
    grupos = d["ean"].where(d["ean"].notna(), sin_ean)
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=SEMILLA)
    i_tr, i_te = next(gss.split(d, groups=grupos))
    tr, te = d.iloc[i_tr].copy(), d.iloc[i_te].copy()

    fuga = set(grupos.iloc[i_tr]) & set(grupos.iloc[i_te])
    assert not fuga, f"FUGA: {len(fuga)} productos en train y test a la vez"
    return tr, te


def opciones() -> dict:
    """Valores posibles de cada categórica, para los desplegables de la app."""
    d = cargar()
    return {
        "marca": sorted(d["marca"].dropna().unique()),
        "tienda": sorted(d["tienda"].unique()),
        "material_montura": sorted(d["material_montura"].dropna().unique()),
        "color": sorted(d["color"].dropna().unique()),
        "genero": sorted(d["genero"].dropna().unique()),
        "marca_a_grupo": (d.dropna(subset=["marca"])
                          .groupby("marca")["grupo"].first().to_dict()),
        "rango_lente": (float(d["ancho_lente"].min()), float(d["ancho_lente"].max())),
        "rango_puente": (float(d["ancho_puente"].min()), float(d["ancho_puente"].max())),
    }
