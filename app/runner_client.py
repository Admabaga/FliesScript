"""Lo que la app le pide al runner de GitHub Actions.

El scraping no ocurre aquí (no cabe un navegador en 512 MB): esta es la única
parte de la app que habla con Actions, y traduce las respuestas de GitHub a algo
que la interfaz pueda mostrar tal cual.
"""

import asyncio
import logging

import httpx

from . import db
from .config import GH_TOKEN, SCRAPE_URL

log = logging.getLogger("runner")

ESPERA_REHIDRATAR_S = 60


def _diagnostico_404() -> str:
    if not GH_TOKEN:
        return "falta GH_TOKEN en Render"
    return "el token debe ser de la cuenta dueña del repo, con permisos repo + workflow"


async def trigger_scrape() -> dict:
    """Le pide a GitHub Actions que corra el scraping ahora, si está configurado."""
    if not SCRAPE_URL:
        return {"started": False, "detalle": "el runner corre solo cada 10 min"}

    headers = {"Accept": "application/vnd.github+json"}
    if GH_TOKEN:
        headers["Authorization"] = f"Bearer {GH_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(SCRAPE_URL, json={"ref": "main"}, headers=headers)
    except Exception as exc:  # noqa: BLE001
        return {"started": False, "detalle": str(exc)[:120]}

    if r.status_code < 300:
        return {"started": True, "detalle": "buscando… los precios llegan en ~3 min"}
    if r.status_code in (401, 403):
        return {"started": False, "detalle": "el token no tiene permiso sobre el repo"}
    if r.status_code == 404:
        # GitHub responde 404 (no 401) cuando la petición va sin credenciales.
        return {"started": False, "detalle": f"GitHub respondió 404: {_diagnostico_404()}"}
    return {"started": False, "detalle": f"GitHub respondió {r.status_code}"}


async def rehydrate() -> None:
    """Tras un reinicio de Render la base queda vacía (el plan free no tiene disco).
    Si al minuto hay búsquedas sin precios, se le pide al runner que las llene."""
    await asyncio.sleep(ESPERA_REHIDRATAR_S)
    watches = db.list_watches(only_active=True)
    if watches and not any(db.get_flights(w["id"]) for w in watches):
        log.info("Base vacía tras reiniciar: pidiendo al runner que busque")
        await trigger_scrape()
