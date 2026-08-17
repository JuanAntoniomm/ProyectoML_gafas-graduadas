"""Convierte la cola SQLite en los CSV de data/raw/.

Reparsea desde el payload guardado, sin tocar la web: un fallo del parser se
corrige y se reejecuta esto, y el dataset se regenera en segundos.

    python src/scraping/exportar.py
    python src/scraping/exportar.py --tienda optica2000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cola  # noqa: E402
import generaloptica as go  # noqa: E402
import optica2000 as o2  # noqa: E402

SALIDA = Path(__file__).resolve().parents[2] / "data" / "raw"

PARSERS = {
    "optica2000": lambda payload, url: o2.parsear(payload, url),
    "generaloptica": lambda payload, url: go.parsear(payload),
}


def exportar(tienda: str | None = None, db: str = "scrape.db",
             sufijo: str = "") -> None:
    con = cola.abrir(db)
    tiendas = [tienda] if tienda else list(PARSERS)

    for t in tiendas:
        filas = con.execute(
            "SELECT url, payload, ts FROM productos "
            "WHERE tienda=? AND estado='hecho' AND payload IS NOT NULL",
            (t,),
        ).fetchall()
        if not filas:
            print(f"{t}: nada que exportar todavía.")
            continue

        registros, errores = [], 0
        for url, payload, ts in filas:
            try:
                d = PARSERS[t](payload, url)
                d["ts_captura"] = ts       # fecha de captura por fila
                registros.append(d)
            except Exception as e:         # noqa: BLE001
                errores += 1
                if errores <= 3:
                    print(f"  fallo al parsear {url}: {type(e).__name__}: {e}")

        df = pd.DataFrame(registros)
        SALIDA.mkdir(parents=True, exist_ok=True)
        destino = SALIDA / f"{t}_graduadas{sufijo}.csv"
        df.to_csv(destino, index=False, encoding="utf-8")

        print(f"\n{t}: {len(df)} filas -> {destino.name}  ({errores} fallos de parseo)")
        if not df.empty:
            print(f"  columnas: {list(df.columns)}")
            if "precio_actual" in df:
                p = pd.to_numeric(df["precio_actual"], errors="coerce")
                print(f"  precio_actual: nulos={p.isna().sum()} "
                      f"min={p.min():.2f} mediana={p.median():.2f} max={p.max():.2f}")
            if "en_oferta" in df:
                n = int(df["en_oferta"].sum())
                print(f"  en oferta: {n} ({100 * n / len(df):.1f}%)")
            if "ean" in df:
                print(f"  EAN nulos={df['ean'].isna().sum()} "
                      f"duplicados={df['ean'].duplicated().sum()}")
            if "ts_captura" in df:
                print(f"  captura: {df['ts_captura'].min()} .. {df['ts_captura'].max()}")

    con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Exporta la cola SQLite a CSV")
    p.add_argument("--tienda", choices=list(PARSERS), default=None)
    p.add_argument("--db", default="scrape.db", help="Base de datos de la cola")
    p.add_argument("--sufijo", default="", help="Sufijo del CSV de salida (p. ej. _prueba)")
    a = p.parse_args()
    exportar(a.tienda, a.db, a.sufijo)
