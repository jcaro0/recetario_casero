#!/usr/bin/env bash
set -euo pipefail

# ===========================================================
# Arranca el recetario SIN Docker: backend Flask + SQLite
# (el backend también sirve el frontend, todo en un proceso).
#
# Uso:
#   ./script.sh
#
# Pensado para Raspberry Pi: nada de contenedores, solo un
# entorno virtual de Python. La base de datos es un único
# fichero (SQLite), sin servicios adicionales.
# ===========================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV_DIR="$SCRIPT_DIR/.venv"

# -----------------------------------------------------------
# 1. Entorno virtual de Python + dependencias
# -----------------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
    echo "✘ Python 3 no está instalado." >&2
    echo "  Instálalo con: sudo apt-get install python3 python3-venv python3-pip" >&2
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "→ Creando entorno virtual de Python en .venv..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "→ Comprobando dependencias de Python..."
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

# -----------------------------------------------------------
# 2. Base de datos SQL (crea las tablas si no existen)
# -----------------------------------------------------------

export DB_PATH="${DB_PATH:-$SCRIPT_DIR/data/recetario.db}"

echo "→ Preparando base de datos..."
(cd "$BACKEND_DIR" && python3 set_up.py)

# -----------------------------------------------------------
# 3. Backend Flask (sirve también el frontend)
# -----------------------------------------------------------

export FRONTEND_FOLDER="$FRONTEND_DIR"
export FLASK_DEBUG="${FLASK_DEBUG:-0}"
export PORT="${PORT:-80}"

IP_LOCAL="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo ""
echo "============================================================"
echo " Recetario disponible en:"
echo "   http://localhost:${PORT}"
if [ -n "$IP_LOCAL" ]; then
    echo "   http://${IP_LOCAL}:${PORT}   (desde otros dispositivos de la red)"
fi
echo ""
echo " Datos guardados en: $DB_PATH"
echo " Ctrl+C para detenerlo."
echo "============================================================"
echo ""

cd "$BACKEND_DIR"
python3 main.py