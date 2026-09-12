"""Run CLI subprocess checks on this Python interpreter and retain evidence."""
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
import test_cli

stream = io.StringIO()
result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=AuditResult).run(
    unittest.defaultTestLoader.loadTestsFromModule(test_cli))
report = {'generated_at': datetime.now(timezone.utc).isoformat(),
          'status': 'pass' if result.wasSuccessful() else 'fail',
          'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                          'executable': sys.executable, 'subprocess_flags': ['-S'],
                          'third_party_imports': 'site-packages disabled'},
          'scope': 'Clean source snapshot in path with spaces and Spanish accents; real CLI subprocesses',
          'test_methods': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
          'skipped': len(result.skipped), 'results': result.records,
          'source_hashes': {**test_cli.SNAPSHOT_MANIFEST,
                            'tests/test_cli.py': hashlib.sha256((ROOT / 'tests/test_cli.py').read_bytes()).hexdigest(),
                            'scripts/verify_cli.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
          'commands': test_cli.CLI_OBSERVATIONS}
destination = ROOT / (sys.argv[1] if len(sys.argv) == 2 else f'evidence/verification/cli_python{sys.version_info.major}{sys.version_info.minor}.json')
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
safe_log = stream.getvalue().encode('utf-8', errors='backslashreplace').decode('utf-8')
destination.with_suffix('.log').write_text(safe_log, encoding='utf-8')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
print(safe_log)
print(json.dumps({'status': report['status'], 'test_methods': report['test_methods'],
                  'commands': len(report['commands']), 'evidence': str(destination)}))
raise SystemExit(0 if result.wasSuccessful() else 1)
