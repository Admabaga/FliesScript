import re

from .base import dedupe, extract_times, standard, to_int_price

NAME = "Wingo"
ENGINE = "playwright"
CARD = "w-org-flight-card"


def search_url(origin: str, destination: str, date: str) -> str:
    # /es/search/{origen}/{destino}/{fecha}/{adultos}/{ninos}/{infantes}/{?}/{moneda}/0/0
    return (
        f"https://booking.wingo.com/es/search/{origin}/{destination}/{date}"
        f"/1/0/0/1/COP/0/0"
    )


async def scrape(origin: str, destination: str, date: str) -> list[dict]:
    url = search_url(origin, destination, date)
    ctx, page = await standard.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_selector(CARD, timeout=45_000)
        cards = await page.locator(CARD).all_inner_texts()
    finally:
        await ctx.close()

    flights = []
    for raw in cards:
        text = " | ".join(line.strip() for line in raw.splitlines() if line.strip())
        price = None
        m = re.search(r"\$\s*([\d.,]+)\s*COP", text)
        if m:
            price = to_int_price(m.group(1))
        if not price:
            continue
        times = extract_times(text)
        flight_no = None
        fm = re.search(r"\b([A-Z0-9]{2}\s?\d{2,4})\b", text)
        if fm:
            flight_no = fm.group(1)
        dm = re.search(r"\b(\d+h\s?\d*m?|\d+m)\b", text)
        flights.append(
            {
                "depart_time": times[0] if times else None,
                "arrive_time": times[1] if len(times) > 1 else None,
                "duration": dm.group(1) if dm else None,
                "flight_no": flight_no,
                "price": price,
                "url": url,
            }
        )
    return dedupe(flights)
