"""Rechaza una web que difiera del núcleo Python o su manifiesto."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'web/python/manifest.json').read_text(encoding='utf8'))
expected={'__init__.py','graph.py','dijkstra.py','codec.py'}
if {f['name'] for f in manifest['files']}!=expected or len(manifest['files'])!=len(expected):
    raise SystemExit('Manifiesto incompleto o duplicado.')
for entry in manifest['files']:
    original=(ROOT/'vertice'/entry['name']).read_bytes()
    copied=(ROOT/'web/python/vertice'/entry['name']).read_bytes()
    if original!=copied or hashlib.sha256(original).hexdigest()!=entry['sha256']:
        raise SystemExit(f'El núcleo web difiere: {entry["name"]}. Ejecuta scripts/sync_web_core.py.')
print('Núcleo nativo, copia web y manifiesto idénticos (4 archivos).')
