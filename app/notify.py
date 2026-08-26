import asyncio
import re
from datetime import date
from urllib.parse import quote

import httpx

from . import baggage, db, whatsapp


SIN_DESTINATARIOS = "sin números configurados"

# Cuántas compras caben en un mensaje antes de volverse ilegible (y de que
# CallMeBot lo corte en 900 caracteres).
MAX_EN_MENSAJE = 3

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fmt(price: int) -> str:
    """120000 -> $120.000 (miles con punto, como se lee en Colombia)."""
    return "$" + f"{int(price):,}".replace(",", ".")


def fecha_corta(iso: str | None) -> str:
    """'2026-09-25' -> 'vie 25 sep'."""
    if not iso:
        return "?"
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"


def leg_line(etiqueta: str, leg: dict, fecha: str | None, con_aerolinea: bool = False) -> str:
    """'Ida vie 25 sep 05:22→06:20 · Go Standard (mano 10 kg) · $159.102 p/p'"""
    o = leg["option"]
    horas = leg.get("depart_time") or "?"
    if leg.get("arrive_time"):
        horas += f"→{leg['arrive_time']}"
    partes = [f"{etiqueta} {fecha_corta(fecha)} {horas}"]
    if con_aerolinea:
        partes.append(leg["airline"])
    nombre = o.get("fare_name")
    partes.append(f"{nombre} ({o['short']})" if nombre else o["label"])
    aprox = "≈" if o["source"] == "estimado" else ""
    partes.append(f"{aprox}{fmt(o['price'])} p/p")
    return "  " + " · ".join(partes)


def build_message(watch: dict, hits: list[dict]) -> str:
    """El mensaje de WhatsApp: cuánto es el total y qué equipaje trae ese precio."""
    adults = max(1, int(watch.get("adults") or 1))
    ida_vuelta = bool(watch.get("return_date"))
    compras = sorted(hits, key=lambda c: c["total"])
    bajadas = [c for c in compras if c.get("novedad") == "bajo"]

    titulo = "📉 Bajó de precio" if bajadas else "✈️ Nueva oferta"
    ruta = f"{watch['origin']}→{watch['destination']}"
    fechas = fecha_corta(watch["date"])
    if ida_vuelta:
        fechas += f" → {fecha_corta(watch['return_date'])}"

    pedido = watch.get("bag_level") or baggage.ANY
    if pedido in baggage.RANK:
        equipaje = f"{baggage.ICON[pedido]} {baggage.LABEL[pedido]} — {baggage.DETAIL[pedido]}"
    else:
        equipaje = "💸 El más barato, sin exigir equipaje"

    viajeros = f"{adults} adulto" + ("s" if adults > 1 else "")
    lines = [
        f"{titulo} · {ruta}",
        f"🗓 {fechas} · 👤 {viajeros}" + (" · ida y vuelta" if ida_vuelta else " · solo ida"),
        equipaje,
        f"💰 Total desde {fmt(compras[0]['total'])} · tu filtro: menos de {fmt(watch['max_price'])}",
        "",
    ]

    for c in compras[:MAX_EN_MENSAJE]:
        if c.get("novedad") == "bajo":
            marca = f"↓ antes {fmt(c['antes'])}"
        else:
            marca = "🆕"
        aprox = "≈" if c["source"] == "estimado" else ""
        titulo = (
            f"{c['out']['airline']} ida · {c['ret']['airline']} vuelta"
            if c["mixed"]
            else c["airline"]
        )
        lines.append(f"• {titulo} — {aprox}{fmt(c['total'])} el total {marca}")
        if c["mixed"]:
            lines.append("  (dos compras, una en cada aerolínea)")
        lines.append(leg_line("Ida", c["out"], watch["date"], c["mixed"]))
        if c["ret"]:
            lines.append(leg_line("Vta", c["ret"], watch.get("return_date"), c["mixed"]))
        extra = c["out"]["option"]["extra"] + (c["ret"]["option"]["extra"] if c["ret"] else 0)
        tramos = ""
        if c["ret"]:
            tramos = f" (ida {fmt(c['out']['option']['price'])} + vuelta {fmt(c['ret']['option']['price'])})"
        personas = f"{adults} persona" + ("s" if adults > 1 else "")
        # Con un solo pasajero y un solo tramo, el desglose repetiría el total.
        if adults > 1 or c["ret"]:
            lines.append(
                f"  Por persona {fmt(c['per_person'])}{tramos} × {personas} = {fmt(c['total'])} total"
            )
        if extra:
            lines.append(
                f"  De cada persona, {fmt(extra)} es el equipaje "
                f"({fmt(c['per_person'] - extra)} el vuelo)."
            )
        else:
            lines.append("  Ese precio no incluye ningún equipaje pago.")
        if c["out"].get("url"):
            lines.append(f"  {c['out']['url']}")
        if c["ret"] and c["mixed"] and c["ret"].get("url"):
            lines.append(f"  {c['ret']['url']}")

    if len(compras) > MAX_EN_MENSAJE:
        lines.append(f"…y {len(compras) - MAX_EN_MENSAJE} opciones más en la app.")

    fuentes = {c["source"] for c in compras[:MAX_EN_MENSAJE]}
    if "estimado" in fuentes:
        lines.append("")
        lines.append("⚠️ No se pudo abrir el panel de tarifas: el precio del equipaje es una "
                     "estimación. Verifica antes de pagar.")
    elif "derivado" in fuentes:
        lines.append("")
        lines.append("ℹ️ El costo del equipaje es el que cobra hoy la aerolínea en esa ruta, "
                     "leído en el vuelo más barato del día.")
    return "\n".join(lines)


def parse_recipients(raw: str) -> list[tuple[str, str | None]]:
    """Una línea por persona. Acepta '+57300...' o '+57300...|apikey' (CallMeBot)."""
    out = []
    for line in (raw or "").splitlines():
        parts = [p.strip() for p in re.split(r"[|:,;]", line) if p.strip()]
        if parts:
            out.append((parts[0], parts[1] if len(parts) > 1 else None))
    return out


def send_callmebot(phone: str, apikey: str, text: str) -> str:
    """Respaldo para cuando WhatsApp Web no está vinculado."""
    url = (
        "https://api.callmebot.com/whatsapp.php"
        f"?phone={quote(phone)}&apikey={quote(apikey)}&text={quote(text[:900])}"
    )
    try:
        r = httpx.get(url, timeout=30)
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", r.text)).strip()
        if r.status_code == 200 and not re.search(r"error|invalid|not found", plain, re.I):
            return f"{phone}: ok (CallMeBot)"
        m = re.search(r"((?:APIKey|You need|Phone|Error|Invalid)[^<]{0,90})", plain, re.I)
        return f"{phone}: {m.group(1).strip() if m else r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return f"{phone}: error {exc}"


async def send_message(text: str) -> list[str]:
    """Manda por WhatsApp Web (QR). Si no está vinculado, cae a CallMeBot."""
    people = parse_recipients(db.get_settings().get("wa_recipients", ""))
    if not people:
        return [SIN_DESTINATARIOS]

    if whatsapp.STATE["status"] != "conectado":
        await whatsapp.refresh_state(wait_s=8)

    if whatsapp.STATE["status"] == "conectado":
        try:
            return await whatsapp.send_all([p for p, _ in people], text)
        finally:
            await whatsapp.stop()  # libera la RAM; la sesión queda en disco

    results = []
    for phone, apikey in people:
        if apikey:
            results.append(await asyncio.to_thread(send_callmebot, phone, apikey, text))
        else:
            results.append(f"{phone}: WhatsApp sin vincular (escanea el QR)")
    return results


async def notify(watch: dict, hits: list[dict]) -> list[str]:
    return await send_message(build_message(watch, hits))
