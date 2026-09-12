"""Run the independent standard-library audit and retain machine-readable evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT))
import independent_oracle
import test_independent


class AuditResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({'test': test.id(), 'status': 'pass'})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.records.append({'test': test.id(), 'status': 'fail', 'detail': self._exc_info_to_string(error, test)})

    def addError(self, test, error):
        super().addError(test, error)
        self.records.append({'test': test.id(), 'status': 'error', 'detail': self._exc_info_to_string(error, test)})

    def addSubTest(self, test, subtest, error):
        super().addSubTest(test, subtest, error)
        if error:
            self.records.append({'test': subtest.id(), 'status': 'subtest_failure',
                                 'detail': self._exc_info_to_string(error, test)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='evidence/verification/independent.json')
    parser.add_argument('--export-cases', action='store_true')
    args = parser.parse_args()
    destination = ROOT / args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    if args.export_cases:
        cases = {'schema_version': 1, 'origin': 'synthetic educational contract fixtures',
                 'oracle': 'Bellman-Ford with integer micro-units; independent of delivered algorithm',
                 'cases': independent_oracle.named_cases()}
        (destination.parent / 'cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        seeded = {'seed': 20260912, 'graphs': independent_oracle.seeded_graphs()}
        (destination.parent / 'seeded_graphs.json').write_text(json.dumps(seeded, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    stream = io.StringIO()
    started = datetime.now(timezone.utc)
    clock = time.perf_counter_ns()
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_independent)
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=AuditResult).run(suite)
    elapsed = (time.perf_counter_ns() - clock) / 1_000_000_000
    paths = [*sorted((ROOT / 'vertice').glob('*.py')), Path(test_independent.__file__),
             Path(independent_oracle.__file__), Path(__file__)]
    report = {
        'started_at': started.isoformat(), 'finished_at': datetime.now(timezone.utc).isoformat(),
        'status': 'pass' if result.wasSuccessful() else 'fail',
        'environment': {'python': platform.python_version(), 'implementation': platform.python_implementation(),
                        'platform': platform.platform(), 'machine': platform.machine()},
        'test_methods': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped), 'elapsed_seconds': elapsed,
        'scenarios': test_independent.AUDIT_COUNTS,
        'scope': 'Algorithm, object invariants and strict JSON boundary. Does not prove UI, HTTP or Pyodide parity.',
        'source_hashes': {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in paths},
        'results': result.records,
    }
    # Invalid Unicode in a tested error must remain evidence, not break this reporter.
    destination.write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    safe_log = stream.getvalue().encode('utf-8', errors='backslashreplace').decode('utf-8')
    destination.with_suffix('.log').write_text(safe_log, encoding='utf-8')
    print(safe_log)
    print(json.dumps({'status': report['status'], 'test_methods': report['test_methods'],
                      'scenarios': report['scenarios'], 'evidence': str(destination)}, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
