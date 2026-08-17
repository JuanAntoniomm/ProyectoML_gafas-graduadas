"""Cola de trabajo en SQLite para los scrapers.

No es el dataset (ese sale a CSV en data/raw/), sino el registro de qué URLs
quedan, cuáles están hechas y cuáles fallaron, para poder parar el scrapeo de 15
horas y reanudarlo sin empezar de cero.

SQLite y no un fichero de texto porque las escrituras son atómicas: un corte a
media línea deja el .txt inservible y la fila de SQLite entera o sin escribir.

`payload` guarda el HTML tal cual llegó, así que un fallo del parser se corrige
reexportando en segundos en vez de volviendo a rastrear.
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
    """Guarda el contenido y marca la ficha como hecha, en un solo UPDATE. Si el
    proceso muere antes del commit la fila sigue pendiente y se reintenta:
    repetir una ficha es inofensivo, saltársela es un hueco silencioso."""
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
