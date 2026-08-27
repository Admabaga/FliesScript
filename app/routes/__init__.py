"""Las rutas HTTP, una por tema. Solo traducen peticiones a llamadas de dominio."""

from . import diagnostics, ingest, settings, watches, whatsapp

ROUTERS = [
    watches.router,
    ingest.router,
    settings.router,
    whatsapp.router,
    diagnostics.router,
]

__all__ = ["ROUTERS", "watches", "ingest", "settings", "whatsapp", "diagnostics"]
