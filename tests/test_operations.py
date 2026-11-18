"""Seguridad y operaciones: cada base vive en TemporaryDirectory."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import backup
import database as db
import set_up
from flask import Flask
from security import install
from werkzeug.security import generate_password_hash


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous = db.DB_PATH
        db.DB_PATH = str(self.root / 'active.db')
        db._ready = False
        self.env = patch.dict(os.environ, {'BACKUP_DIR': str(self.root / 'backups')})
        self.env.start()
        set_up.initialize()
        self.recipe = db.create_recipe('Actual', [{'name': 'Arroz', 'qty': 2}], notes='No perder', preparation=['Cocer'])

    def tearDown(self):
        db.DB_PATH = self.previous
        db._ready = False
        self.env.stop()
        self.temp.cleanup()

    def test_missing_never_creates_even_after_ready(self):
        missing = self.root / 'absent.db'
        db.DB_PATH = str(missing)
        for ready in (True, False):
            db._ready = ready
            with self.assertRaises(FileNotFoundError):
                db.get_all_recipes()
            self.assertFalse(missing.exists())

    def test_empty_future_and_incomplete_rejected(self):
        for name, sql in [('empty', ''), ('future', 'PRAGMA user_version=999'),
                          ('incomplete', 'PRAGMA user_version=4')]:
            db.DB_PATH = str(self.root / (name + '.db'))
            with closing(sqlite3.connect(db.DB_PATH)) as conn:
                conn.executescript(sql)
            db._ready = False
            with self.assertRaises(RuntimeError):
                db._ensure_ready()
            with self.assertRaises(RuntimeError):
                set_up.create_tables()

    def test_init_refuses_existing(self):
        with self.assertRaises(FileExistsError):
            set_up.initialize()
        self.assertEqual(db.get_recipe(self.recipe['id']), self.recipe)

    def test_wal_backup_and_explicit_restore_preserve_current(self):
        with closing(sqlite3.connect(db.DB_PATH)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute("UPDATE recipes SET notes='Última escritura WAL'")
            writer.commit()
            saved = backup.backup(db.DB_PATH, self.root / 'backups')
            self.assertEqual(backup.verify(saved)['recipes'], 1)
            with closing(backup.connect_existing(saved, True)) as conn:
                self.assertEqual(conn.execute('SELECT notes FROM recipes').fetchone()[0], 'Última escritura WAL')
        db.create_recipe('Nueva', [{'name': 'Sal'}])
        with self.assertRaises(ValueError):
            backup.restore(saved, db.DB_PATH, self.root / 'backups')
        before = backup.restore(saved, db.DB_PATH, self.root / 'backups', stopped=True, confirm=db.DB_PATH)
        self.assertEqual(backup.verify(before)['recipes'], 2)
        self.assertEqual(backup.verify(db.DB_PATH)['recipes'], 1)
        db._ready = False
        self.assertEqual(db.get_recipe(self.recipe['id'])['notes'], 'Última escritura WAL')

    def test_corrupt_backup_cannot_restore_or_prune_last_valid(self):
        directory = self.root / 'backups'
        for _ in range(3):
            saved = backup.backup(db.DB_PATH, directory, retain=0)
        self.assertEqual(len(list(directory.glob('*.sqlite3'))), 1)
        corrupt = directory / 'corrupt.sqlite3'
        corrupt.write_bytes(b'not sqlite')
        with self.assertRaises(sqlite3.Error):
            backup.restore(corrupt, db.DB_PATH, directory, stopped=True, confirm=db.DB_PATH)
        self.assertEqual(db.get_recipe(self.recipe['id']), self.recipe)
        self.assertTrue(saved.exists())

    def legacy(self):
        path = self.root / 'legacy.db'
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript('''
            CREATE TABLE recipes(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE ingredients(id INTEGER PRIMARY KEY, recipe_id INTEGER, position INTEGER, name TEXT, qty REAL, unit TEXT);
            CREATE TABLE menu(day TEXT PRIMARY KEY, recipe_id INTEGER);
            INSERT INTO recipes VALUES(25, 'Antigua');
            INSERT INTO ingredients VALUES(67,25,0,'ARROZ',100,'g');
            INSERT INTO menu VALUES('lunes',25);
            PRAGMA user_version=1;
            ''')
        db.DB_PATH = str(path)
        db._ready = False
        return path

    def test_v1_migration_preserves_ids_references_and_backup(self):
        self.legacy()
        with self.assertRaises(RuntimeError):
            db.get_all_recipes()
        set_up.create_tables()
        self.assertEqual(db.get_recipe(25)['name'], 'Antigua')
        with db.connection() as conn:
            self.assertEqual(conn.execute('SELECT id FROM ingredients').fetchone()[0], 67)
            self.assertEqual(conn.execute("SELECT recipe_id FROM menu WHERE day='lunes' AND meal='comida'").fetchone()[0], 25)
        old = next((self.root / 'backups').glob('recetario-before-migration-*.sqlite3'))
        self.assertEqual(backup.verify(old)['version'], 1)

    def test_migration_failure_rolls_back_ddl_and_rows(self):
        self.legacy()
        with patch.object(set_up, '_upgrade_columns', side_effect=RuntimeError('simulated failure')):
            with self.assertRaises(RuntimeError):
                set_up.create_tables()
        with closing(backup.connect_existing(db.DB_PATH)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertNotIn('type', {r[1] for r in conn.execute('PRAGMA table_info(recipes)')})
            self.assertNotIn('meal', {r[1] for r in conn.execute('PRAGMA table_info(menu)')})
            self.assertEqual(conn.execute('SELECT recipe_id FROM menu').fetchone()[0], 25)

    def test_backup_failure_prevents_migration(self):
        self.legacy()
        with patch('backup.backup', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                set_up.create_tables()
        self.assertEqual(backup.verify(db.DB_PATH)['version'], 1)

    def test_backup_rejects_directory_inside_repository(self):
        root = Path(__file__).resolve().parents[1]
        with self.assertRaises(ValueError):
            backup.backup(db.DB_PATH, root / 'unsafe-backups')
        self.assertFalse((root / 'unsafe-backups').exists())

    def test_cli_info_is_read_only_and_requires_explicit_path(self):
        script = Path(__file__).resolve().parents[1] / 'backend/manage.py'
        result = subprocess.run([sys.executable, str(script), '--db', db.DB_PATH, 'info'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['recipes'], 1)
        result = subprocess.run([sys.executable, str(script), '--db', str(self.root / 'missing.db'), 'info'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'missing.db').exists())

    def auth_app(self, enabled=True):
        app = Flask('test')
        auth = self.root / 'auth.json'
        auth.write_text(json.dumps({'secret_key': 'x' * 64,
                         'password_hash': generate_password_hash('test password', method='pbkdf2:sha256:600000')}))
        with patch.dict(os.environ, {'AUTH_CONFIG': str(auth) if enabled else ''}):
            install(app)
        @app.route('/write', methods=['POST', 'PUT', 'PATCH', 'DELETE'])
        def write():
            return {'ok': True}
        return app.test_client()

    def test_auth_sessions_csrf_origins_logout(self):
        client = self.auth_app()
        headers = {'X-Recetario-Request': '1'}
        self.assertEqual(client.post('/write', headers=headers).status_code, 401)
        with patch('security.time.monotonic', return_value=100):
            self.assertEqual(client.post('/auth/login', json={'password': 'wrong'}, headers=headers).status_code, 401)
        with patch('security.time.monotonic', return_value=200):
            response = client.post('/auth/login', json={'password': 'test password'}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', response.headers['Set-Cookie'])
        token = client.get('/auth/status').json['csrf']
        self.assertEqual(client.post('/write', headers=headers).status_code, 403)
        headers['X-CSRF-Token'] = token
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            self.assertEqual(client.open('/write', method=method, headers=headers).status_code, 200)
        self.assertEqual(client.post('/write', headers=dict(headers, Origin='https://evil.example')).status_code, 403)
        self.assertEqual(client.post('/auth/logout', headers=headers).status_code, 200)
        self.assertEqual(client.post('/write', headers=headers).status_code, 401)

    def test_disabled_auth_and_external_forms(self):
        client = self.auth_app(False)
        self.assertFalse(client.get('/auth/status').json['enabled'])
        self.assertEqual(client.post('/write').status_code, 200)
        self.assertEqual(client.post('/write', headers={'Origin': 'http://evil.example'}).status_code, 403)

    def test_first_deployment_copies_latest_25_and_refuses_overwrite(self):
        for index in range(24):
            db.create_recipe(f'Receta {index}', [{'name': 'Sal'}], notes=f'Nota {index}')
        target = self.root / 'external' / 'recetario.db'
        script = Path(__file__).resolve().parents[1] / 'deploy/protect_existing.py'
        command = [sys.executable, str(script), '--source', db.DB_PATH, '--target', str(target),
                   '--backup-dir', str(self.root / 'external-backups'), '--writers-stopped']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(backup.verify(target)['recipes'], 25)
        self.assertEqual(backup.verify(db.DB_PATH)['recipes'], 25)
        with closing(backup.connect_existing(target, True)) as conn:
            self.assertEqual(conn.execute('SELECT notes FROM recipes WHERE id=25').fetchone()[0], 'Nota 23')
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(backup.verify(target)['recipes'], 25)

    def test_deployment_paths_ports_and_no_database_in_image(self):
        root = Path(__file__).resolve().parents[1]
        compose = (root / 'docker-compose.yaml').read_text()
        self.assertIn('8000:8000', compose)
        self.assertIn('./backend/data:/app/data', compose)
        self.assertIn('DB_PATH: /app/data/recetario.db', compose)
        script = (root / 'script.sh').read_text()
        self.assertIn('${PORT:-80}', script)
        self.assertIn('$SCRIPT_DIR/data/recetario.db', script)
        self.assertIn('$BACKEND_DIR/requirements.txt', script)
        self.assertIn('data/', (root / 'backend/.dockerignore').read_text())
