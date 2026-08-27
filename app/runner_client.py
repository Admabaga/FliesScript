"""Lo que la app le pide al runner de GitHub Actions.

El scraping no ocurre aquí (no cabe un navegador en 512 MB): esta es la única
parte de la app que habla con Actions, y traduce las respuestas de GitHub a algo
que la interfaz pueda mostrar tal cual.

**Por qué hay un vigilante y no basta el `cron`:** el `*/10` del workflow es una
intención, no una promesa. GitHub retrasa (y se salta) los cron de alta
frecuencia cuando su cola está cargada; midiendo un día entero de este repo el
intervalo real fue de **53 min de promedio, con huecos de hasta 2 horas**. Los
`workflow_dispatch`, en cambio, arrancan de inmediato.

Así que la app se vigila a sí misma: si los precios están viejos, pide una
búsqueda. Se revisa cada pocos minutos y también en cada `/health`, que es lo que
UptimeRobot golpea para que Render no se duerma: ese ping se vuelve el latido.
Con eso el `cron` queda de red de seguridad, no de motor.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from . import db
from .config import GH_TOKEN, SCRAPE_URL

log = logging.getLogger("runner")

ESPERA_REHIDRATAR_S = 60

# Precios más viejos que esto = hay que volver a buscar.
VIEJO_MIN = 12
# Nunca pedir dos búsquedas seguidas antes de esto (una corrida tarda ~3 min).
ESPERA_BASE_MIN = 8
# Si pedir no sirve (el runner falla, falta el token), se espera cada vez más.
ESPERA_MAX_MIN = 60
TICK_S = 240


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


# ------------------------------------------------------------------ vigilante

ESTADO = {
    "ultimo_intento": None,  # cuándo se pidió la última búsqueda (UTC)
    "espera_min": ESPERA_BASE_MIN,
    "detalle": None,  # qué respondió GitHub la última vez
    "visto": None,  # qué antigüedad tenían los precios en ese intento
}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _leer_utc(texto: str | None) -> datetime | None:
    """SQLite guarda 'YYYY-MM-DD HH:MM:SS' en UTC, sin zona."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def edad_de_los_precios() -> float | None:
    """Minutos desde que llegaron los últimos precios, o None si nunca llegaron."""
    ultimo = _leer_utc(db.last_scrape_at())
    if ultimo is None:
        return None
    return (_ahora() - ultimo).total_seconds() / 60


def estado_vigilante() -> dict:
    """Lo que la UI (y /health) muestran del vigilante."""
    edad = edad_de_los_precios()
    return {
        "activo": bool(SCRAPE_URL),
        "edad_min": round(edad) if edad is not None else None,
        "ultimo_intento": ESTADO["ultimo_intento"].isoformat(timespec="seconds")
        if ESTADO["ultimo_intento"]
        else None,
        "espera_min": ESTADO["espera_min"],
        "detalle": ESTADO["detalle"],
    }


async def ensure_fresh() -> dict:
    """Pide una búsqueda si los precios están viejos. Es idempotente y barato:
    se puede llamar en cada `/health` sin miedo."""
    if not SCRAPE_URL:
        return {"pedida": False, "motivo": "sin SCRAPE_URL configurado"}
    if not db.list_watches(only_active=True):
        return {"pedida": False, "motivo": "no hay búsquedas activas"}

    edad = edad_de_los_precios()
    if edad is not None and edad < VIEJO_MIN:
        # Llegaron precios frescos: lo que se pidió antes funcionó.
        ESTADO["espera_min"] = ESPERA_BASE_MIN
        return {"pedida": False, "motivo": f"precios de hace {edad:.0f} min"}

    ahora = _ahora()
    ultimo = ESTADO["ultimo_intento"]
    if ultimo and (ahora - ultimo) < timedelta(minutes=ESTADO["espera_min"]):
        return {"pedida": False, "motivo": "pedida hace poco"}

    # Si desde el intento anterior los precios no se movieron, pedir más seguido
    # no ayuda: algo está fallando (token sin permisos, runner en rojo).
    if ultimo and ESTADO["visto"] == db.last_scrape_at():
        ESTADO["espera_min"] = min(ESTADO["espera_min"] * 2, ESPERA_MAX_MIN)
    else:
        ESTADO["espera_min"] = ESPERA_BASE_MIN

    ESTADO["ultimo_intento"] = ahora
    ESTADO["visto"] = db.last_scrape_at()
    resultado = await trigger_scrape()
    ESTADO["detalle"] = resultado.get("detalle")
    log.info(
        "vigilante: precios de hace %s min -> %s (%s)",
        "nunca" if edad is None else f"{edad:.0f}",
        "pedida" if resultado.get("started") else "no se pudo",
        resultado.get("detalle"),
    )
    return {"pedida": bool(resultado.get("started")), **resultado}


async def watchdog() -> None:
    """Revisa cada pocos minutos, por si nadie golpea `/health`."""
    while True:
        await asyncio.sleep(TICK_S)
        try:
            await ensure_fresh()
        except Exception as exc:  # noqa: BLE001  el vigilante nunca debe tumbar la app
            log.warning("vigilante: %s", str(exc)[:150])
