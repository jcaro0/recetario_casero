"""Un proceso WSGI pequeño para los dos entornos."""
import os
import sys
import database as db


def main():
    try:
        db._ensure_ready()
        from main import app
        from waitress import serve
        port = int(os.environ.get('PORT', '8000'))
        print(f'Recetario: DB_PATH={db.DB_PATH}; puerto={port}', flush=True)
        serve(app, host='0.0.0.0', port=port, threads=2,
              connection_limit=32, channel_timeout=30, max_request_body_size=1024 * 1024)
    except PermissionError:
        print('ERROR: sin permiso para escuchar. Para puerto 80 usa el servicio systemd con CAP_NET_BIND_SERVICE; no ejecutes Python como root.', file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f'ERROR al arrancar: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
