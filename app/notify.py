import re
from urllib.parse import quote

import httpx

from . import db


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


def parse_recipients(raw: str) -> list[tuple[str, str]]:
    """'+573054305869|123456' por linea -> [(telefono, apikey)]. Tolera ':' y ','."""
    out = []
    for line in (raw or "").splitlines():
        parts = [p.strip() for p in re.split(r"[|:,;]", line) if p.strip()]
        if len(parts) >= 2:
            out.append((parts[0], parts[1]))
    return out


def send_whatsapp(text: str) -> list[str]:
    """CallMeBot: gratis, sin cuenta. La apikey es por telefono, una por persona.
    https://www.callmebot.com/blog/free-api-whatsapp-messages/"""
    people = parse_recipients(db.get_settings().get("wa_recipients", ""))
    if not people:
        return ["sin números configurados"]
    results = []
    for phone, apikey in people:
        url = (
            "https://api.callmebot.com/whatsapp.php"
            f"?phone={quote(phone)}&apikey={quote(apikey)}&text={quote(text[:900])}"
        )
        try:
            r = httpx.get(url, timeout=30)
            # CallMeBot responde HTML; el motivo del fallo va dentro.
            plain = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", r.text)).strip()
            bad = r.status_code != 200 or re.search(r"error|invalid|not found", plain, re.I)
            if not bad:
                results.append(f"{phone}: ok")
            else:
                m = re.search(r"((?:APIKey|You need|Phone|Error|Invalid)[^<]{0,90})", plain, re.I)
                results.append(f"{phone}: {m.group(1).strip() if m else r.status_code}")
        except Exception as exc:  # noqa: BLE001
            results.append(f"{phone}: error {exc}")
    return results


def notify(watch: dict, hits: list[dict]) -> list[str]:
    return send_whatsapp(build_message(watch, hits))
