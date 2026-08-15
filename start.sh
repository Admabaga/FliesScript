#!/bin/sh
# Dos procesos: el sidecar de WhatsApp (Node) y la app web (Python).
# El sidecar va en segundo plano; uvicorn se queda como proceso principal para
# que abra el puerto de inmediato y Render no mate el servicio.
PORT="${PORT:-8000}"
echo "Flight: arrancando en el puerto $PORT"

if command -v node >/dev/null 2>&1; then
  (cd whatsapp-bot && node index.js) &
  echo "Flight: sidecar de WhatsApp levantado"
else
  echo "AVISO: Node no disponible, no habrá alertas por WhatsApp."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
