"""Retain actual loopback HTTP test results and source fingerprints."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT))
from verify_independent import AuditResult
import test_server

stream = io.StringIO()
result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=AuditResult).run(
    unittest.defaultTestLoader.loadTestsFromModule(test_server))
paths = [ROOT / 'server.py', ROOT / 'tests/test_server.py', Path(__file__),
         *sorted((ROOT / 'vertice').glob('*.py'))]
report = {'generated_at': datetime.now(timezone.utc).isoformat(),
          'status': 'pass' if result.wasSuccessful() else 'fail',
          'environment': {'python': platform.python_version(), 'platform': platform.platform()},
          'scope': 'Real HTTP loopback requests to isolated synthetic web fixtures; no external services',
          'test_methods': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
          'skipped': len(result.skipped), 'results': result.records,
          'source_hashes': {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in paths}, 'http_requests': test_server.HTTP_OBSERVATIONS}
destination = ROOT / (sys.argv[1] if len(sys.argv) == 2 else 'evidence/verification/http.json')
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
safe_log = stream.getvalue().encode('utf-8', errors='backslashreplace').decode('utf-8')
destination.with_suffix('.log').write_text(safe_log, encoding='utf-8')
print(safe_log)
print(json.dumps({'status': report['status'], 'test_methods': report['test_methods'],
                  'requests': len(report['http_requests']), 'evidence': str(destination)}))
raise SystemExit(0 if result.wasSuccessful() else 1)
