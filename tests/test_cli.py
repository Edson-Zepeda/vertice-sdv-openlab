"""Exercise the actual CLI in a clean source snapshot, without site-packages."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI_OBSERVATIONS = []
SNAPSHOT_MANIFEST = {}


class CleanCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='Vértice limpio con espacios-', dir=ROOT / 'tmp')
        cls.snapshot = Path(cls.temporary.name)
        shutil.copytree(ROOT / 'vertice', cls.snapshot / 'vertice', ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('server.py', 'Iniciar.cmd'):
            shutil.copy2(ROOT / name, cls.snapshot / name)
        for path in [*sorted((cls.snapshot / 'vertice').glob('*.py')), cls.snapshot / 'server.py', cls.snapshot / 'Iniciar.cmd']:
            relative = path.relative_to(cls.snapshot).as_posix()
            source_digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            copied_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if source_digest != copied_digest:
                raise AssertionError('Clean snapshot differs from source')
            SNAPSHOT_MANIFEST[relative] = copied_digest

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.case_directory = self.snapshot / self._testMethodName
        self.case_directory.mkdir()
        self.graph_file = self.case_directory / 'grafo español.json'

    def command(self, *arguments, input_bytes=None, expected=0, env_overrides=None):
        environment = os.environ.copy()
        for variable in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONSAFEPATH'):
            environment.pop(variable, None)
        if env_overrides:
            environment.update(env_overrides)
        result = subprocess.run([sys.executable, '-S', '-m', 'vertice.cli', *map(str, arguments)],
                                cwd=self.snapshot, env=environment, input=input_bytes,
                                capture_output=True, timeout=10)
        stdout = result.stdout.decode('utf-8', errors='backslashreplace')
        stderr = result.stderr.decode('utf-8', errors='backslashreplace')
        CLI_OBSERVATIONS.append({'test': self.id(), 'arguments': [str(arg).replace(str(self.snapshot), '<snapshot>')
                                                                  for arg in arguments],
                                 'returncode': result.returncode, 'stdout': stdout, 'stderr': stderr,
                                 'stdin_bytes': len(input_bytes) if input_bytes is not None else None,
                                 'site_packages_disabled': True})
        self.assertEqual(result.returncode, expected, f'{stdout}\n{stderr}')
        self.assertNotIn('Traceback', stderr)
        return stdout, stderr

    def seed_graph(self):
        graph = {'schema_version': 1, 'directed': False,
                 'nodes': [{'id': 'A', 'label': 'Café 🚗 你好', 'x': 0, 'y': 0},
                           {'id': 'B', 'label': 'Destino', 'x': 1, 'y': 1}],
                 'edges': [{'id': 'ab', 'source': 'A', 'target': 'B', 'weight': '0.125'}]}
        self.graph_file.write_text(json.dumps(graph, ensure_ascii=False), encoding='utf-8')
        return graph

    def test_documented_create_edit_validate_and_solve_sequence(self):
        self.command('create', '--output', self.graph_file)
        self.command('edit', self.graph_file, 'add-node', 'A', '--label', 'Inicio', '--x', '100', '--y', '150',
                     '--output', self.graph_file, '--overwrite')
        self.command('edit', self.graph_file, 'add-node', 'B', '--label', 'Destino', '--x', '400', '--y', '150',
                     '--output', self.graph_file, '--overwrite')
        self.command('edit', self.graph_file, 'add-edge', 'ab', '--source', 'A', '--target', 'B', '--weight', '0.125',
                     '--output', self.graph_file, '--overwrite')
        stdout, _ = self.command('validate', self.graph_file)
        self.assertIn('2 nodos, 1 conexiones', stdout)
        stdout, _ = self.command('solve', self.graph_file, '--source', 'A', '--target', 'B', '--json', '--trace')
        result = json.loads(stdout)
        self.assertEqual(result['cost'], '0.125')
        self.assertEqual(result['path'], ['A', 'B'])
        self.assertTrue(result['trace'])

    def test_updates_and_removals_change_subsequent_searches(self):
        self.seed_graph()
        self.command('edit', self.graph_file, 'update-node', 'A', '--label', 'Salida nueva', '--output', self.graph_file, '--overwrite')
        self.command('edit', self.graph_file, 'update-edge', 'ab', '--weight', '0', '--output', self.graph_file, '--overwrite')
        stdout, _ = self.command('solve', self.graph_file, '-s', 'A', '-t', 'B', '--json')
        self.assertEqual(json.loads(stdout)['cost'], '0')
        self.command('edit', self.graph_file, 'remove-edge', 'ab', '--output', self.graph_file, '--overwrite')
        stdout, _ = self.command('solve', self.graph_file, '-s', 'A', '-t', 'B', '--json')
        self.assertEqual(json.loads(stdout)['status'], 'no_path')
        self.command('edit', self.graph_file, 'remove-node', 'B', '--output', self.graph_file, '--overwrite')
        self.command('solve', self.graph_file, '-s', 'A', '-t', 'B', '--json', expected=2)

    def test_existing_output_is_preserved_without_explicit_overwrite(self):
        self.seed_graph()
        before = self.graph_file.read_bytes()
        self.command('create', '--output', self.graph_file, expected=2)
        self.assertEqual(self.graph_file.read_bytes(), before)
        self.command('edit', self.graph_file, 'update-edge', 'ab', '--weight', '9', '--output', self.graph_file, expected=2)
        self.assertEqual(self.graph_file.read_bytes(), before)

    def test_invalid_edit_never_replaces_saved_graph(self):
        self.seed_graph()
        before = self.graph_file.read_bytes()
        self.command('edit', self.graph_file, 'update-edge', 'ab', '--weight', '-1',
                     '--output', self.graph_file, '--overwrite', expected=2)
        self.assertEqual(self.graph_file.read_bytes(), before)
        self.assertEqual(list(self.case_directory.glob('.vertice-*.tmp')), [])

    def test_missing_input_or_output_directory_is_controlled(self):
        self.command('validate', self.graph_file, expected=2)
        self.command('create', '--output', self.case_directory / 'missing' / 'graph.json', expected=2)
        self.assertEqual(list(self.case_directory.glob('.vertice-*.tmp')), [])

    def test_no_path_is_valid_zero_exit_and_never_zero_cost(self):
        self.seed_graph()
        graph = json.loads(self.graph_file.read_text(encoding='utf-8'))
        graph['edges'] = []
        self.graph_file.write_text(json.dumps(graph), encoding='utf-8')
        stdout, _ = self.command('solve', self.graph_file, '-s', 'A', '-t', 'B', '--json')
        result = json.loads(stdout)
        self.assertEqual((result['status'], result['path'], result['cost']), ('no_path', [], None))

    def test_human_readable_route_and_trace_flag(self):
        self.seed_graph()
        stdout, _ = self.command('solve', self.graph_file, '-s', 'A', '-t', 'B')
        self.assertIn('A → B', stdout)
        self.assertIn('Costo: 0.125', stdout)
        stdout, _ = self.command('solve', self.graph_file, '-s', 'A', '-t', 'B', '--json')
        self.assertEqual(json.loads(stdout)['trace'], [])

    def test_stdin_preserves_utf8_under_windows_legacy_locale(self):
        graph = self.seed_graph()
        output = self.case_directory / 'copia desde entrada.json'
        # A redirected UTF-8 file must not be decoded as cp1252 on Windows.
        self.command('edit', '-', 'update-node', 'B', '--label', 'Destino actualizado', '--output', output,
                     input_bytes=json.dumps(graph, ensure_ascii=False).encode('utf-8'),
                     env_overrides={'PYTHONUTF8': '0', 'PYTHONIOENCODING': 'cp1252'})
        saved = json.loads(output.read_text(encoding='utf-8'))
        self.assertEqual(next(node for node in saved['nodes'] if node['id'] == 'A')['label'], graph['nodes'][0]['label'])

    def test_utf8_file_round_trip_and_directed_choice(self):
        original = self.seed_graph()
        output = self.case_directory / 'copia válida.json'
        self.command('edit', self.graph_file, 'update-node', 'B', '--x', '5', '--output', output)
        saved = json.loads(output.read_text(encoding='utf-8'))
        self.assertEqual(saved['nodes'][0]['label'], original['nodes'][0]['label'])
        self.assertEqual(saved['edges'][0]['weight'], '0.125')
        empty = self.case_directory / 'dirigido.json'
        self.command('create', '--directed', '--output', empty)
        self.assertIs(json.loads(empty.read_text())['directed'], True)

    def test_argument_errors_exit_two_without_traceback(self):
        self.command('solve', expected=2)
        self.command('invalid-command', expected=2)
        self.command('create', '--help')

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher requires Windows')
    def test_windows_launcher_check_in_spanish_path(self):
        result = subprocess.run(['cmd.exe', '/d', '/c', 'Iniciar.cmd', '--check'], cwd=self.snapshot,
                                capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        stdout = result.stdout.decode('utf-8', errors='backslashreplace')
        CLI_OBSERVATIONS.append({'test': self.id(), 'launcher': 'Iniciar.cmd --check',
                                 'returncode': result.returncode, 'stdout': stdout,
                                 'note': 'Launcher selects installed Python; version is printed in stdout'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('VERTICE', stdout)
        self.assertIn('listo', stdout)

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher requires Windows')
    def test_windows_launcher_propagates_occupied_port_failure(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen(1)
            port = occupied.getsockname()[1]
            result = subprocess.run(['cmd.exe', '/d', '/c', 'Iniciar.cmd', '--port', str(port), '--no-open'],
                                    cwd=self.snapshot, capture_output=True, timeout=10,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        CLI_OBSERVATIONS.append({'test': self.id(), 'launcher': 'Iniciar.cmd --port <occupied> --no-open',
                                 'returncode': result.returncode,
                                 'stderr': result.stderr.decode('utf-8', errors='backslashreplace')})
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'No se pudo iniciar', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
