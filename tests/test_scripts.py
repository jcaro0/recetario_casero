"""Pruebas de los lanzadores sin arrancar Docker ni acceder a bases personales."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.calls = self.root / 'calls.jsonl'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, CALLS=str(self.calls), PATH=str(self.bin) + os.pathsep + os.environ['PATH'])

    def tearDown(self):
        self.temp.cleanup()

    def fake(self, name, code):
        path = self.bin / name
        path.write_text('#!' + sys.executable + '\n' + code)
        path.chmod(0o700)
        return path

    def run_script(self, script, *arguments):
        return subprocess.run(['/bin/bash', str(REPO / script), *arguments], cwd=self.root,
                              env=self.env, capture_output=True, text=True)

    def recorded(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def prepare_docker(self):
        self.fake('docker', '''import json, os, sys
with open(os.environ['CALLS'], 'a') as stream:
    stream.write(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')
if 'run' in sys.argv and os.environ.get('FAIL_PREFLIGHT') == '1':
    sys.exit(1)
''')

    def test_docker_start_checks_base_before_up_from_another_directory(self):
        self.prepare_docker()
        result = self.run_script('despliegue_docker.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.recorded()
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[1]['args'][-2:], ['build', 'backend'])
        self.assertEqual(calls[2]['args'][-5:], ['backend', 'python', 'main.py', '--check-db', '--init-if-missing'])
        self.assertEqual(calls[3]['args'][-4:], ['up', '-d', '--no-deps', 'backend'])
        for call in calls[1:]:
            self.assertEqual(call['cwd'], str(REPO))
            self.assertIn(str(REPO / 'docker-compose.yaml'), call['args'])
            self.assertFalse({'init', 'migrate', 'down'} & set(call['args']))

    def test_docker_failed_database_check_never_starts_or_removes_volumes(self):
        self.prepare_docker()
        self.env['FAIL_PREFLIGHT'] = '1'
        result = self.run_script('despliegue_docker.sh')
        self.assertNotEqual(result.returncode, 0)
        calls = self.recorded()
        self.assertEqual(len(calls), 3)
        self.assertFalse(any('up' in call['args'] or 'down' in call['args'] for call in calls))

    def test_scripts_help_and_invalid_arguments_have_no_side_effects(self):
        for name in ['despliegue_docker.sh', 'despliegue_raspberry.sh', 'ejecutar_test.sh']:
            with self.subTest(script=name):
                result = self.run_script(name, '--help')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Uso:', result.stdout)
                self.assertNotEqual(self.run_script(name, 'incorrecto').returncode, 0)
                self.assertNotEqual(self.run_script(name, 'start', 'extra').returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_test_runner_isolates_environment_and_propagates_failure(self):
        # El intérprete simulado evita recursión al probar el propio lanzador.
        interpreter = self.fake('test-python', '''import json, os, sys
if '-c' in sys.argv:
    sys.exit(0)
with open(os.environ['CALLS'], 'a') as stream:
    stream.write(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd(),
                            'db': os.environ['DB_PATH'], 'backup': os.environ['BACKUP_DIR'],
                            'config': os.environ.get('RECETARIO_ENV'),
                            'days': os.environ.get('MENU_DAYS'),
                            'pythonpath': os.environ['PYTHONPATH']}) + '\\n')
sys.exit(7)
''')
        config = self.root / 'no-source.env'
        config.write_text('exit 99\n')
        self.env.update(TEST_PYTHON=str(interpreter), DB_PATH='/no-usar/personal.db',
                        BACKUP_DIR='/no-usar/backups', RECETARIO_ENV=str(config), MENU_DAYS='domingo',
                        TEST_RESULTS_DIR=str(self.root / 'results'))
        result = self.run_script('ejecutar_test.sh', 'all')
        self.assertEqual(result.returncode, 7, result.stderr)
        calls = self.recorded()
        self.assertEqual(len(calls), 1)  # Un fallo de backend impide ejecutar los demás.
        call = calls[0]
        self.assertEqual(call['cwd'], str(REPO))
        self.assertEqual(call['pythonpath'], str(REPO / 'backend'))
        self.assertEqual(call['config'], '')
        self.assertIsNone(call['days'])
        self.assertNotEqual(call['db'], self.env['DB_PATH'])
        self.assertNotEqual(call['backup'], self.env['BACKUP_DIR'])
        self.assertTrue(Path(call['db']).is_absolute())
        self.assertEqual(Path(call['db']).parent, Path(call['backup']).parent)
        self.assertFalse(Path(call['db']).parent.exists())  # Limpieza incluso tras fallar.

    def test_systemd_uses_raspberry_launcher(self):
        service = (REPO / 'deploy/recetario.service').read_text()
        self.assertIn('ExecStart=/home/pi/recetario/despliegue_raspberry.sh start', service)
        self.assertNotIn('/script.sh', service)
        self.assertFalse((REPO / 'script.sh').exists())


if __name__ == '__main__':
    unittest.main()
