"""Bounded, reproducible probes; no network and no generated workload > 25 kB."""
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vertice.codec import solve_json

base = json.dumps({'graph': {'schema_version': 1, 'directed': False,
                           'nodes': [{'id': 'A'}, {'id': 'B'}],
                           'edges': [{'id': 'e', 'source': 'A', 'target': 'B', 'weight': '__WEIGHT__'}]},
                   'source': 'A', 'target': 'B'})
probes = [('large_positive_exponent', '1e999999999999999999999999999999999'),
          ('large_negative_exponent', '1e-999999999999999999999999999999999'),
          ('trailing_zero_2000', '0.1' + '0' * 2000),
          ('trailing_zero_20000', '0.1' + '0' * 20000)]
records = []
for name, weight in probes:
    payload = base.replace('"__WEIGHT__"', weight)
    start = time.perf_counter_ns()
    try:
        value = solve_json(payload)
        outcome = {'outcome': 'accepted', 'cost': json.loads(value)['cost']}
    except Exception as exc:
        outcome = {'outcome': 'exception', 'exception_type': type(exc).__name__, 'message': str(exc)}
    elapsed = (time.perf_counter_ns() - start) / 1_000_000
    records.append({'id': name, 'input_bytes': len(payload.encode()), 'elapsed_ms': elapsed,
                    'input_sha256': hashlib.sha256(payload.encode()).hexdigest(), **outcome})
report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
          'source_hashes': {str(path.relative_to(ROOT)).replace('\\', '/'):
                            hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted((ROOT / 'vertice').glob('*.py'))},
          'probes': records}
encoded = json.dumps(report, indent=2)
if len(sys.argv) == 2:
    output = ROOT / sys.argv[1]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded + '\n', encoding='utf-8')
print(encoded)
