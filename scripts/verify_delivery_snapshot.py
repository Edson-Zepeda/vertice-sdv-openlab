"""Exercise delivery commands from an isolated copy without Git or render caches.

The snapshot is retained under ignored tmp/ for inspection. No package is
published and no application/core/media source is modified.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'evidence/delivery'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (ROOT / 'tmp').mkdir(exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='Entrega Vértice con espacios-', dir=ROOT / 'tmp')).resolve()
    assert base.is_relative_to((ROOT / 'tmp').resolve())
    snapshot = base / 'proyecto'
    snapshot.mkdir()
    directories = ['vertice', 'web', 'examples', 'media/narration', 'evidence/dependencies']
    files = ['README.md', 'requirements-build.txt', 'LICENSE', 'THIRD_PARTY.md', 'project.json', 'server.py', 'Iniciar.cmd',
             '.github/workflows/verify.yml', 'docs/DEFENSA.md', 'docs/VerticeSDV_Informe.pdf',
             'scripts/check_web_core.py', 'scripts/sync_web_core.py', 'scripts/package_release.py', 'scripts/benchmark.py',
             'scripts/build_film.py', 'scripts/verify_film.py', 'tests/engine_queue.mjs', 'tests/independent_oracle.py',
             'evidence/video.json', 'evidence/verification/benchmark.json', 'output/playwright/desktop-route.png']
    for directory in directories:
        shutil.copytree(ROOT / directory, snapshot / directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in files:
        destination = snapshot / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    hashes = {p.relative_to(snapshot).as_posix(): sha(p) for p in snapshot.rglob('*') if p.is_file()}
    assert all(sha(ROOT / name) == digest for name, digest in hashes.items())
    env = os.environ.copy()
    for variable in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONSAFEPATH'):
        env.pop(variable, None)
    env['PYTHONIOENCODING'] = 'utf-8'
    commands = []

    def command(label, arguments, expected=0, cwd=snapshot, timeout=30):
        result = subprocess.run(arguments, cwd=cwd, env=env, capture_output=True, encoding='utf8', errors='replace', timeout=timeout)
        commands.append({'label': label, 'arguments': [str(v) for v in arguments], 'cwd': str(cwd),
                         'expected_exit': expected, 'exit': result.returncode, 'passed': result.returncode == expected,
                         'stdout': result.stdout[-5000:], 'stderr': result.stderr[-3000:]})
        return result

    py = sys.executable
    command('local_server_without_site_packages', [py, '-S', str(snapshot / 'server.py'), '--check'], cwd=base)
    command('documented_validate_example', [py, '-S', '-m', 'vertice.cli', 'validate', 'examples/desvio.json'])
    solved = command('documented_solve_example', [py, '-S', '-m', 'vertice.cli', 'solve', 'examples/desvio.json', '--source', 'S', '--target', 'T', '--json'])
    commands[-1]['passed'] = commands[-1]['passed'] and json.loads(solved.stdout)['cost'] == '11'
    command('web_core_integrity_from_other_directory', [py, '-S', str(snapshot / 'scripts/check_web_core.py')], cwd=base)
    command('web_core_sync_from_other_directory', [py, '-S', str(snapshot / 'scripts/sync_web_core.py')], cwd=base)
    command('documented_benchmark_help', [py, '-S', 'scripts/benchmark.py', '--help'])
    node = shutil.which('node')
    if node:
        command('documented_engine_queue', [node, 'tests/engine_queue.mjs'])
    else:
        commands.append({'label': 'documented_engine_queue', 'passed': False, 'reason': 'Node.js is not installed'})
    if os.name == 'nt':
        command('windows_launcher_from_spanish_directory', ['cmd', '/d', '/c', 'Iniciar.cmd', '--check'])
    # A source ZIP has no Git history; the packaging helper should explain that.
    command('repack_without_git_has_concise_error', [py, '-S', 'scripts/package_release.py', '--output', str(base / 'repack.zip')], expected=2)
    # Reproduce the previously recorded verifier against this exact clean shape.
    prior = ROOT / 'evidence/delivery/before/verify_film.py.txt'
    target = snapshot / 'scripts/verify_film.py'
    shutil.copyfile(prior, target)
    before = command('before_video_verifier_requires_excluded_render_plan', [py, str(target), '--output', 'evidence/video-before.json'], expected=1)
    before_report = json.loads((snapshot / 'evidence/video-before.json').read_text(encoding='utf8'))
    (EVIDENCE / 'clean_snapshot_video_before.json').write_text(json.dumps(before_report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    shutil.copyfile(ROOT / 'scripts/verify_film.py', target)
    command('video_verifies_without_render_intermediates', [py, str(target)], timeout=240)
    video_report = json.loads((snapshot / 'evidence/video_audit/verification.json').read_text(encoding='utf8'))
    commands[-1]['passed'] = commands[-1]['passed'] and video_report['status'] == 'passed' and video_report.get('plan_source') == 'included_export_proof'
    (EVIDENCE / 'clean_snapshot_video.json').write_text(json.dumps(video_report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    unchanged = [name for name, digest in hashes.items() if sha(snapshot / name) != digest]
    source_changed = [name for name, digest in hashes.items() if sha(ROOT / name) != digest]
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'status': 'pass' if all(c['passed'] for c in commands) and not unchanged and not source_changed else 'fail',
              'script_sha256': sha(__file__), 'snapshot': str(snapshot), 'python': sys.version,
              'excluded': ['.git', 'media/render', 'node_modules', '.venv', '__pycache__'],
              'scope': 'Curated delivery snapshot. Includes vendored web runtime and voice assets; no original Git metadata or development environment.',
              'copied_files': len(hashes), 'source_hashes': hashes, 'copied_inputs_changed': unchanged, 'original_inputs_changed': source_changed,
              'commands': commands}
    (EVIDENCE / 'clean_snapshot.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'passed': sum(c['passed'] for c in commands), 'commands': len(commands), 'files': len(hashes)}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
