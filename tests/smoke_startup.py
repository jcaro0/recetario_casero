"""Arranca despliegue_raspberry.sh desde /tmp con SQLite temporal y Waitress real.
Requiere las dependencias del backend; abre exclusivamente un puerto efímero.
"""
import json
import os
from pathlib import Path
import socket
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

import database as db
import set_up


def run():
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db.DB_PATH = str(root / 'active.db')
        db._ready = False
        set_up.initialize()
        saved = db.save_recipe('Sobrevive al reinicio', [{'name': 'Sal'}])
        product_id = db.save_manual_product('Papel', 2, 'paquetes')
        db.check_manual_product(product_id, True)
        venv = root / 'venv'
        (venv / 'bin').mkdir(parents=True)
        (venv / 'bin/python').write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
        (venv / 'bin/python').chmod(0o700)
        (venv / 'recetario-requirements.txt').write_bytes((repo / 'backend/requirements.txt').read_bytes())
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, DB_PATH=db.DB_PATH, VENV_DIR=str(venv), PORT=str(port), RECETARIO_ENV='')
        def start():
            return subprocess.Popen(['bash', str(repo / 'despliegue_raspberry.sh')], cwd='/tmp', env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(2):
            process = start()
            try:
                deadline = time.monotonic() + 15
                while True:
                    if process.poll() is not None:
                        raise AssertionError(process.stdout.read())
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/recipes', timeout=1) as response:
                            assert json.load(response) == [saved]
                        with urlopen(f'http://127.0.0.1:{port}/shopping-list', timeout=1) as response:
                            assert json.load(response) == [dict(manual_id=product_id, name='Papel',
                                                               qty=2, unit='paquetes', checked=True)]
                        break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(.1)
            finally:
                process.terminate()
                process.communicate(timeout=5)
        env['DB_PATH'] = str(root / 'unexpected-missing.db')
        result = subprocess.run(['bash', str(repo / 'despliegue_raspberry.sh')], cwd='/tmp', env=env, capture_output=True, text=True)
        assert result.returncode != 0 and 'Base ausente' in result.stderr, result
        assert not Path(env['DB_PATH']).exists()
        print('OK: despliegue_raspberry.sh desde otro directorio, Waitress, persistencia tras reinicio y rechazo de base ausente')

if __name__ == '__main__':
    run()
