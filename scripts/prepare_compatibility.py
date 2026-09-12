"""Optional audit helper: official portable CPython runtimes, no installation.

Only writes to this project's ignored tmp/compatibility directory. Does not
change PATH, registry, installed Python, or any user browser setting.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'tmp/compatibility'
PACKAGES = [
    {'version': '3.10.11', 'page': 'https://www.python.org/downloads/release/python-31011/',
     'url': 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip',
     'published_digest_algorithm': 'md5', 'published_digest': 'f1c0538b060e03cbb697ab3581cb73bc'},
    {'version': '3.14.7', 'page': 'https://www.python.org/downloads/release/python-3147/',
     'url': 'https://www.python.org/ftp/python/3.14.7/python-3.14.7-embed-amd64.zip',
     'published_digest_algorithm': 'sha256',
     'published_digest': 'd297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15'},
]


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    results = []
    for package in PACKAGES:
        archive = DESTINATION / package['url'].rsplit('/', 1)[-1]
        if not archive.exists():
            request = urllib.request.Request(package['url'], headers={'User-Agent': 'VerticeSDV-Compatibility/1.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(30 * 1024 * 1024 + 1)
            if len(data) > 30 * 1024 * 1024:
                raise ValueError('Unexpected package size')
            archive.write_bytes(data)
        data = archive.read_bytes()
        observed = hashlib.new(package['published_digest_algorithm'], data).hexdigest()
        if observed != package['published_digest']:
            raise ValueError(f"Published digest mismatch for {package['version']}")
        runtime = (DESTINATION / f"python-{package['version']}").resolve()
        if not runtime.is_relative_to(DESTINATION.resolve()):
            raise ValueError('Runtime directory outside temporary workspace')
        runtime.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:
                raise ValueError('Corrupt runtime ZIP')
            if sum(item.file_size for item in bundle.infolist()) > 150 * 1024 * 1024:
                raise ValueError('Unexpected expanded runtime size')
            for item in bundle.infolist():
                if not (runtime / item.filename).resolve().is_relative_to(runtime):
                    raise ValueError('Unsafe path in official runtime ZIP')
            bundle.extractall(runtime)
        # The embed file normally pins sys.path to the runtime directory. Rename
        # only that local configuration so -m can load a clean snapshot in cwd.
        # Every product subprocess additionally uses -S (no site-packages).
        settings = []
        for path in runtime.glob('python*._pth'):
            disabled = path.with_suffix(path.suffix + '.audit-disabled')
            settings.append({'file': path.name, 'original': path.read_text(encoding='utf-8'),
                             'audit_change': 'renamed only in isolated test runtime to permit cwd package imports'})
            path.replace(disabled)
        version = subprocess.run([str(runtime / 'python.exe'), '-S', '--version'],
                                 capture_output=True, check=True, timeout=10).stdout.decode().strip()
        results.append({**package, 'archive_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                        'published_digest_verified': True, 'runtime': str(runtime.relative_to(ROOT)),
                        'reported_version': version, 'isolated_configuration': settings})
        print(version, 'portable runtime ready', len(data), 'bytes', flush=True)
    report = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Temporary audit runtimes; not bundled with deliverable, no system installation',
              'notes': 'Python 3.10.11 is an old binary release used only to exercise the declared minimum series, '
                       'not a recommendation to install this patch level. SHA-256 retained for both; '
                       '3.10 page publishes MD5, which is only an integrity cross-check, not authenticity proof.',
              'packages': results}
    (ROOT / 'evidence/verification/portable_runtimes.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
