#!/usr/bin/env bash
set -euo pipefail

# ===========================================================
# Arranca el recetario SIN Docker: Redis + backend Flask
# (el backend también sirve el frontend, todo en un proceso).
#
# Uso:
#   ./script.sh
#
# Pensado para Raspberry Pi: nada de contenedores, solo un
# entorno virtual de Python y redis-server instalado en el
# propio sistema.
# ===========================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV_DIR="$SCRIPT_DIR/.venv"
REDIS_DATA_DIR="$SCRIPT_DIR/redis-data"

export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6379}"

STARTED_REDIS=0

cleanup() {
    
    if [ "${CLEANUP_DONE:-0}" = "1" ]; then
        return
    fi
    CLEANUP_DONE=1

    if [ "$STARTED_REDIS" = "1" ]; then
        echo ""
        echo "Deteniendo redis-server (con guardado a disco) ..."
        redis-cli -p "$REDIS_PORT" shutdown save >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

# -----------------------------------------------------------
# 1. Redis
# -----------------------------------------------------------

if command -v redis-cli >/dev/null 2>&1 && redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
    echo "✔ Redis ya está corriendo (lo reutilizo, no lo toco)."
    echo "  Sus datos persisten según su propia configuración"
    echo "  (si es el servicio del sistema, normalmente en /var/lib/redis)."
else
    if ! command -v redis-server >/dev/null 2>&1; then
        echo "→ redis-server no está instalado. Instalando (pedirá tu contraseña de sudo)..."
        sudo apt-get update
        sudo apt-get install -y redis-server
    fi

    mkdir -p "$REDIS_DATA_DIR"

    echo "→ Arrancando redis-server con persistencia en disco..."
    # - RDB: además de guardar cada 5 min si ha habido cambios, forzamos
    #   un guardado en el cleanup() de abajo al parar el script.
    # - AOF (appendonly): registra cada escritura en un log; con
    #   appendfsync everysec, en el peor caso (un corte de luz brusco en
    #   la Raspberry) solo se perdería el último segundo de cambios.
    # Con esto los datos sobreviven tanto a un "Ctrl+C" normal como a
    # un apagón, y quedan guardados en: redis-data/ (dentro del proyecto).
    redis-server \
        --daemonize yes \
        --port "$REDIS_PORT" \
        --dir "$REDIS_DATA_DIR" \
        --dbfilename dump.rdb \
        --save 300 1 \
        --save 60 100 \
        --appendonly yes \
        --appendfsync everysec \
        --appendfilename appendonly.aof

    STARTED_REDIS=1

    sleep 1
    if ! redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
        echo "✘ No se pudo arrancar Redis." >&2
        exit 1
    fi

    echo "  Datos guardados de forma permanente en: $REDIS_DATA_DIR"
fi

# -----------------------------------------------------------
# 2. Entorno virtual de Python + dependencias
# -----------------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
    echo "✘ Python 3 no está instalado." >&2
    echo "  Instálalo con: sudo apt-get install python3 python3-venv python3-pip" >&2
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "→ Creando entorno virtual de Python en backend/venv..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "→ Comprobando dependencias de Python..."
pip install --quiet --upgrade pip
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

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
echo " Ctrl+C para detenerlo."
echo "============================================================"
echo ""

cd "$BACKEND_DIR"
python3 main.py