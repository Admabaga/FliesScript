from . import avianca, jetsmart, wingo

# Agrupadas por motor (wingo y avianca comparten Chromium) para no abrir dos.
AIRLINES = [wingo, avianca, jetsmart]
NAMES = [m.NAME for m in AIRLINES]

__all__ = ["AIRLINES", "NAMES", "wingo", "jetsmart", "avianca"]
