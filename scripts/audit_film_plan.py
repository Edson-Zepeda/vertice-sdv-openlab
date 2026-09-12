"""Read-only audit of the film plan and rendered content, before MP4 export."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('film_builder_for_audit', ROOT / 'scripts/build_film.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
plan_path = ROOT / 'media/render/film-plan.json'
plan = json.loads(plan_path.read_text(encoding='utf-8'))
renderer = builder.Renderer(builder.sources(), plan['scenes'])
scenes = []
for index, scene in enumerate(plan['scenes']):
    overlaps = [{'first_end': first['end'], 'next_start': second['start'],
                 'seconds': first['end'] - second['start']}
                for first, second in zip(scene['cues'], scene['cues'][1:])
                if first['end'] > second['start']]
    # Exclude subtitles, title, footer and progress bar: moving those alone does
    # not establish movement of the visual explanation.
    fingerprints = []
    for progress in (.25, .50, .75):
        at = scene['duration'] * progress
        pixels = renderer.frame(index, at, scene['duration']).crop((80, 300, 1840, 915)).tobytes()
        fingerprints.append({'local_seconds': at, 'content_sha256': hashlib.sha256(pixels).hexdigest()})
    scenes.append({'id': scene['id'], 'duration': scene['duration'], 'cue_overlaps': overlaps,
                   'content_samples': fingerprints, 'distinct_content_samples': len({row['content_sha256'] for row in fingerprints})})
report = {'generated_at': datetime.now(timezone.utc).isoformat(),
          'status': 'pre_export_diagnostic', 'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
          'builder_sha256': hashlib.sha256((ROOT / 'scripts/build_film.py').read_bytes()).hexdigest(),
          'scope': 'Three renderer samples per scene, not verification of final encoded MP4 or animation quality',
          'scenes': scenes}
destination = ROOT / (sys.argv[1] if len(sys.argv) == 2 else 'evidence/video_audit/plan_audit.json')
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'scenes': len(scenes), 'overlaps': sum(len(row['cue_overlaps']) for row in scenes),
                  'same_content_at_three_samples': [row['id'] for row in scenes if row['distinct_content_samples'] == 1]}))
