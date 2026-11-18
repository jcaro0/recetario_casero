#!/usr/bin/env bash
set -euo pipefail
umask 077
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" != 0 ] || fail 'Ejecuta como usuario normal. Para puerto 80 utiliza el servicio systemd documentado.'
# Archivo de shell opcional, externo al repositorio, solo de confianza.
if [ -n "${RECETARIO_ENV:-}" ]; then
    [ -r "$RECETARIO_ENV" ] || fail "No se puede leer $RECETARIO_ENV"
    set -a
    source "$RECETARIO_ENV"
    set +a
fi
VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/.venv}"
export PORT="${PORT:-80}"
export FRONTEND_FOLDER="${FRONTEND_FOLDER:-$SCRIPT_DIR/frontend}"
export FLASK_DEBUG="${FLASK_DEBUG:-0}"
# Conserva el valor histórico de script.sh, sin seleccionar la base de Docker.
export DB_PATH="${DB_PATH:-$SCRIPT_DIR/data/recetario.db}"
[[ "$DB_PATH" = /* ]] || fail 'DB_PATH debe ser absoluto.'
command -v python3 >/dev/null || fail 'Instala python3 y python3-venv.'
case "${1:-start}" in
    install)
        [ -x "$VENV_DIR/bin/python" ] || python3 -m venv "$VENV_DIR"
        "$VENV_DIR/bin/python" -m pip install -r "$BACKEND_DIR/requirements.txt"
        cp "$BACKEND_DIR/requirements.txt" "$VENV_DIR/recetario-requirements.txt"
        echo 'Dependencias listas. Configura DB_PATH antes de iniciar.'
        exit 0 ;;
    start) ;;
    *) fail 'Uso: script.sh [install|start]' ;;
esac
[ -x "$VENV_DIR/bin/python" ] || fail 'Ejecuta primero ./script.sh install'
cmp -s "$BACKEND_DIR/requirements.txt" "$VENV_DIR/recetario-requirements.txt" || fail 'Dependencias cambiadas: ejecuta ./script.sh install'
[ -f "$DB_PATH" ] || fail "Base ausente: $DB_PATH. Revisa la ruta; solo para una instalación NUEVA usa manage.py init."
cd "$BACKEND_DIR"
"$VENV_DIR/bin/python" -c 'import database; database._ensure_ready()'
echo "Recetario: base $DB_PATH; puerto $PORT; escucha en la red local."
exec "$VENV_DIR/bin/python" "$BACKEND_DIR/serve.py"
