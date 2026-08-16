"""Recibe los resultados del runner (GitHub Actions), los guarda y decide si alertar.

El scraping NO ocurre aquí: pasa en GitHub Actions, donde hay CPU y RAM de verdad.
Render solo guarda, muestra y manda los WhatsApp (que sí caben en 512 MB).
"""

import logging
from datetime import date, datetime

from . import db, notify

log = logging.getLogger("engine")

STATE = {"running": False, "last_scan": None, "last_error": None}

# Bajada mínima para volver a avisar por un vuelo ya conocido: sin esto, una
# diferencia de $200 dispararía un mensaje.
MIN_DROP = 1000


def pending_watches() -> list[dict]:
    """Lo que el runner debe consultar: fechas activas que aún no han pasado."""
    today = date.today().isoformat()
    return [w for w in db.list_watches(only_active=True) if w["date"] >= today]


async def apply_results(watch_id: int, airlines: dict) -> dict:
    """airlines = {"Wingo": {"status": "ok", "flights": [...], "message": "..."}}"""
    watch = next((w for w in db.list_watches() if w["id"] == watch_id), None)
    if watch is None:
        return {"error": f"la fecha {watch_id} ya no existe"}

    hits = []
    for airline, data in airlines.items():
        flights = data.get("flights") or []
        status = data.get("status") or ("ok" if flights else "vacio")
        if status == "ok" and flights:
            db.replace_flights(watch_id, airline, flights)
            db.set_status(watch_id, airline, "ok", f"{len(flights)} vuelos")
            hits += [
                {**f, "airline": airline} for f in flights if f["price"] <= watch["max_price"]
            ]
        elif status == "vacio":
            db.replace_flights(watch_id, airline, [])
            db.set_status(watch_id, airline, "vacio", "sin vuelos en esa ruta/fecha")
        else:
            db.set_status(watch_id, airline, "error", data.get("message", "no se pudo leer"))

    sent = []
    if hits:
        # Solo se avisa lo que es noticia: un vuelo que no se había visto bajo el
        # filtro, o uno ya conocido que bajó de precio. Lo repetido no se manda.
        conocidos = db.alerted_prices(watch_id)
        to_alert = []
        for h in hits:
            key = f"{watch_id}|{h['airline']}|{h.get('depart_time')}"
            antes = conocidos.get(key)
            if antes is None:
                to_alert.append((key, {**h, "novedad": "nuevo"}))
            elif h["price"] <= antes - MIN_DROP:
                to_alert.append((key, {**h, "novedad": "bajo", "antes": antes}))
        if to_alert:
            sent = await notify.notify(watch, [h for _, h in to_alert])
            entregado = any(r.endswith(": ok") for r in sent)
            # Si no hay a quién avisar, igual se da por visto: no tiene sentido
            # acumular "novedades" que nadie va a recibir. Pero si había alguien
            # y el envío falló, queda pendiente para el próximo intento.
            if entregado or sent == [notify.SIN_DESTINATARIOS]:
                for key, h in to_alert:
                    db.mark_alert(key, h["price"])

    STATE["last_scan"] = datetime.now().isoformat(timespec="seconds")
    log.info("fecha %s: %s vuelos bajo el filtro, alertas=%s", watch_id, len(hits), sent)
    return {"watch_id": watch_id, "hits": len(hits), "alerts": sent}
