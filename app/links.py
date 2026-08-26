"""Los enlaces de compra de cada aerolínea.

Viven aquí, y no dentro del scraper, por dos razones:

  - la imagen de la app (Docker) solo copia `app/`, así que es lo único que el
    servidor puede importar, y el enlace lo pinta la app;
  - el runner de GitHub Actions sí tiene todo el repo, y este módulo no importa
    nada, así que los scrapers lo usan sin arrastrar dependencias.

Los tres deep links llevan la cantidad de pasajeros y el buscador la respeta
(verificado: Wingo abre con "2 viajeros", Avianca con "2 Adultos", JetSMART con
"2 pasajeros"). Es la gracia del filtro de adultos: se llega a comprar sin
volver a llenar el formulario de la aerolínea.

Como el enlace se arma al momento de mostrarlo, cambiar los adultos de una
búsqueda ya lo actualiza, sin esperar a la siguiente revisión.
"""


def wingo(origin: str, destination: str, date: str, adults: int = 1) -> str:
    # /es/search/{origen}/{destino}/{fecha}/{adultos}/{ninos}/{infantes}/{?}/{moneda}/0/0
    return (
        f"https://booking.wingo.com/es/search/{origin}/{destination}/{date}"
        f"/{max(1, int(adults))}/0/0/1/COP/0/0"
    )


def jetsmart(origin: str, destination: str, date: str, adults: int = 1) -> str:
    return (
        "https://booking.jetsmart.com/Flight/InternalSelect"
        "?c=true&mon=true&r=false&cur=COP&culture=es-CO"
        f"&dd1={date}&o1={origin}&d1={destination}"
        f"&ADT={max(1, int(adults))}&CHD=0&INF=0"
    )


def avianca(origin: str, destination: str, date: str, adults: int = 1) -> str:
    return (
        "https://booking.avianca.com/av/booking/avail"
        f"?departureDate={date}&tripType=one-way&platform=WEBB2C"
        f"&from={origin}&to={destination}"
        f"&nbAdults={max(1, int(adults))}&nbYoungs=0&nbChildren=0&nbInfants=0"
        "&language=ES&pointOfSale=CO&accessMethod=default&backend=PRD"
    )


BUILDERS = {"Wingo": wingo, "JetSMART": jetsmart, "Avianca": avianca}


def search_url(
    airline: str, origin: str, destination: str, date: str, adults: int = 1
) -> str | None:
    build = BUILDERS.get(airline)
    return build(origin, destination, date, adults) if build else None
