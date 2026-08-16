import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, engine, notify, whatsapp
from .config import GH_TOKEN, INGEST_TOKEN, SCRAPE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

STATIC = Path(__file__).resolve().parent.parent / "static"
AIRLINES = ["Wingo", "JetSMART", "Avianca"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    asyncio.create_task(rehydrate())
    yield
    await whatsapp.stop()


app = FastAPI(title="Flight", lifespan=lifespan)


def check_token(token: str | None):
    if not INGEST_TOKEN:
        raise HTTPException(503, "falta configurar INGEST_TOKEN en el servidor")
    if token != INGEST_TOKEN:
        raise HTTPException(401, "token inválido")


@app.get("/health")
async def health():
    return {"ok": True, **engine.STATE}


# ---------------------------------------------------------------- fechas / UI


@app.get("/api/watches")
async def get_watches():
    out = []
    for w in db.list_watches():
        out.append({**w, "flights": db.get_flights(w["id"]), "status": db.get_statuses(w["id"])})
    return {
        "watches": out,
        "airlines": AIRLINES,
        "last_scan": engine.STATE["last_scan"],
        "running": engine.STATE["running"],
    }


@app.post("/api/watches")
async def post_watch(payload: dict = Body(...)):
    for field in ("origin", "destination", "date", "max_price"):
        if not payload.get(field):
            raise HTTPException(400, f"falta {field}")
    watch_id = db.add_watch(
        payload["origin"], payload["destination"], payload["date"], payload["max_price"]
    )
    asyncio.create_task(trigger_scrape())  # que el runner la mire ya
    return {"id": watch_id}


@app.patch("/api/watches/{watch_id}")
async def patch_watch(watch_id: int, payload: dict = Body(...)):
    db.update_watch(watch_id, **payload)
    return {"ok": True}


@app.delete("/api/watches/{watch_id}")
async def del_watch(watch_id: int):
    db.delete_watch(watch_id)
    return {"ok": True}


# ------------------------------------------------- runner (GitHub Actions)


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
        if r.status_code < 300:
            return {"started": True, "detalle": "buscando… los precios llegan en ~3 min"}
        if r.status_code in (401, 403):
            return {"started": False, "detalle": "el token no tiene permiso sobre el repo"}
        if r.status_code == 404:
            # GitHub responde 404 (no 401) cuando la petición va sin credenciales.
            falta = "falta GH_TOKEN en Render" if not GH_TOKEN else (
                "el token debe ser de la cuenta dueña del repo, con permisos repo + workflow"
            )
            return {"started": False, "detalle": f"GitHub respondió 404: {falta}"}
        return {"started": False, "detalle": f"GitHub respondió {r.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"started": False, "detalle": str(exc)[:120]}


async def rehydrate():
    """Tras un reinicio de Render la base queda vacía (el plan free no tiene disco).
    Si al minuto hay fechas sin precios, se le pide al runner que las llene."""
    await asyncio.sleep(60)
    watches = db.list_watches(only_active=True)
    if watches and not any(db.get_flights(w["id"]) for w in watches):
        log.info("Base vacía tras reiniciar: pidiendo al runner que busque")
        await trigger_scrape()


@app.post("/api/scan")
async def post_scan():
    return await trigger_scrape()


@app.get("/api/pending")
async def pending(x_token: str | None = Header(default=None)):
    """El runner pregunta qué fechas debe consultar."""
    check_token(x_token)
    return {"watches": engine.pending_watches()}


@app.post("/api/results")
async def results(payload: dict = Body(...), x_token: str | None = Header(default=None)):
    """El runner entrega lo que encontró; aquí se guarda y se alerta."""
    check_token(x_token)
    return await engine.apply_results(payload["watch_id"], payload.get("airlines", {}))


# ------------------------------------------------------------- ajustes / WhatsApp


@app.get("/api/settings")
async def get_settings():
    return db.get_settings()


@app.post("/api/settings")
async def post_settings(payload: dict = Body(...)):
    db.save_settings(payload)
    return {"ok": True}


@app.post("/api/test-alert")
async def test_alert():
    return {
        "results": await notify.send_message(
            "✈️ Flight — mensaje de prueba. Si lees esto, las alertas funcionan."
        )
    }


@app.get("/api/whatsapp")
async def whatsapp_status():
    """Se consulta al sidecar cada vez: el QR de allá se renueva solo."""
    return await whatsapp.refresh_state()


@app.post("/api/whatsapp/connect")
async def whatsapp_connect():
    """El sidecar ya tiene el QR listo; la UI lo va leyendo con GET."""
    return await whatsapp.start_pairing()


@app.post("/api/whatsapp/logout")
async def whatsapp_logout():
    """Cierra la sesión para vincular otro teléfono."""
    return await whatsapp.logout()


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")
