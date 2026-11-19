#!/bin/sh
# Copia puntual para cron: no arranca la app ni instala dependencias.
set -eu
umask 077
DEPLOY_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(dirname "$DEPLOY_DIR")
CONFIG_FILE=${RECETARIO_ENV:-${HOME:?}/.config/recetario/recetario.env}
[ -r "$CONFIG_FILE" ] || { echo "ERROR: configuración no legible: $CONFIG_FILE" >&2; exit 1; }
set -a
. "$CONFIG_FILE"
set +a
VENV_DIR=${VENV_DIR:-$REPO_DIR/.venv}
[ -x "$VENV_DIR/bin/python" ] || { echo 'ERROR: ejecuta despliegue_raspberry.sh install primero.' >&2; exit 1; }
: "${DB_PATH:?Configura DB_PATH en recetario.env}"
: "${BACKUP_DIR:?Configura BACKUP_DIR en recetario.env}"
exec "$VENV_DIR/bin/python" "$REPO_DIR/backend/manage.py" backup --label weekly
