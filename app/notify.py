import asyncio
import re
from urllib.parse import quote

import httpx

from . import db, whatsapp


def fmt(price: int) -> str:
    """120000 -> $120.000 (miles con punto, como se lee en Colombia)."""
    return "$" + f"{int(price):,}".replace(",", ".")


def build_message(watch: dict, hits: list[dict]) -> str:
    route = f"{watch['origin']}→{watch['destination']}"
    cheapest = min(h["price"] for h in hits)
    lines = [
        f"✈️ {route} · {watch['date']} · desde {fmt(cheapest)}",
        f"(tu filtro: menos de {fmt(watch['max_price'])})",
        "",
    ]
    for h in sorted(hits, key=lambda x: x["price"]):
        hora = h.get("depart_time") or "?"
        llegada = f"-{h['arrive_time']}" if h.get("arrive_time") else ""
        lines.append(f"• {h['airline']} {hora}{llegada} → {fmt(h['price'])}")
    lines.append("")
    for airline in sorted({h["airline"] for h in hits}):
        lines.append(next(h["url"] for h in hits if h["airline"] == airline))
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
        return ["sin números configurados"]

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
