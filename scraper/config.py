"""Configuración del scraper. Solo aplica al runner de GitHub Actions."""

import os

# Akamai (Avianca) detecta el modo headless y devuelve 403, así que el navegador
# corre "con ventana" sobre una pantalla virtual (xvfb en el workflow).
HEADLESS = os.getenv("HEADLESS", "false").lower() != "false"

NAV_TIMEOUT_MS = int(os.getenv("NAV_TIMEOUT_MS", "60000"))

# Perfiles persistentes del navegador: conservan las cookies del anti-bot.
PROFILE_ROOT = os.getenv("PROFILE_ROOT", "data/profiles")
