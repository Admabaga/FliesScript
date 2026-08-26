import os
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH, SETTING_DEFAULTS

SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    origin      TEXT NOT NULL,
    destination TEXT NOT NULL,
    date        TEXT NOT NULL,
    return_date TEXT,
    adults      INTEGER NOT NULL DEFAULT 1,
    bag_level   TEXT NOT NULL DEFAULT 'any',
    max_price   INTEGER NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS flights (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id     INTEGER NOT NULL,
    airline      TEXT NOT NULL,
    direction    TEXT NOT NULL DEFAULT 'out',
    depart_time  TEXT,
    arrive_time  TEXT,
    duration     TEXT,
    flight_no    TEXT,
    price        INTEGER NOT NULL,
    url          TEXT,
    scraped_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (watch_id) REFERENCES watches(id) ON DELETE CASCADE
);

-- Un vuelo se vende a varios precios segun el equipaje: una fila por tarifa.
CREATE TABLE IF NOT EXISTS fares (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id INTEGER NOT NULL,
    name      TEXT,
    level     TEXT NOT NULL,
    price     INTEGER NOT NULL,
    source    TEXT NOT NULL DEFAULT 'estimado',
    FOREIGN KEY (flight_id) REFERENCES flights(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scan_status (
    watch_id   INTEGER NOT NULL,
    airline    TEXT NOT NULL,
    status     TEXT NOT NULL,
    message    TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (watch_id, airline)
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_key TEXT PRIMARY KEY,
    price     INTEGER NOT NULL,
    sent_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


# Columnas añadidas después de la primera versión. Las bases que ya existen no se
# recrean con el SCHEMA, así que hay que agregarlas a mano.
MIGRATIONS = {
    "watches": {
        "return_date": "TEXT",
        "adults": "INTEGER NOT NULL DEFAULT 1",
        "bag_level": "TEXT NOT NULL DEFAULT 'any'",
    },
    "flights": {"direction": "TEXT NOT NULL DEFAULT 'out'"},
}


def migrate(c):
    for table, columns in MIGRATIONS.items():
        have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, decl in columns.items():
            if name not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        migrate(c)
        for key, value in SETTING_DEFAULTS.items():
            c.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO NOTHING",
                (key, value),
            )


def get_settings() -> dict:
    with conn() as c:
        rows = c.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def save_settings(values: dict):
    with conn() as c:
        for key, value in values.items():
            if key not in SETTING_DEFAULTS:
                continue
            c.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )


def list_watches(only_active: bool = False) -> list[dict]:
    sql = "SELECT * FROM watches"
    if only_active:
        sql += " WHERE active = 1"
    sql += " ORDER BY date, id"
    with conn() as c:
        return [dict(r) for r in c.execute(sql).fetchall()]


def add_watch(
    origin,
    destination,
    date,
    max_price,
    return_date=None,
    adults=1,
    bag_level="any",
) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO watches(origin, destination, date, return_date, adults,"
            " bag_level, max_price) VALUES(?,?,?,?,?,?,?)",
            (
                origin.upper(),
                destination.upper(),
                date,
                return_date or None,
                int(adults or 1),
                bag_level or "any",
                int(max_price),
            ),
        )
        return cur.lastrowid


def update_watch(watch_id: int, **fields):
    allowed = {
        "origin",
        "destination",
        "date",
        "return_date",
        "adults",
        "bag_level",
        "max_price",
        "active",
    }
    fields = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "return_date" in fields and not fields["return_date"]:
        fields["return_date"] = None  # "" = volvió a ser solo ida
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE watches SET {sets} WHERE id = ?", (*fields.values(), watch_id))


def delete_watch(watch_id: int):
    with conn() as c:
        c.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
        c.execute("DELETE FROM flights WHERE watch_id = ?", (watch_id,))
        c.execute("DELETE FROM scan_status WHERE watch_id = ?", (watch_id,))


def replace_flights(watch_id: int, airline: str, flights: list[dict]):
    """Reemplaza los vuelos de una aerolínea (ida y vuelta) con sus tarifas."""
    with conn() as c:
        c.execute("DELETE FROM flights WHERE watch_id = ? AND airline = ?", (watch_id, airline))
        for f in flights:
            cur = c.execute(
                "INSERT INTO flights(watch_id, airline, direction, depart_time, arrive_time,"
                " duration, flight_no, price, url) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    watch_id,
                    airline,
                    f.get("direction") or "out",
                    f.get("depart_time"),
                    f.get("arrive_time"),
                    f.get("duration"),
                    f.get("flight_no"),
                    int(f["price"]),
                    f.get("url"),
                ),
            )
            c.executemany(
                "INSERT INTO fares(flight_id, name, level, price, source) VALUES(?,?,?,?,?)",
                [
                    (cur.lastrowid, t.get("name"), t["level"], int(t["price"]),
                     t.get("source") or "estimado")
                    for t in (f.get("fares") or [])
                ],
            )


def set_status(watch_id: int, airline: str, status: str, message: str = ""):
    with conn() as c:
        c.execute(
            "INSERT INTO scan_status(watch_id, airline, status, message, updated_at)"
            " VALUES(?,?,?,?, datetime('now'))"
            " ON CONFLICT(watch_id, airline) DO UPDATE SET"
            " status = excluded.status, message = excluded.message,"
            " updated_at = excluded.updated_at",
            (watch_id, airline, status, message[:300]),
        )


def get_flights(watch_id: int) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM flights WHERE watch_id = ? ORDER BY price, depart_time",
            (watch_id,),
        ).fetchall()
        flights = [dict(r) for r in rows]
        if not flights:
            return []
        fares = c.execute(
            "SELECT f.* FROM fares f JOIN flights v ON v.id = f.flight_id"
            " WHERE v.watch_id = ? ORDER BY f.price",
            (watch_id,),
        ).fetchall()
    by_flight = {}
    for f in fares:
        by_flight.setdefault(f["flight_id"], []).append(
            {"name": f["name"], "level": f["level"], "price": f["price"], "source": f["source"]}
        )
    for flight in flights:
        flight["fares"] = by_flight.get(flight["id"], [])
    return flights


def last_scrape_at() -> str | None:
    """Cuándo llegaron los últimos precios (UTC, como lo guarda SQLite).

    Es el reloj que mira el vigilante: sobrevive a los reinicios de Render, a
    diferencia de `engine.STATE`, que vive en memoria.
    """
    with conn() as c:
        fila = c.execute("SELECT MAX(scraped_at) AS t FROM flights").fetchone()
    return fila["t"] if fila and fila["t"] else None


def get_statuses(watch_id: int) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM scan_status WHERE watch_id = ?", (watch_id,)).fetchall()
    return [dict(r) for r in rows]


def alerted_prices(watch_id: int) -> dict[str, int]:
    """Ultimo precio avisado por vuelo. Sirve para no repetir lo ya conocido."""
    with conn() as c:
        rows = c.execute(
            "SELECT alert_key, price FROM alerts WHERE alert_key LIKE ?", (f"{watch_id}|%",)
        ).fetchall()
    return {r["alert_key"]: r["price"] for r in rows}


def mark_alert(alert_key: str, price: int):
    with conn() as c:
        c.execute(
            "INSERT INTO alerts(alert_key, price, sent_at) VALUES(?,?, datetime('now'))"
            " ON CONFLICT(alert_key) DO UPDATE SET price = excluded.price,"
            " sent_at = excluded.sent_at",
            (alert_key, int(price)),
        )
