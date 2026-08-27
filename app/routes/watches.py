"""Las búsquedas: crear, cambiar, borrar y leer con sus precios."""

import asyncio

from fastapi import APIRouter, Body, HTTPException

from .. import baggage, db, engine, pricing, runner_client
from ..validation import clean_watch

router = APIRouter(prefix="/api", tags=["watches"])

AIRLINES = ["Wingo", "JetSMART", "Avianca"]

# Cambiar esto obliga a volver a consultar: es otra búsqueda distinta.
CAMPOS_QUE_PIDEN_SCRAPE = {"date", "return_date", "adults", "origin", "destination"}


def _vocabulario_equipaje() -> dict:
    """Las etiquetas del equipaje salen del backend para que la pantalla, el
    filtro y el WhatsApp digan exactamente lo mismo."""
    return {
        "bag_filters": baggage.FILTERS,
        "bag_labels": {
            "label": baggage.LABEL,
            "short": baggage.SHORT,
            "icon": baggage.ICON,
            "detail": baggage.DETAIL,
        },
    }


@router.get("/watches")
async def get_watches():
    watches = [
        {
            **w,
            "status": db.get_statuses(w["id"]),
            **pricing.summary(w, db.get_flights(w["id"])),
        }
        for w in db.list_watches()
    ]
    return {
        "watches": watches,
        "airlines": AIRLINES,
        **_vocabulario_equipaje(),
        "last_scan": engine.STATE["last_scan"],
        "running": engine.STATE["running"],
        # Para que se note si la búsqueda automática dejó de funcionar en vez de
        # quedarse callada: edad de los precios y qué respondió GitHub.
        "auto": runner_client.estado_vigilante(),
    }


@router.post("/watches")
async def post_watch(payload: dict = Body(...)):
    datos = clean_watch(payload)
    ya_existia = db.find_watch(
        datos["origin"],
        datos["destination"],
        datos["date"],
        datos.get("return_date") or None,
        datos.get("adults", 1),
        datos.get("bag_level", baggage.ANY),
    )
    watch_id = db.add_watch(
        datos["origin"],
        datos["destination"],
        datos["date"],
        datos["max_price"],
        return_date=datos.get("return_date") or None,
        adults=datos.get("adults", 1),
        bag_level=datos.get("bag_level", baggage.ANY),
    )
    # Solo se pide búsqueda si la fecha es nueva. Al reponer la copia del
    # navegador llegan varias altas de golpe, y una corrida de Actions por cada
    # una solo sirve para que GitHub cancele las anteriores.
    if ya_existia is None:
        asyncio.create_task(runner_client.trigger_scrape())
    return {"id": watch_id}


@router.patch("/watches/{watch_id}")
async def patch_watch(watch_id: int, payload: dict = Body(...)):
    actual = next((w for w in db.list_watches() if w["id"] == watch_id), None)
    if actual is None:
        raise HTTPException(404, "esa búsqueda ya no existe")

    datos = clean_watch(payload, partial=True, current=actual)

    # Editar una búsqueda hasta dejarla idéntica a otra chocaría con el índice
    # único; se avisa en vez de reventar.
    futuro = {**actual, **datos}
    gemela = db.find_watch(
        futuro["origin"],
        futuro["destination"],
        futuro["date"],
        futuro.get("return_date"),
        futuro.get("adults", 1),
        futuro.get("bag_level", baggage.ANY),
    )
    if gemela is not None and gemela != watch_id:
        raise HTTPException(409, "ya tienes otra búsqueda igual a esa")

    if "active" in payload:
        datos["active"] = 1 if payload["active"] else 0
    db.update_watch(watch_id, **datos)

    if CAMPOS_QUE_PIDEN_SCRAPE & set(datos):
        asyncio.create_task(runner_client.trigger_scrape())
    return {"ok": True}


@router.delete("/watches/{watch_id}")
async def del_watch(watch_id: int):
    db.delete_watch(watch_id)
    return {"ok": True}


@router.post("/scan")
async def post_scan():
    return await runner_client.trigger_scrape()
