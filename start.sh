#!/bin/sh
# Arranca bajo una pantalla virtual. Si xvfb no estuviera disponible, arranca
# igual en headless: Wingo y JetSMART siguen funcionando y solo cae Avianca.
set -e
PORT="${PORT:-8000}"
APP="uvicorn app.main:app --host 0.0.0.0 --port $PORT"

if command -v xvfb-run >/dev/null 2>&1; then
  exec xvfb-run -a --server-args="-screen 0 1366x900x24" $APP
else
  echo "AVISO: xvfb no disponible, arrancando en headless (Avianca fallará)."
  export HEADLESS=true
  exec $APP
fi
