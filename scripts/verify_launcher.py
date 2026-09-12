"""Recheck only Windows launcher behavior after server startup changes."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT))
from verify_independent import AuditResult
import test_cli

names = ['test_windows_launcher_check_in_spanish_path', 'test_windows_launcher_propagates_occupied_port_failure']
suite = unittest.TestSuite(test_cli.CleanCliTests(name) for name in names)
stream = io.StringIO()
result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=AuditResult).run(suite)
report = {'generated_at': datetime.now(timezone.utc).isoformat(),
          'status': 'pass' if result.wasSuccessful() else 'fail', 'test_methods': result.testsRun,
          'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
          'scope': 'Only two launcher checks in a clean snapshot; no browser opened',
          'source_hashes': {**test_cli.SNAPSHOT_MANIFEST,
                            'tests/test_cli.py': hashlib.sha256((ROOT / 'tests/test_cli.py').read_bytes()).hexdigest(),
                            'scripts/verify_launcher.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
          'results': result.records, 'commands': test_cli.CLI_OBSERVATIONS}
destination = ROOT / 'evidence/verification/launcher.json'
destination.write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
destination.with_suffix('.log').write_text(stream.getvalue(), encoding='utf-8')
print(stream.getvalue())
raise SystemExit(0 if result.wasSuccessful() else 1)
