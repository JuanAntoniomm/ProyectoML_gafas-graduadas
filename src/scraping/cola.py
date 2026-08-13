"""
cola.py
=======

Cola de trabajo en SQLite para los scrapers.

NO es donde vive el dataset. El dataset final sale a CSV en `data/raw/`.
Esto es el cuaderno de bitácora: qué URLs quedan por visitar, cuáles ya están
hechas y cuáles fallaron. Sirve para poder parar el scrapeo y reanudarlo sin
empezar de cero.

Por qué SQLite y no un .txt o un CSV:
    Si el ordenador se apaga mientras escribes una línea en un fichero de texto,
    el fichero queda a medias y no sabes por dónde ibas. SQLite hace escrituras
    atómicas: o la fila entra entera o no entra. Viene en la librería estándar
    de Python, no hay que instalar nada.

Decisión de diseño importante — se guarda el HTML crudo:
    La columna `payload` guarda la respuesta tal cual llegó. Si mañana descubres
    un fallo en el parser, reparseas desde la base de datos en segundos en vez de
    volver a rastrear la web durante 15 horas. Cuesta espacio en disco y ahorra
    tiempo real.

Regla de oro del reanudado:
    Se escribe el dato PRIMERO y se marca como hecho DESPUÉS. Si el proceso muere
    en medio, la peor consecuencia es repetir una ficha (inofensivo) en lugar de
    saltársela (silencioso y difícil de detectar).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_DIR = ROOT / "data" / "raw"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS productos (
    url         TEXT PRIMARY KEY,
    tienda      TEXT NOT NULL,
    estado      TEXT NOT NULL DEFAULT 'pendiente',   -- pendiente | hecho | error
    ean         TEXT,
    payload     TEXT,        -- HTML o JSON crudo, para poder reparsear sin rastrear
    ts          TEXT,        -- momento de captura, ISO 8601 UTC
    intentos    INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_estado ON productos(estado);
CREATE INDEX IF NOT EXISTS idx_tienda ON productos(tienda);
"""


def ahora() -> str:
    """Timestamp ISO 8601 en UTC. Va en cada fila para poder detectar si a mitad
    del scrapeo cambió una campaña promocional."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def abrir(nombre_db: str) -> sqlite3.Connection:
    """Abre (o crea) la base de datos de la cola."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_DIR / nombre_db)
    con.execute("PRAGMA journal_mode=WAL")      # aguanta mejor los cortes bruscos
    con.executescript(ESQUEMA)
    con.commit()
    return con


def encolar(con: sqlite3.Connection, urls: list[str], tienda: str) -> int:
    """Mete URLs en la cola. Las que ya estén se ignoran (INSERT OR IGNORE),
    así que se puede reenumerar sin perder el progreso."""
    cur = con.executemany(
        "INSERT OR IGNORE INTO productos (url, tienda) VALUES (?, ?)",
        [(u, tienda) for u in urls],
    )
    con.commit()
    return cur.rowcount


def pendientes(con: sqlite3.Connection, tienda: str, max_intentos: int = 3) -> list[str]:
    """URLs que quedan por rastrear. Descarta las que ya fallaron demasiadas veces."""
    filas = con.execute(
        "SELECT url FROM productos WHERE tienda = ? AND estado != 'hecho' "
        "AND intentos < ? ORDER BY url",
        (tienda, max_intentos),
    ).fetchall()
    return [f[0] for f in filas]


def guardar_ok(con: sqlite3.Connection, url: str, payload: str, ean: str | None) -> None:
    """Guarda el contenido y marca la ficha como hecha.

    El orden importa: se escribe payload y ts en el mismo UPDATE que el estado,
    dentro de una única transacción. Si el proceso muere antes del commit, la
    fila sigue en 'pendiente' y se reintentará.
    """
    con.execute(
        "UPDATE productos SET estado='hecho', payload=?, ean=?, ts=?, "
        "intentos=intentos+1, error=NULL WHERE url=?",
        (payload, ean, ahora(), url),
    )
    con.commit()


def guardar_error(con: sqlite3.Connection, url: str, mensaje: str) -> None:
    """Suma un intento y anota el error. NO marca como hecho."""
    con.execute(
        "UPDATE productos SET estado='error', intentos=intentos+1, error=?, ts=? "
        "WHERE url=?",
        (mensaje[:500], ahora(), url),
    )
    con.commit()


def resumen(con: sqlite3.Connection) -> dict:
    """Cuántas van por tienda y estado. Para saber si merece la pena seguir."""
    filas = con.execute(
        "SELECT tienda, estado, COUNT(*) FROM productos GROUP BY tienda, estado"
    ).fetchall()
    out: dict = {}
    for tienda, estado, n in filas:
        out.setdefault(tienda, {})[estado] = n
    return out


if __name__ == "__main__":
    con = abrir("scrape.db")
    r = resumen(con)
    if not r:
        print("Cola vacía. Ejecuta primero un script de enumeración.")
    for tienda, estados in r.items():
        total = sum(estados.values())
        hechos = estados.get("hecho", 0)
        print(f"{tienda:16} {hechos:>5}/{total:<5} hechas  "
              f"({100 * hechos / total:.1f}%)  detalle: {estados}")
    con.close()
