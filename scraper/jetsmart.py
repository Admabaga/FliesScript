import re

from .base import dedupe, extract_times, stealth, to_int_price

NAME = "JetSMART"
ENGINE = "patchright"


def search_url(origin: str, destination: str, date: str) -> str:
    return (
        "https://booking.jetsmart.com/Flight/InternalSelect"
        f"?c=true&mon=true&r=false&cur=COP&culture=es-CO"
        f"&dd1={date}&o1={origin}&d1={destination}"
    )


async def scrape(origin: str, destination: str, date: str) -> list[dict]:
    url = search_url(origin, destination, date)
    ctx, page = await stealth.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded")

        # Interstitial anti-bot ("Client Challenge"): se resuelve solo en unos segundos.
        for _ in range(20):
            if "Client Challenge" not in (await page.title()):
                break
            await page.wait_for_timeout(1500)

        # JetSMART abre primero el calendario de precios; hay que pulsar "Continuar".
        await page.wait_for_selector("text=Calendario precios", timeout=45_000)
        cont = page.locator("div.cursor-pointer", has_text=re.compile(r"^\s*Continuar\s*$"))
        if await cont.count():
            await cont.first.click()

        await page.wait_for_selector("text=Vuelo Operado por", timeout=45_000)
        await page.wait_for_timeout(1500)
        cards = await page.locator("div:has-text('Vuelo Operado por')").all_inner_texts()
    finally:
        await ctx.close()

    flights = []
    for raw in cards:
        text = " | ".join(line.strip() for line in raw.splitlines() if line.strip())
        # Descarta contenedores grandes que envuelven varias tarjetas.
        if text.count("Vuelo Operado por") != 1 or len(text) > 900:
            continue
        prices = [p for p in (to_int_price(x) for x in re.findall(r"\$\s*([\d.,]+)", text)) if p]
        if not prices:
            continue
        times = extract_times(text)
        dm = re.search(r"(\d+h\s?\d*\s?min|\d+\s?min)", text)
        flights.append(
            {
                "depart_time": times[0] if times else None,
                "arrive_time": times[1] if len(times) > 1 else None,
                "duration": dm.group(1) if dm else None,
                "flight_no": None,
                "price": min(prices),
                "url": url,
            }
        )
    return dedupe(flights)
