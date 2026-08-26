"""Las dos rutas que usa el runner de GitHub Actions.

Van protegidas por `INGEST_TOKEN`: son las únicas que escriben precios.
"""

from fastapi import APIRouter, Body, Header, HTTPException

from .. import engine
from ..config import INGEST_TOKEN

router = APIRouter(prefix="/api", tags=["runner"])


def check_token(token: str | None) -> None:
    if not INGEST_TOKEN:
        raise HTTPException(503, "falta configurar INGEST_TOKEN en el servidor")
    if token != INGEST_TOKEN:
        raise HTTPException(401, "token inválido")


@router.get("/pending")
async def pending(x_token: str | None = Header(default=None)):
    """El runner pregunta qué búsquedas debe consultar."""
    check_token(x_token)
    return {"watches": engine.pending_watches()}


@router.post("/results")
async def results(payload: dict = Body(...), x_token: str | None = Header(default=None)):
    """El runner entrega lo que encontró; aquí se guarda y se alerta."""
    check_token(x_token)
    return await engine.apply_results(payload["watch_id"], payload.get("airlines", {}))
