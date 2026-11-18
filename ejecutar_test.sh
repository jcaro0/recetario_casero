#!/usr/bin/env bash
set -euo pipefail
umask 077
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_VENV_DIR="${TEST_VENV_DIR:-$SCRIPT_DIR/.venv-tests}"
fail() { echo "ERROR: $*" >&2; exit 1; }
usage() {
    cat <<'HELP'
Uso: ./ejecutar_test.sh [all|backend|startup|browser|install]
  all      Backend, arranque/reinicio con Waitress y navegador real (por defecto).
  backend  Pruebas de API, SQLite, migraciones y operaciones.
  startup  Arranque y reinicio de Raspberry con una base temporal y puerto efímero.
  browser  Recorridos de interfaz con Playwright y Chromium; capturas en tests/results.
  install  Instala las herramientas de desarrollo y Chromium en un entorno de pruebas.

Solo para desarrollo. No arranca Docker, no usa bases personales y no instala
nada al ejecutar pruebas. install usa .venv-tests (cambiable con TEST_VENV_DIR).
TEST_PYTHON permite utilizar otro intérprete preparado para las pruebas.
CHROMIUM_PATH permite utilizar un Chromium ya instalado en el ordenador.
HELP
}
[ "$#" -le 1 ] || { usage >&2; exit 1; }
TEST_SUITE="${1:-all}"
case "$TEST_SUITE" in
    -h|--help) usage; exit 0 ;;
    all|backend|startup|browser|install) ;;
    *) usage >&2; exit 1 ;;
esac
cd "$SCRIPT_DIR"
export TEST_RESULTS_DIR="${TEST_RESULTS_DIR:-$SCRIPT_DIR/tests/results}"
if [ "$TEST_SUITE" = install ]; then
    command -v python3 >/dev/null || fail 'Instala python3 y python3-venv en el ordenador de desarrollo.'
    [ -x "$TEST_VENV_DIR/bin/python" ] || python3 -m venv "$TEST_VENV_DIR"
    "$TEST_VENV_DIR/bin/python" -m pip install -r "$SCRIPT_DIR/backend/requirements.txt" playwright
    if [ -z "${CHROMIUM_PATH:-}" ]; then
        "$TEST_VENV_DIR/bin/python" -m playwright install chromium
    fi
    echo 'Herramientas de pruebas listas. Ejecuta ./ejecutar_test.sh'
    exit 0
fi
if [ -n "${TEST_PYTHON:-}" ]; then
    TEST_INTERPRETER="$TEST_PYTHON"
elif [ -x "$TEST_VENV_DIR/bin/python" ]; then
    TEST_INTERPRETER="$TEST_VENV_DIR/bin/python"
elif [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    TEST_INTERPRETER="$SCRIPT_DIR/.venv/bin/python"
else
    TEST_INTERPRETER=python3
fi
command -v "$TEST_INTERPRETER" >/dev/null || fail 'No se encuentra Python. Ejecuta ./ejecutar_test.sh install'
"$TEST_INTERPRETER" -c 'import flask, waitress' || fail 'Faltan dependencias de pruebas. Ejecuta ./ejecutar_test.sh install'
if [ "$TEST_SUITE" = all ] || [ "$TEST_SUITE" = browser ]; then
    "$TEST_INTERPRETER" -c 'import playwright.sync_api' || fail 'Falta Playwright. Ejecuta ./ejecutar_test.sh install'
fi

# Una base ausente dentro del temporal protege incluso de accesos accidentales
# al DB_PATH predeterminado. Cada prueba prepara su propia base de prueba.
TEST_TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/recetario-tests.XXXXXX")"
trap 'rm -rf -- "$TEST_TEMP_DIR"' EXIT
export DB_PATH="$TEST_TEMP_DIR/no-usar-base-real.db"
export BACKUP_DIR="$TEST_TEMP_DIR/backups"
export BACKUP_RETAIN=2
export RECETARIO_ENV=""
unset MENU_DAYS FRONTEND_FOLDER PORT VENV_DIR FLASK_DEBUG
export PYTHONPATH="$SCRIPT_DIR/backend"
mkdir -p "$TEST_RESULTS_DIR"
if [ "$TEST_SUITE" = all ] || [ "$TEST_SUITE" = backend ]; then
    "$TEST_INTERPRETER" -m unittest discover -s "$SCRIPT_DIR/tests" -v 2>&1 | tee "$TEST_RESULTS_DIR/backend.log"
fi
if [ "$TEST_SUITE" = all ] || [ "$TEST_SUITE" = startup ]; then
    "$TEST_INTERPRETER" "$SCRIPT_DIR/tests/smoke_startup.py" 2>&1 | tee "$TEST_RESULTS_DIR/startup.log"
fi
if [ "$TEST_SUITE" = all ] || [ "$TEST_SUITE" = browser ]; then
    "$TEST_INTERPRETER" "$SCRIPT_DIR/tests/browser_recipes.py" 2>&1 | tee "$TEST_RESULTS_DIR/browser.log"
fi
echo "Pruebas seleccionadas completadas correctamente. Resultados en $TEST_RESULTS_DIR"
