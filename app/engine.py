"""Recibe los resultados del runner (GitHub Actions), los guarda y decide si alertar.

El scraping NO ocurre aquí: pasa en GitHub Actions, donde hay CPU y RAM de verdad.
Render solo guarda, muestra y manda los WhatsApp (que sí caben en 512 MB).
"""

import logging
import re
from datetime import date, datetime

from . import baggage, db, notify, pricing

log = logging.getLogger("engine")

STATE = {"running": False, "last_scan": None, "last_error": None}

# Bajada mínima para volver a avisar por una compra ya conocida: sin esto, una
# diferencia de $200 dispararía un mensaje.
MIN_DROP = 1000


def pending_watches() -> list[dict]:
    """Lo que el runner debe consultar: fechas activas que aún no han pasado."""
    today = date.today().isoformat()
    return [w for w in db.list_watches(only_active=True) if w["date"] >= today]


def addon_overrides() -> dict:
    """Precio del equipaje suelto puesto a mano en Ajustes (vacío = usar la tabla)."""
    settings = db.get_settings()

    def num(key: str) -> int:
        digits = re.sub(r"\D", "", settings.get(key) or "")
        return int(digits) if digits else 0

    return {"carry_on": num("bag_carryon_cop"), "checked": num("bag_checked_cop")}


def store_airline(watch_id: int, airline: str, data: dict, overrides: dict) -> None:
    """Guarda lo de una aerolínea: vuelos de ida y vuelta, cada uno con sus tarifas.

    `data` = {"status", "flights": [{..., "direction"}], "ladders": {"out": {...}}}
    """
    flights = data.get("flights") or []
    status = data.get("status") or ("ok" if flights else "vacio")

    if status != "ok" or not flights:
        if status == "vacio":
            db.replace_flights(watch_id, airline, [])
            db.set_status(watch_id, airline, "vacio", "sin vuelos en esa ruta/fecha")
        else:
            db.set_status(watch_id, airline, "error", data.get("message", "no se pudo leer"))
        return

    ladders = data.get("ladders") or {}
    con_tarifas = []
    for f in flights:
        direction = f.get("direction") or "out"
        ladder = ladders.get(direction) or {}
        con_tarifas.append(
            {
                **f,
                "direction": direction,
                "fares": baggage.build_fares(airline, f["price"], ladder, overrides),
            }
        )
    db.replace_flights(watch_id, airline, con_tarifas)

    # El estado dice de dónde salió el precio del equipaje: leído o estimado.
    leidas = any((ladders.get(d) or {}).get("deltas") for d in ("out", "ret"))
    detalle = f"{len(con_tarifas)} vuelos · equipaje {'leído' if leidas else 'estimado'}"
    if data.get("message"):
        detalle += f" · {data['message']}"
    db.set_status(watch_id, airline, "ok", detalle)


async def apply_results(watch_id: int, airlines: dict) -> dict:
    """Guarda lo que encontró el runner y avisa solo lo que es noticia."""
    watch = next((w for w in db.list_watches() if w["id"] == watch_id), None)
    if watch is None:
        return {"error": f"la fecha {watch_id} ya no existe"}

    overrides = addon_overrides()
    for airline, data in airlines.items():
        store_airline(watch_id, airline, data, overrides)

    # Las compras se calculan sobre todo lo guardado, no solo sobre lo que acaba
    # de llegar: en ida y vuelta un tramo puede venir de otra aerolínea.
    compras = pricing.combos(watch, db.get_flights(watch_id))
    hits = [c for c in compras if c["hit"]]

    sent = []
    if hits:
        # Solo es noticia una compra que no se había visto bajo el filtro, o una
        # ya avisada que bajó de precio. Lo mismo al mismo precio no se repite.
        conocidos = db.alerted_prices(watch_id)
        to_alert = []
        for c in hits:
            key = pricing.combo_key(watch_id, c)
            antes = conocidos.get(key)
            if antes is None:
                to_alert.append((key, {**c, "novedad": "nuevo"}))
            elif c["total"] <= antes - MIN_DROP:
                to_alert.append((key, {**c, "novedad": "bajo", "antes": antes}))
        if to_alert:
            sent = await notify.notify(watch, [c for _, c in to_alert])
            entregado = any(r.endswith(": ok") for r in sent)
            # Si no hay a quién avisar, igual se da por visto: no tiene sentido
            # acumular "novedades" que nadie va a recibir. Pero si había alguien
            # y el envío falló, queda pendiente para el próximo intento.
            if entregado or sent == [notify.SIN_DESTINATARIOS]:
                for key, c in to_alert:
                    db.mark_alert(key, c["total"])

    STATE["last_scan"] = datetime.now().isoformat(timespec="seconds")
    log.info("fecha %s: %s compras bajo el filtro, alertas=%s", watch_id, len(hits), sent)
    return {"watch_id": watch_id, "hits": len(hits), "alerts": sent}
