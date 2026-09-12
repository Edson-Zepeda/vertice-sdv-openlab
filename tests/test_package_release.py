"""Release safety tests with isolated tracked-file fixtures; no real repository modified."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('packager_under_test', ROOT / 'scripts/package_release.py')
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='entrega-aislada-', dir=ROOT / 'tmp')
        self.base = Path(self.temporary.name).resolve()
        self.assertTrue(self.base.is_relative_to(ROOT / 'tmp'))
        self.source = self.base / 'Vértice fuente con espacios'
        self.source.mkdir()
        self.data = {name: ('fixture ' + name).encode() for name in packager.REQUIRED}
        self.data['project.json'] = b'{"version":"1.0.0"}'
        self.data['web/docs/VerticeSDV_Informe.pdf'] = self.data['docs/VerticeSDV_Informe.pdf']
        copies = []
        for name in ['__init__.py', 'graph.py', 'dijkstra.py', 'codec.py']:
            body = self.data[f'vertice/{name}']
            self.data[f'web/python/vertice/{name}'] = body
            copies.append({'name': name, 'sha256': packager.sha(body)})
        self.data['web/python/manifest.json'] = json.dumps({'files': copies}).encode()
        for kind, names in [('fonts', ['web/fonts/Manrope-OFL.txt', 'web/fonts/DMSans-OFL.txt']),
                            ('pyodide', ['web/vendor/pyodide/LICENSE', 'web/vendor/pyodide/CPYTHON-LICENSE'])]:
            self.data[f'evidence/dependencies/{kind}.json'] = json.dumps({'files': [
                {'path': name, 'bytes': len(self.data[name]), 'sha256': packager.sha(self.data[name])} for name in names]}).encode()
        self.dirty = False
        self.commit_data = self.data.copy()
        self.write_source()

    def tearDown(self):
        self.assertTrue(self.base.resolve().is_relative_to((ROOT / 'tmp').resolve()))
        self.temporary.cleanup()

    def write_source(self):
        for name, data in self.data.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def fake_git(self, *args):
        if args == ('status', '--porcelain'):
            return b' M README.md' if self.dirty else b''
        if args == ('ls-files', '-z'):
            return b'\0'.join(name.encode() for name in sorted(self.data)) + b'\0'
        if args == ('rev-parse', 'HEAD'):
            return b'a' * 40
        if args == ('show', '-s', '--format=%ct', 'HEAD'):
            return b'1726000001'
        if len(args) == 2 and args[0] == 'show' and args[1].startswith('HEAD:'):
            return self.commit_data[args[1][5:]]
        raise AssertionError(args)

    def package(self, output=None, *extra):
        output = output or self.base / 'Entrega.zip'
        with patch.object(packager, 'ROOT', self.source), patch.object(packager, 'git', self.fake_git), \
                patch('sys.argv', ['package_release.py', '--output', str(output), *extra]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            packager.main()
        return output

    def test_repeatable_zip_and_unicode_filename(self):
        first = self.package(self.base / 'Entrega Vértice.zip')
        second = self.package(self.base / 'Segundo.zip')
        self.assertEqual(first.read_bytes(), second.read_bytes())
        expected = hashlib.sha256(first.read_bytes()).hexdigest()
        self.assertEqual(first.with_suffix('.sha256').read_text(encoding='utf8'), f'{expected}  Entrega Vértice.zip\n')
        self.assertEqual(json.loads(first.with_suffix('.receipt.json').read_text(encoding='utf8'))['sha256'], expected)
        with zipfile.ZipFile(first) as archive:
            self.assertTrue(all(entry.create_system == 3 for entry in archive.infolist()))
            self.assertTrue(all(entry.date_time[-1] % 2 == 0 for entry in archive.infolist()))
            self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
            self.assertEqual(archive.read('VerticeSDV/README.md'), self.data['README.md'])

    def test_output_cannot_overwrite_source_or_write_inside_source(self):
        original = (self.source / 'README.md').read_bytes()
        for target in [self.source / 'README.md', self.source / 'nested/output.zip']:
            with self.subTest(target=str(target)), self.assertRaises(SystemExit) as result:
                self.package(target)
            self.assertEqual(result.exception.code, 2)
        self.assertEqual((self.source / 'README.md').read_bytes(), original)
        self.assertFalse((self.source / 'nested').exists())

    def test_failed_verification_preserves_existing_release(self):
        output = self.base / 'Entrega.zip'
        output.write_bytes(b'previous release')
        checksum = output.with_suffix('.sha256')
        checksum.write_bytes(b'previous checksum')
        with patch.object(packager, 'verify_archive', side_effect=ValueError('injected CRC failure')):
            with self.assertRaisesRegex(ValueError, 'injected CRC'):
                self.package(output)
        self.assertEqual(output.read_bytes(), b'previous release')
        self.assertEqual(checksum.read_bytes(), b'previous checksum')
        self.assertFalse(list(self.base.glob('.vertice-package-*')))

    def test_required_license_and_case_collision_are_rejected(self):
        self.data.pop('LICENSE')
        with self.assertRaises(SystemExit):
            self.package()
        self.data['LICENSE'] = b'license'
        self.data['readme.md'] = b'collision'
        with self.assertRaises(SystemExit):
            self.package()
        self.assertFalse((self.base / 'Entrega.zip').exists())

    def test_private_traversal_and_windows_ambiguous_paths_are_rejected(self):
        for name in ['../outside', '/absolute', 'C:/outside', 'a\\b', 'a//b', 'a/./b',
                     'private/key.txt', '.env', '.env.production', '.git/config', 'tmp/file',
                     'web/CON.txt', 'web/COM¹.txt', 'web/name.', 'web/name ', 'web/name?.txt', 'web/name*.txt',
                     'web/<name>', 'media/render/silent.mp4', 'web/id_rsa']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                packager.validate_name(name)
        self.assertEqual(str(packager.validate_name('docs/Vértice.md')), 'docs/Vértice.md')

    def test_dependency_hash_and_web_mirror_are_checked(self):
        damaged = self.data.copy()
        damaged['web/vendor/pyodide/LICENSE'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'Dependencia distinta'):
            packager.verify_contents(damaged)
        damaged = self.data.copy()
        damaged['web/python/vertice/graph.py'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'núcleo web desactualizada'):
            packager.verify_contents(damaged)
        damaged = self.data.copy()
        damaged['web/docs/VerticeSDV_Informe.pdf'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'informe PDF'):
            packager.verify_contents(damaged)

    def test_dirty_requires_explicit_flag_and_never_claims_ready(self):
        self.dirty = True
        with self.assertRaises(SystemExit):
            self.package()
        output = self.package(None, '--allow-dirty')
        with zipfile.ZipFile(output) as archive:
            manifest = json.loads(archive.read('VerticeSDV/MANIFEST.json'))
        self.assertTrue(manifest['source_dirty'])
        self.assertFalse(manifest['release_ready'])

    def test_clean_working_bytes_must_match_commit(self):
        (self.source / 'README.md').write_bytes(b'changed after status')
        with self.assertRaisesRegex(ValueError, 'Bytes difieren'):
            self.package()
        self.assertFalse((self.base / 'Entrega.zip').exists())

    def test_extracted_snapshot_without_git_gets_actionable_error(self):
        with patch.object(self, 'fake_git', side_effect=subprocess.CalledProcessError(128, 'git')):
            with self.assertRaises(SystemExit) as result:
                self.package()
        self.assertEqual(result.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
