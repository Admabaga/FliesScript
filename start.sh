#!/bin/sh
# Arranca la pantalla virtual APARTE y deja que uvicorn tome el proceso principal.
# (Con `xvfb-run uvicorn ...` el puerto no llegaba a abrirse y Render lo mataba.)
PORT="${PORT:-8000}"
echo "Flight: arrancando en el puerto $PORT"

if command -v Xvfb >/dev/null 2>&1; then
  Xvfb :99 -screen 0 1366x900x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
  export DISPLAY=:99
  sleep 2
  echo "Flight: pantalla virtual lista en DISPLAY=$DISPLAY"
else
  echo "AVISO: Xvfb no disponible, se usa headless (Avianca fallará)."
  export HEADLESS=true
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
