#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'HELP'
Uso: ./despliegue_docker.sh [start|build|stop|status|logs]
  start   Construye, comprueba la base existente y arranca en el puerto 8000.
  build   Construye la imagen sin arrancar ni modificar la base.
  stop    Detiene la aplicación conservando datos y volúmenes.
  status  Muestra el estado del servicio.
  logs    Sigue los registros (Ctrl+C para salir).

Sin argumento se utiliza start. Requiere Docker con Compose v2.
No inicializa ni migra bases automáticamente. Para una base pendiente de
migración, detén el servicio y sigue el procedimiento con respaldo del README.
HELP
}
[ "$#" -le 1 ] || { usage >&2; exit 1; }
case "${1:-start}" in
    -h|--help) usage; exit 0 ;;
    start|build|stop|status|logs) ;;
    *) usage >&2; exit 1 ;;
esac
command -v docker >/dev/null || { echo 'ERROR: instala Docker y su complemento Compose v2.' >&2; exit 1; }
docker compose version >/dev/null
cd "$SCRIPT_DIR"
compose() {
    docker compose --project-directory "$SCRIPT_DIR" -f "$SCRIPT_DIR/docker-compose.yaml" "$@"
}
case "${1:-start}" in
    start)
        compose build backend
        # Falla ante una base ausente o incompatible, sin crearla ni migrarla.
        compose run --rm --no-deps -T backend python -c 'import database; database._ensure_ready()'
        compose up -d --no-deps backend
        echo 'Recetario disponible en http://localhost:8000'
        ;;
    build) compose build backend ;;
    stop) compose stop backend ;;
    status) compose ps backend ;;
    logs) compose logs -f backend ;;
esac
