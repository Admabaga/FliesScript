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
    max_price   INTEGER NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS flights (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id     INTEGER NOT NULL,
    airline      TEXT NOT NULL,
    depart_time  TEXT,
    arrive_time  TEXT,
    duration     TEXT,
    flight_no    TEXT,
    price        INTEGER NOT NULL,
    url          TEXT,
    scraped_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (watch_id) REFERENCES watches(id) ON DELETE CASCADE
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


def init():
    with conn() as c:
        c.executescript(SCHEMA)
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


def add_watch(origin, destination, date, max_price) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO watches(origin, destination, date, max_price) VALUES(?,?,?,?)",
            (origin.upper(), destination.upper(), date, int(max_price)),
        )
        return cur.lastrowid


def update_watch(watch_id: int, **fields):
    allowed = {"origin", "destination", "date", "max_price", "active"}
    fields = {k: v for k, v in fields.items() if k in allowed and v is not None}
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
    with conn() as c:
        c.execute("DELETE FROM flights WHERE watch_id = ? AND airline = ?", (watch_id, airline))
        c.executemany(
            "INSERT INTO flights(watch_id, airline, depart_time, arrive_time, duration,"
            " flight_no, price, url) VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    watch_id,
                    airline,
                    f.get("depart_time"),
                    f.get("arrive_time"),
                    f.get("duration"),
                    f.get("flight_no"),
                    int(f["price"]),
                    f.get("url"),
                )
                for f in flights
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
    return [dict(r) for r in rows]


def get_statuses(watch_id: int) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM scan_status WHERE watch_id = ?", (watch_id,)).fetchall()
    return [dict(r) for r in rows]


def should_alert(alert_key: str, price: int, cooldown_hours: int) -> bool:
    """Alerta si nunca se envio, si vencio el cooldown, o si el precio bajo aun mas."""
    with conn() as c:
        row = c.execute("SELECT * FROM alerts WHERE alert_key = ?", (alert_key,)).fetchone()
        if row is None:
            return True
        expired = c.execute(
            "SELECT datetime(sent_at, ?) < datetime('now') AS ok FROM alerts WHERE alert_key = ?",
            (f"+{int(cooldown_hours)} hours", alert_key),
        ).fetchone()["ok"]
        return bool(expired) or price < row["price"]


def mark_alert(alert_key: str, price: int):
    with conn() as c:
        c.execute(
            "INSERT INTO alerts(alert_key, price, sent_at) VALUES(?,?, datetime('now'))"
            " ON CONFLICT(alert_key) DO UPDATE SET price = excluded.price,"
            " sent_at = excluded.sent_at",
            (alert_key, int(price)),
        )
