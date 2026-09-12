"""Empaqueta archivos versionados, verifica integridad y reemplaza el ZIP atómicamente.

La fuente debe ser un clon Git. La salida se guarda fuera de ese clon.
La reproducibilidad binaria presupone los mismos archivos y versión de zlib.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'VerticeSDV'
REQUIRED = {
    'README.md', 'Iniciar.cmd', 'server.py', 'project.json', 'LICENSE', 'THIRD_PARTY.md',
    'vertice/__init__.py', 'vertice/graph.py', 'vertice/dijkstra.py', 'vertice/codec.py', 'vertice/cli.py',
    'web/index.html', 'web/proyecto.html', 'web/python/manifest.json',
    'docs/VerticeSDV_Informe.pdf', 'web/docs/VerticeSDV_Informe.pdf',
    'web/media/VerticeSDV_Demo.mp4', 'web/media/VerticeSDV.vtt', 'web/data/film.json',
    'evidence/dependencies/fonts.json', 'evidence/dependencies/pyodide.json',
    'web/fonts/Manrope-OFL.txt', 'web/fonts/DMSans-OFL.txt',
    'web/vendor/pyodide/LICENSE', 'web/vendor/pyodide/CPYTHON-LICENSE',
}
FORBIDDEN_PARTS = {'node_modules', '.venv', '__pycache__', 'tmp', '.git', 'private', '.ssh', '.aws'}
WINDOWS_RESERVED = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in '123456789¹²³'), *(f'lpt{i}' for i in '123456789¹²³')}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, stderr=subprocess.STDOUT)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_name(name):
    relative = PurePosixPath(name)
    if (not name or relative.is_absolute() or str(relative) != name or '..' in relative.parts or
            '\\' in name or any(c in '<>:"|?*' or ord(c) < 32 for c in name)):
        raise ValueError(f'Ruta inválida: {name!r}')
    for part in relative.parts:
        folded = part.casefold()
        if folded in FORBIDDEN_PARTS or folded.startswith('.env') or folded in {'id_rsa', 'id_ed25519'}:
            raise ValueError(f'Archivo privado o temporal versionado: {name!r}')
        if part.endswith((' ', '.')) or folded.split('.')[0] in WINDOWS_RESERVED:
            raise ValueError(f'Nombre no portable en Windows: {name!r}')
    if relative.parts[:2] == ('media', 'render'):
        raise ValueError(f'Render temporal versionado: {name!r}')
    return relative


def verify_contents(contents):
    for manifest_name in ('evidence/dependencies/fonts.json', 'evidence/dependencies/pyodide.json'):
        for item in json.loads(contents[manifest_name])['files']:
            name = item['path']
            validate_name(name)
            if name not in contents:
                raise ValueError(f'Dependencia no versionada: {name}')
            if len(contents[name]) != item['bytes'] or sha(contents[name]) != item['sha256']:
                raise ValueError(f'Dependencia distinta de su manifiesto: {name}')
    expected = {'__init__.py', 'graph.py', 'dijkstra.py', 'codec.py'}
    entries = json.loads(contents['web/python/manifest.json'])['files']
    if len(entries) != len(expected) or {e['name'] for e in entries} != expected:
        raise ValueError('Manifiesto del núcleo web incompleto o duplicado.')
    for item in entries:
        name = item['name']
        native, web = contents[f'vertice/{name}'], contents.get(f'web/python/vertice/{name}')
        if native != web or sha(native) != item['sha256']:
            raise ValueError(f'Copia del núcleo web desactualizada: {name}')
    if contents['docs/VerticeSDV_Informe.pdf'] != contents['web/docs/VerticeSDV_Informe.pdf']:
        raise ValueError('Las copias del informe PDF son distintas.')


def verify_archive(path, entries):
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f'CRC incorrecto: {bad}')
        expected_names = {f'{PREFIX}/{entry["path"]}' for entry in entries} | {f'{PREFIX}/MANIFEST.json'}
        if set(archive.namelist()) != expected_names or len(archive.namelist()) != len(expected_names):
            raise ValueError('Entradas duplicadas, incompletas o inesperadas en el ZIP.')
        stored = json.loads(archive.read(f'{PREFIX}/MANIFEST.json'))
        if stored['files'] != entries:
            raise ValueError('El manifiesto ZIP no coincide con los archivos recopilados.')
        for entry in entries:
            data = archive.read(f'{PREFIX}/{entry["path"]}')
            if len(data) != entry['bytes'] or sha(data) != entry['sha256']:
                raise ValueError(f'Hash incorrecto en el ZIP: {entry["path"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'VerticeSDV_Proyecto.zip')
    parser.add_argument('--allow-dirty', action='store_true', help='Solo revisión local; marca paquete no publicable')
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.is_relative_to(ROOT.resolve()):
        parser.error('La salida debe estar fuera del directorio fuente para proteger sus archivos.')
    if destination.suffix.lower() != '.zip':
        parser.error('La salida debe tener extensión .zip.')
    try:
        dirty = bool(git('status', '--porcelain').strip())
    except (OSError, subprocess.CalledProcessError):
        parser.error('Se necesita Git y un clon del repositorio. El ZIP extraído ya está listo para usarse.')
    if dirty and not args.allow_dirty:
        parser.error('La fuente debe estar versionada y sin cambios antes de empaquetar.')
    names = [value.decode('utf8') for value in git('ls-files', '-z').split(b'\0') if value]
    missing = REQUIRED - set(names)
    if missing:
        parser.error(f'Faltan entregables versionados: {sorted(missing)}')
    folded = [name.casefold() for name in names]
    if len(set(folded)) != len(folded) or 'manifest.json' in folded:
        parser.error('Hay nombres duplicados en Windows o un MANIFEST.json reservado.')
    revision = git('rev-parse', 'HEAD').decode().strip()
    stamp = int(git('show', '-s', '--format=%ct', 'HEAD').decode().strip())
    date = datetime.fromtimestamp(stamp, timezone.utc)
    if not 1980 <= date.year <= 2107:
        parser.error('La fecha del commit queda fuera del intervalo ZIP 1980–2107.')
    timestamp = (date.year, date.month, date.day, date.hour, date.minute, date.second // 2 * 2)
    entries, contents = [], {}
    for name in sorted(names):
        relative = validate_name(name)
        path = ROOT / Path(*relative.parts)
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError(f'Enlace fuera del paquete: {name!r}')
        data = path.read_bytes()
        if not dirty and git('show', f'HEAD:{name}') != data:
            raise ValueError(f'Bytes difieren del commit: {name}')
        contents[name] = data
        entries.append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
    verify_contents(contents)
    manifest = {'schema_version': 1, 'project': PREFIX, 'version': json.loads(contents['project.json'])['version'],
                'source_revision': revision, 'source_dirty': dirty, 'release_ready': not dirty,
                'timestamp': date.isoformat(), 'compression': {'method': 'deflate', 'level': 9, 'zlib': zlib.ZLIB_RUNTIME_VERSION},
                'files': entries}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_paths = []
    try:
        with tempfile.NamedTemporaryFile(prefix='.vertice-package-', suffix='.zip.tmp', dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
        temporary_paths.append(temporary)
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in [*contents.items(), ('MANIFEST.json', manifest_bytes)]:
                info = zipfile.ZipInfo(f'{PREFIX}/{name}', date_time=timestamp)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        verify_archive(temporary, entries)
        package_hash = sha(temporary.read_bytes())
        receipt = {'file': str(destination), 'bytes': temporary.stat().st_size, 'sha256': package_hash,
                   'files': len(entries), 'source_revision': revision, 'source_dirty': dirty}
        sidecars = [(destination.with_suffix('.sha256'), f'{package_hash}  {destination.name}\n'.encode('utf8')),
                    (destination.with_suffix('.receipt.json'), (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode('utf8'))]
        replacements = [(temporary, destination)]
        for output, data in sidecars:
            with tempfile.NamedTemporaryFile(prefix='.vertice-package-', suffix='.tmp', dir=destination.parent, delete=False) as stream:
                stream.write(data)
                sidecar_temporary = Path(stream.name)
            temporary_paths.append(sidecar_temporary)
            replacements.append((sidecar_temporary, output))
        for source, output in replacements:
            os.replace(source, output)
        print(json.dumps(receipt, ensure_ascii=True))
    finally:
        # Only unlink explicitly created regular temporary files; never recurse.
        for path in temporary_paths:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
