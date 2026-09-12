"""Adversarial in-memory image probes for the film verifier's regional thresholds.

No delivered media is edited. Intentionally remove titles or caption letters
from renderer frames to demonstrate why a whole-frame average is insufficient.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

from PIL import ImageChops, ImageDraw, ImageStat

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('builder_for_pixel_probes', ROOT / 'scripts/build_film.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
plan = json.loads((ROOT / 'media/render/film-plan.json').read_text(encoding='utf-8'))
renderer = builder.Renderer(builder.sources(), plan['scenes'])
regions = {'title': (77, 180, 1840, 290), 'captions': (170, 923, 1750, 1005)}
results = []
for index, scene in enumerate(plan['scenes']):
    at = scene['duration'] * .58
    original = renderer.frame(index, at, scene['duration'])
    assert any(c['start'] <= at < c['end'] for c in scene['cues'])
    for name, color in [('title', builder.PAPER), ('captions', builder.INK)]:
        mutant = original.copy()
        # Caption erasure leaves the rounded background box intact.
        erasure = regions[name] if name == 'title' else (190, 935, 1730, 990)
        ImageDraw.Draw(mutant).rectangle(erasure, fill=color)
        diff = ImageChops.difference(original, mutant)
        global_mae = sum(ImageStat.Stat(diff).mean) / 3
        local_mae = sum(ImageStat.Stat(diff.crop(regions[name])).mean) / 3
        results.append({'scene': scene['id'], 'mutation': f'erase_{name}', 'global_mae': global_mae,
                        'region_mae': local_mae, 'old_global_criterion_accepts': global_mae <= 6,
                        'regional_criterion_rejects': local_mae > 3})
evidence = {'scope': 'Synthetic counterexamples in memory, not an MP4 inspection or edit',
            'source_hashes': {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [Path(__file__), ROOT / 'scripts/verify_film.py', ROOT / 'scripts/build_film.py',
                                        ROOT / 'media/render/film-plan.json']}, 'results': results}
destination = ROOT / 'evidence/video_audit/verifier_image_mutations.json'
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'mutations': len(results), 'rejected_by_regions': sum(r['regional_criterion_rejects'] for r in results),
                  'wrongly_accepted_by_global_only': sum(r['old_global_criterion_accepts'] for r in results)}))
raise SystemExit(0 if all(r['regional_criterion_rejects'] for r in results) else 1)
