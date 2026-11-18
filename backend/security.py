"""Autenticación doméstica opcional; sesiones firmadas y CSRF en el backend."""
import hmac
import os
import secrets
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from flask import request, jsonify, session
from werkzeug.security import check_password_hash


def install(app):
    config_path = os.environ.get('AUTH_CONFIG')
    app.config['AUTH_ENABLED'] = bool(config_path)
    if config_path:
        import json
        config = json.loads(Path(config_path).read_text())
        if len(config.get('secret_key', '')) < 32 or not config.get('password_hash', '').startswith('pbkdf2:sha256:'):
            raise RuntimeError('AUTH_CONFIG requiere secret_key aleatoria y password_hash PBKDF2 SHA256.')
        app.secret_key = config['secret_key']
        app.config['AUTH_PASSWORD_HASH'] = config['password_hash']
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                      SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '0') == '1',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=1024 * 1024)
    # Una verificación simultánea como máximo: limita memoria/CPU en la Pi.
    import threading
    login_lock = threading.Lock()
    next_login = [0.0]

    @app.before_request
    def protect_writes():
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return
        # También protege instalaciones sin contraseña frente a formularios externos.
        origin = request.headers.get('Origin')
        if origin and (urlsplit(origin).netloc != request.host or urlsplit(origin).scheme != request.scheme):
            return jsonify(error='Origen no permitido'), 403
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return jsonify(error='Petición externa no permitida'), 403
        if not app.config['AUTH_ENABLED']:
            return
        if request.headers.get('X-Recetario-Request') != '1':
            return jsonify(error='Falta cabecera de protección CSRF'), 403
        if request.path == '/auth/login':
            return
        if not session.get('authenticated'):
            return jsonify(error='Inicia sesión en /login.html para modificar datos'), 401
        token = request.headers.get('X-CSRF-Token', '')
        if not token or not hmac.compare_digest(token, session.get('csrf', '')):
            return jsonify(error='Token CSRF incorrecto; vuelve a iniciar sesión'), 403

    @app.get('/auth/status')
    def status():
        return jsonify(enabled=app.config['AUTH_ENABLED'], authenticated=bool(session.get('authenticated')),
                       csrf=session.get('csrf'))

    @app.post('/auth/login')
    def login():
        if not app.config['AUTH_ENABLED']:
            return jsonify(error='La autenticación está desactivada'), 400
        if not login_lock.acquire(blocking=False):
            return jsonify(error='Espera unos segundos antes de reintentar'), 429
        try:
            if time.monotonic() < next_login[0]:
                return jsonify(error='Espera unos segundos antes de reintentar'), 429
            next_login[0] = time.monotonic() + 2
            password = (request.get_json(silent=True) or {}).get('password')
            if not isinstance(password, str) or len(password) > 1024 or not check_password_hash(app.config['AUTH_PASSWORD_HASH'], password):
                return jsonify(error='Contraseña incorrecta'), 401
            session.clear()
            session.permanent = True
            session['authenticated'] = True
            session['csrf'] = secrets.token_urlsafe(32)
            return jsonify(ok=True)
        finally:
            login_lock.release()

    @app.post('/auth/logout')
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.path.startswith('/auth/'):
            response.headers['Cache-Control'] = 'no-store'
        return response


if __name__ == '__main__':
    import getpass
    import json
    import sys
    from werkzeug.security import generate_password_hash
    path = Path(sys.argv[1])
    password = getpass.getpass('Nueva contraseña (12 caracteres mínimo): ')
    if len(password) < 12 or password != getpass.getpass('Repetir contraseña: '):
        raise SystemExit('Contraseña corta o confirmación distinta.')
    config = {'secret_key': secrets.token_hex(32),
              'password_hash': generate_password_hash(password, method='pbkdf2:sha256:600000')}
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(config, stream)
    print(f'Configuración creada en {path}. Activa AUTH_CONFIG con esa ruta y reinicia.')
