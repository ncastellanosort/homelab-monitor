#!/usr/bin/env bash
# deploy.sh — sube el monitor al ESP32 en una sola sesion de mpremote.
#
#   ./deploy.sh [PUERTO] [--mpy] [--dry-run]
#
#   PUERTO     /dev/ttyUSB0, COM3, ... (por defecto: auto)
#   --mpy      precompila los modulos con mpy-cross (menos RAM al importar)
#   --dry-run  muestra el comando de mpremote sin ejecutarlo
#
# Variables opcionales: MPREMOTE, MPY_CROSS (rutas a los ejecutables).
# Si la placa no responde (monitor bloqueando el REPL o watchdog reiniciando),
# haz safe-boot: pulsa EN/RST, suelta, y pulsa BOOT antes de 3 s. Luego repite.
set -euo pipefail

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }

PORT=auto
MPY=0
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --mpy) MPY=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "Opcion desconocida: $1" >&2; usage >&2; exit 2 ;;
    *) PORT=$1 ;;
  esac
  shift
done

cd "$(dirname "$0")"
MPREMOTE=${MPREMOTE:-mpremote}
MPY_CROSS=${MPY_CROSS:-mpy-cross}

# Borra en la placa todos los modulos (.py salvo boot/main, y .mpy): un .py
# viejo tendria prioridad sobre un .mpy nuevo. El .env no se toca.
CLEAN="import os;[os.remove(f) for f in os.listdir() if f.endswith('.mpy') or (f.endswith('.py') and f not in ('boot.py','main.py'))]"

files=()
if [ "$MPY" = 1 ]; then
  rm -rf build && mkdir -p build
  for f in src/*.py; do
    name=$(basename "$f")
    case "$name" in
      boot.py|main.py) files+=("$f") ;;   # MicroPython solo ejecuta los .py
      *) "$MPY_CROSS" -o "build/${name%.py}.mpy" "$f"
         files+=("build/${name%.py}.mpy") ;;
    esac
  done
else
  files=(src/*.py)
fi

args=(connect "$PORT" exec "$CLEAN" + cp "${files[@]}" :)
if [ -f .env ]; then
  args+=(+ cp .env :.env)
else
  echo "AVISO: no hay .env; se conserva el que ya tenga la placa (cp .env.example .env)." >&2
fi
args+=(+ reset)

if [ "$DRY" = 1 ]; then
  printf '%q ' "$MPREMOTE" "${args[@]}"
  echo
  exit 0
fi

echo "Subiendo ${#files[@]} archivos a $PORT ..."
"$MPREMOTE" "${args[@]}"
echo "Listo. La placa se ha reiniciado; ver salida con: $MPREMOTE connect $PORT"
