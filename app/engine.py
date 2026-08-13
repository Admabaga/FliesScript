import asyncio
import logging
from datetime import date, datetime

from . import db, notify
from .scrapers import AIRLINES
from .scrapers.base import keep_only, stop_all

log = logging.getLogger("engine")

_lock = asyncio.Lock()
STATE = {"running": False, "last_scan": None, "last_error": None}


def friendly_error(exc: Exception) -> str:
    """La UI la lee un humano, no un dev: nada de selectores ni stack traces."""
    text = str(exc).lower()
    if "no aparecieron resultados" in text or "timeout" in text:
        return "no respondió a tiempo; se reintenta en la próxima revisión"
    if "net::" in text or "connection" in text:
        return "sin conexión con la aerolínea"
    return "no se pudo leer la página; se reintenta luego"


RETRIES = 3
RETRY_BACKOFF_S = [30, 90]  # los anti-bot penalizan las rafagas: mejor esperar
PACE_S = 12  # pausa entre consultas para no parecer un bot


async def _scrape_with_retries(module, watch: dict) -> list[dict]:
    """Los anti-bot (sobre todo Akamai en Avianca) fallan de forma intermitente."""
    last = None
    for attempt in range(RETRIES):
        try:
            return await module.scrape(watch["origin"], watch["destination"], watch["date"])
        except Exception as exc:  # noqa: BLE001
            last = exc
            log.info("%s intento %s/%s falló: %s", module.NAME, attempt + 1, RETRIES, exc)
            if attempt < RETRIES - 1:
                await asyncio.sleep(RETRY_BACKOFF_S[attempt])
    raise last


async def scan_watch(watch: dict) -> dict:
    """Consulta las 3 aerolineas para una fecha y dispara alertas si aplica."""
    hits = []
    for i, module in enumerate(AIRLINES):
        if i:
            await asyncio.sleep(PACE_S)
        try:
            await keep_only(module.ENGINE)  # un solo Chromium vivo a la vez
            flights = await _scrape_with_retries(module, watch)
            db.replace_flights(watch["id"], module.NAME, flights)
            if flights:
                db.set_status(watch["id"], module.NAME, "ok", f"{len(flights)} vuelos")
            else:
                db.set_status(watch["id"], module.NAME, "vacio", "sin vuelos en esa ruta/fecha")
            for f in flights:
                if f["price"] <= watch["max_price"]:
                    hits.append({**f, "airline": module.NAME})
        except Exception as exc:  # noqa: BLE001
            log.warning("scrape %s falló: %s", module.NAME, exc)
            db.set_status(watch["id"], module.NAME, "error", friendly_error(exc))

    sent = []
    cooldown = int(db.get_settings().get("alert_cooldown_h") or 8)
    to_alert = []
    for h in hits:
        key = f"{watch['id']}|{h['airline']}|{h.get('depart_time')}"
        if db.should_alert(key, h["price"], cooldown):
            to_alert.append((key, h))
    if to_alert:
        sent = notify.notify(watch, [h for _, h in to_alert])
        if any(r.endswith(": ok") for r in sent):
            for key, h in to_alert:
                db.mark_alert(key, h["price"])

    return {"watch_id": watch["id"], "hits": len(hits), "alerts": sent}


async def scan_all(only_watch_id: int | None = None) -> dict:
    if _lock.locked():
        return {"skipped": "ya hay un escaneo en curso"}
    async with _lock:
        STATE["running"] = True
        results = []
        try:
            today = date.today().isoformat()
            for watch in db.list_watches(only_active=True):
                if only_watch_id and watch["id"] != only_watch_id:
                    continue
                if watch["date"] < today:  # fecha vencida: no gastar scraping
                    db.set_status(watch["id"], "-", "vencida", "la fecha ya pasó")
                    continue
                if results:
                    await asyncio.sleep(PACE_S)
                results.append(await scan_watch(watch))
            STATE["last_error"] = None
        except Exception as exc:  # noqa: BLE001
            STATE["last_error"] = str(exc)
            log.exception("scan_all falló")
        finally:
            await stop_all()  # libera la RAM del navegador hasta el proximo escaneo
            STATE["running"] = False
            STATE["last_scan"] = datetime.now().isoformat(timespec="seconds")
        return {"results": results, "last_scan": STATE["last_scan"]}
