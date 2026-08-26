"""Validación de lo que llega del formulario.

Vive aparte de las rutas porque es una regla de negocio, no de transporte: una
vuelta antes de la ida está mal venga de la UI, de la copia del navegador o de
donde sea. Las rutas solo la invocan y devuelven el error.
"""

import re
from datetime import date

from fastapi import HTTPException

from . import baggage

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_ADULTOS = 9


def _texto(payload: dict, campo: str) -> str:
    return (payload.get(campo) or "").strip()


def _ruta(payload: dict, out: dict, partial: bool) -> None:
    for campo in ("origin", "destination"):
        valor = _texto(payload, campo).upper()
        if valor:
            out[campo] = valor
        elif not partial:
            raise HTTPException(400, f"falta {campo}")
    if out.get("origin") and out["origin"] == out.get("destination"):
        raise HTTPException(400, "el origen y el destino son el mismo")


def _fechas(payload: dict, out: dict, partial: bool, current: dict | None) -> None:
    if payload.get("date") or not partial:
        salida = _texto(payload, "date")
        if not DATE_RE.match(salida):
            raise HTTPException(400, "la fecha de ida no es válida")
        if salida < date.today().isoformat():
            raise HTTPException(400, "la fecha de ida ya pasó")
        out["date"] = salida

    if "return_date" not in payload:
        return
    regreso = _texto(payload, "return_date")
    if not regreso:
        out["return_date"] = ""  # volvió a ser solo ida
        return
    if not DATE_RE.match(regreso):
        raise HTTPException(400, "la fecha de vuelta no es válida")
    # La ida puede no venir en un PATCH: entonces se compara con la guardada.
    salida = out.get("date") or (current or {}).get("date") or ""
    if salida and regreso < salida:
        raise HTTPException(400, "la vuelta no puede ser antes de la ida")
    out["return_date"] = regreso


def _pasajeros(payload: dict, out: dict) -> None:
    if payload.get("adults") is None:
        return
    try:
        adultos = int(payload["adults"])
    except (TypeError, ValueError):
        raise HTTPException(400, "la cantidad de adultos no es válida") from None
    if not 1 <= adultos <= MAX_ADULTOS:
        raise HTTPException(400, f"los adultos van de 1 a {MAX_ADULTOS}")
    out["adults"] = adultos


def _equipaje(payload: dict, out: dict) -> None:
    if payload.get("bag_level") is None:
        return
    nivel = str(payload["bag_level"])
    if nivel not in {f["value"] for f in baggage.FILTERS}:
        raise HTTPException(400, "ese filtro de equipaje no existe")
    out["bag_level"] = nivel


def _precio(payload: dict, out: dict, partial: bool) -> None:
    if payload.get("max_price") is None and partial:
        return
    try:
        precio = int(payload.get("max_price") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "el precio no es válido") from None
    if precio <= 0:
        raise HTTPException(400, "falta el precio del filtro")
    out["max_price"] = precio


def clean_watch(payload: dict, partial: bool = False, current: dict | None = None) -> dict:
    """Deja lo que llegó listo para la base, o lanza 400 con el motivo.

    `partial` = PATCH: solo se revisa lo que viene. `current` es la búsqueda
    guardada, para comparar contra lo que el payload no trae.
    """
    out: dict = {}
    _ruta(payload, out, partial)
    _fechas(payload, out, partial, current)
    _pasajeros(payload, out)
    _equipaje(payload, out)
    _precio(payload, out, partial)
    return out
