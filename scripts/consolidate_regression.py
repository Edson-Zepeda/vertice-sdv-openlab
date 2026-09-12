"""Normalize already executed checks; never rerun or invent test executions."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'evidence/verification'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')


def preserve(path, records):
    backup = path.with_name(path.stem + '_before_final_guard' + path.suffix)
    if not backup.exists():
        shutil.copyfile(path, backup)
    records.append({'original': path.relative_to(ROOT).as_posix(),
                    'preserved': backup.relative_to(ROOT).as_posix(), 'sha256': sha(backup)})
    return backup


def main():
    guard_path = EVIDENCE / 'json_guard.json'
    guard = read(guard_path)
    assert guard['all_passed'] and guard['protected_unchanged']
    for name, digest in guard['protected_sha256'].items():
        assert sha(ROOT / name) == digest, f'Stale matrix source: {name}'
    assert sha(ROOT / 'scripts/verify_json_guard.py') == guard['source_sha256']
    versions = {'3.10.11': '310', '3.11.9': '311', '3.12.14': '312', '3.14.7': '314'}
    assert {run['version'].removeprefix('Python ') for run in guard['matrix']} == set(versions)
    preserved = []
    normalized = []
    for run in guard['matrix']:
        version = run['version'].removeprefix('Python ')
        suffix = versions[version]
        destination = EVIDENCE / ('independent.json' if suffix == '311' else f'independent_python{suffix}.json')
        baseline_path = preserve(destination, preserved)
        preserve(destination.with_suffix('.log'), preserved)
        baseline = read(baseline_path)
        # The suite and algorithm did not change. Its previous counter instrumentation
        # remains a documented coverage baseline, not a newly observed measurement.
        stable = ('tests/test_independent.py', 'tests/independent_oracle.py',
                  'vertice/graph.py', 'vertice/dijkstra.py')
        for name in stable:
            assert sha(ROOT / name) == baseline['source_hashes'][name], f'Changed coverage definition: {name}'
        suite = next(item for item in run['suites'] if item['name'] == 'test_independent.py')
        assert suite['passed'] and suite['exit_code'] == 0 and suite['tests'] == 38
        log_path = ROOT / run['log']
        full_log = log_path.read_text(encoding='utf-8')
        section = full_log.split('\ntest_independent.py\n', 1)[1].split('\ntest_json_guard.py\n', 1)[0]
        entries = re.findall(r'^(\w+) \((test_independent\.[^)]+)\) \.\.\. ok$', section, re.M)
        # Python 3.10 prints only the class in parentheses; newer runtimes
        # include the method there as well. Preserve the actual test ID in both.
        matches = [qualified if qualified.endswith('.' + method) else qualified + '.' + method
                   for method, qualified in entries]
        assert len(matches) == 38 and len(set(matches)) == 38
        assert set(matches) == {item['test'] for item in baseline['results']}
        timing = re.search(r'Ran 38 tests in ([0-9.]+)s\s+OK\s*$', section)
        assert timing, 'Only a complete successful suite can be normalized'
        current_cli = read(EVIDENCE / f'cli_python{suffix}.json')
        assert current_cli['status'] == 'pass' and current_cli['environment']['python'] == version
        source_hashes = {name: digest for name, digest in guard['protected_sha256'].items()
                         if name.startswith('vertice/')}
        source_hashes.update({name: sha(ROOT / name) for name in (
            'tests/test_independent.py', 'tests/independent_oracle.py',
            'scripts/verify_json_guard.py', 'scripts/consolidate_regression.py')})
        report = {
            'generated_at': guard['created_utc'], 'status': 'pass',
            'timestamp_scope': 'Completion of the shared matrix collector; individual start/end timestamps were not captured.',
            'environment': {'python': version, 'implementation': 'CPython',
                            'platform': current_cli['environment']['platform'], 'executable': run['executable'],
                            'subprocess_flags': ['-S']},
            'test_methods': 38, 'failures': 0, 'errors': 0, 'skipped': 0,
            'elapsed_seconds': float(timing.group(1)),
            'elapsed_scope': 'Rounded unittest suite duration from the retained log, excluding subprocess startup.',
            'scenarios': baseline['scenarios'],
            'scenario_count_provenance': {
                'mode': 'Prior instrumentation of the identical deterministic suite and unchanged graph/solver',
                'file': baseline_path.relative_to(ROOT).as_posix(), 'sha256': sha(baseline_path),
                'note': 'The shared rerun passed all 38 methods but did not emit AUDIT_COUNTS. Counts are retained coverage definitions, not new counter observations.'},
            'scope': baseline['scope'], 'source_hashes': source_hashes,
            'derived_from': {'matrix': guard_path.relative_to(ROOT).as_posix(), 'matrix_sha256': sha(guard_path),
                             'log': run['log'], 'log_sha256': sha(log_path),
                             'note': 'Extracted from an actual shared execution of unittest; verify_independent.py was not run again.'},
            'results': [{'test': name, 'status': 'pass'} for name in matches],
        }
        write(destination, report)
        destination.with_suffix('.log').write_text(section.lstrip(), encoding='utf-8')
        normalized.append(destination.name)

    # The launcher is already exercised by the current CLI matrix. Extract its
    # two observations explicitly rather than claim another standalone execution.
    launcher = EVIDENCE / 'launcher.json'
    preserve(launcher, preserved)
    preserve(launcher.with_suffix('.log'), preserved)
    cli_path = EVIDENCE / 'cli_python311.json'
    cli = read(cli_path)
    results = [item for item in cli['results'] if '.test_windows_launcher_' in item['test']]
    commands = [item for item in cli['commands'] if '.test_windows_launcher_' in item['test']]
    assert len(results) == len(commands) == 2 and all(item['status'] == 'pass' for item in results)
    report = {key: cli[key] for key in ('generated_at', 'status', 'environment', 'source_hashes')}
    report.update({'test_methods': 2, 'failures': 0, 'errors': 0, 'skipped': 0,
                   'scope': 'Two launcher checks extracted from the current CPython 3.11 CLI execution; not an additional run.',
                   'derived_from': {'file': cli_path.relative_to(ROOT).as_posix(), 'sha256': sha(cli_path)},
                   'results': results, 'commands': commands})
    write(launcher, report)
    launcher.with_suffix('.log').write_text(
        'Extracted from cli_python311.log; no additional execution.\n' + '\n'.join(
            line for line in cli_path.with_suffix('.log').read_text(encoding='utf-8').splitlines()
            if 'test_windows_launcher_' in line) + '\n', encoding='utf-8')
    write(EVIDENCE / 'shared_regression_preservation.json', {
        'generated_at': datetime.now(timezone.utc).isoformat(), 'files': preserved,
        'normalized_independent_reports': normalized, 'launcher_derived_from': 'cli_python311.json'})

    matrix = []
    for version, suffix in versions.items():
        files = [f'cli_python{suffix}.json',
                 'http.json' if suffix == '311' else f'http_python{suffix}.json',
                 'independent.json' if suffix == '311' else f'independent_python{suffix}.json']
        suites = []
        for name in files:
            path = EVIDENCE / name
            report = read(path)
            assert report['status'] == 'pass' and report['environment']['python'] == version
            for source, digest in report['source_hashes'].items():
                assert sha(ROOT / source) == digest, f'Stale evidence {name}: {source}'
            suites.append({'file': path.relative_to(ROOT).as_posix(), 'sha256': sha(path),
                           'test_methods': report['test_methods'], 'source_hashes_current': True,
                           'derived_from_shared_run': 'derived_from' in report})
        matrix.append({'python': version, 'suites': suites})
    write(EVIDENCE / 'final_guard_matrix.json', {
        'generated_at': datetime.now(timezone.utc).isoformat(), 'all_passed': True, 'matrix': matrix,
        'scope': 'Four runtimes on one Windows computer; repeated versions do not create additional unique scenarios. No Linux or remote CI execution is claimed.',
        'collector_sha256': sha(Path(__file__))})
    print(json.dumps({'status': 'pass', 'runtimes': len(matrix), 'reports': sum(len(row['suites']) for row in matrix),
                      'test_executions_performed_by_this_script': 0}))


if __name__ == '__main__':
    main()
