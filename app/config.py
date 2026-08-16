import os
import re

from dotenv import load_dotenv

load_dotenv()


def clean(name: str, default: str = "") -> str:
    """Al pegar valores en el panel de Render se cuelan saltos de línea y espacios;
    en una URL o un token eso revienta la petición."""
    return re.sub(r"\s+", "", os.getenv(name, default))


DB_PATH = os.getenv("DB_PATH", "data/flights.db")
PORT = int(os.getenv("PORT", "8000"))

# Clave compartida con el runner de GitHub Actions.
INGEST_TOKEN = clean("INGEST_TOKEN")

# Para que el botón "Actualizar" dispare el workflow de scraping:
# https://api.github.com/repos/USUARIO/REPO/actions/workflows/scrape.yml/dispatches
SCRAPE_URL = clean("SCRAPE_URL")
GH_TOKEN = clean("GH_TOKEN")  # token clásico con permisos repo + workflow

# Lo editable desde la UI. El intervalo de búsqueda NO está aquí: vive en el
# cron del workflow, y las alertas se disparan por novedad, no por tiempo.
SETTING_DEFAULTS = {
    # Un numero por linea: "+573054305869" (o "+573054305869|apikey" para CallMeBot).
    "wa_recipients": os.getenv("WA_RECIPIENTS", ""),
}
