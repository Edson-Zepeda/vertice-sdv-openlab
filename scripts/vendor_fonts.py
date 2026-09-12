"""Descarga fuentes abiertas sin solicitudes externas durante el uso de la web."""
from pathlib import Path
import hashlib
import json
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
REVISION = '809e4d8b8d7e9364a914909bb777679606c178b8'

def main():
    revision = REVISION
    entries = {
        'Manrope.ttf': 'ofl/manrope/Manrope%5Bwght%5D.ttf',
        'Manrope-OFL.txt': 'ofl/manrope/OFL.txt',
        'DMSans.ttf': 'ofl/dmsans/DMSans%5Bopsz%2Cwght%5D.ttf',
        'DMSans-OFL.txt': 'ofl/dmsans/OFL.txt',
    }
    destination = ROOT / 'web' / 'fonts'
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    for filename, path in entries.items():
        url = f'https://raw.githubusercontent.com/google/fonts/{revision}/{path}'
        with urllib.request.urlopen(url) as response:
            data = response.read()
        (destination / filename).write_bytes(data)
        results.append({'path': f'web/fonts/{filename}', 'url': url, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    manifest = {'repository': 'https://github.com/google/fonts', 'revision': revision,
                'retrieved_at': datetime.now(timezone.utc).isoformat(), 'files': results}
    (ROOT / 'evidence' / 'dependencies' / 'fonts.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'files': len(results), 'bytes': sum(item['bytes'] for item in results), 'revision': revision}))

if __name__ == '__main__':
    main()
