#!/bin/sh
# Dos procesos: el sidecar de WhatsApp (Node) y la app web (Python).
# El sidecar va en segundo plano; uvicorn se queda como proceso principal para
# que abra el puerto de inmediato y Render no mate el servicio.
PORT="${PORT:-8000}"
echo "Flight: arrancando en el puerto $PORT"

if command -v node >/dev/null 2>&1; then
  echo "Flight: node $(node -v)"
  # Supervisor simple: si el sidecar se cae, vuelve a levantarse.
  (
    cd whatsapp-bot || exit 1
    while true; do
      node index.js
      echo "[wa] el sidecar terminó (código $?); reintentando en 5s"
      sleep 5
    done
  ) &
else
  echo "AVISO: Node no disponible, no habrá alertas por WhatsApp."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
