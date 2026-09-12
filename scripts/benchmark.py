"""Reproducible local measurements; no claims about vehicle or browser latency.

Graph construction, JSON parsing and the independent reference are excluded from
solver timing. A separate end-to-end field includes JSON parsing/validation and
JSON serialization. Memory is a separate traced run, not mixed into timing.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from independent_oracle import bellman_ford, decimal_text, graph
from vertice import Graph
from vertice.codec import solve_json
from vertice.dijkstra import DijkstraSolver


def workloads():
    result = []
    for size in (50, 200, 500):
        ids = [f'N{i:03d}' for i in range(size)]
        data = graph(ids, [(ids[i], ids[i + 1], '1.125') for i in range(size - 1)], True)
        result.append((f'chain_{size}', data, ids[0], ids[-1]))
    rng = random.Random(20260912)
    ids = [f'N{i:03d}' for i in range(500)]
    pairs = {(ids[i], ids[i + 1]): '1' for i in range(499)}
    while len(pairs) < 4000:
        source, target = rng.sample(ids, 2)
        pairs.setdefault((source, target), str(rng.randint(0, 200) / 10))
    data = graph(ids, [(source, target, weight) for (source, target), weight in pairs.items()], True)
    result.append(('directed_500_4000', data, ids[0], ids[-1]))
    grid = [f'N{i:03d}' for i in range(400)]
    pairs = []
    for row in range(20):
        for col in range(20):
            position = row * 20 + col
            if row < 19:
                pairs.append((grid[position], grid[position + 20], '1'))
            if col < 19:
                pairs.append((grid[position], grid[position + 1], '1'))
    result.append(('undirected_grid_400', graph(grid, pairs), grid[0], grid[-1]))
    isolated = graph(ids, [(ids[i], ids[i + 1], '0') for i in range(498)], True)
    result.append(('unreachable_500_zero_chain', isolated, ids[0], ids[-1]))
    result.append(('same_source_target_500', data, ids[250], ids[250]))
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def distribution(values):
    ordered = sorted(values)
    return {'samples_ms': values, 'median_ms': statistics.median(values),
            'min_ms': min(values), 'max_ms': max(values),
            'p95_nearest_rank_ms': ordered[math.ceil(0.95 * len(ordered)) - 1]}


def measure(call, repeats):
    values = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        call()
        values.append((time.perf_counter_ns() - start) / 1_000_000)
    return distribution(values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='evidence/verification/benchmark.json')
    parser.add_argument('--repeats', type=int, default=9)
    args = parser.parse_args()
    if args.repeats < 3 or args.repeats > 100:
        parser.error('--repeats must be between 3 and 100')
    records = []
    for name, data, source, target in workloads():
        oracle_cost = decimal_text(bellman_ford(data, source)[target])
        native = Graph.from_dict(data)
        solver = DijkstraSolver(native)
        for trace in (False, True):
            payload = {'graph': data, 'source': source, 'target': target, 'trace': trace}
            encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
            first = solver.solve(source, target, trace)
            assert first['cost'] == oracle_cost, (name, first['cost'], oracle_cost)
            assert json.loads(solve_json(encoded)) == first, name
            for _ in range(2):
                solver.solve(source, target, trace)
            solver_time = measure(lambda: solver.solve(source, target, trace), args.repeats)
            end_to_end = measure(lambda: solve_json(encoded), args.repeats)
            tracemalloc.start()
            solver.solve(source, target, trace)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            record = {'id': name, 'nodes': len(data['nodes']), 'edges': len(data['edges']),
                      'directed': data['directed'], 'trace_enabled': trace, 'trace_events': len(first['trace']),
                      'source': source, 'target': target, 'cost': first['cost'],
                      'oracle_match': first['cost'] == oracle_cost, 'stats': first['stats'],
                      'payload_sha256': hashlib.sha256(encoded.encode()).hexdigest(),
                      'payload_bytes': len(encoded.encode()), 'solver_only': solver_time,
                      'json_to_json': end_to_end, 'solver_tracemalloc_peak_bytes': peak}
            records.append(record)
            print(f"{name} trace={trace}: solver median {solver_time['median_ms']:.3f} ms; "
                  f"JSON median {end_to_end['median_ms']:.3f} ms; oracle OK")
    paths = sorted((ROOT / 'vertice').glob('*.py')) + [Path(__file__), ROOT / 'tests/independent_oracle.py']
    report = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'environment': {'python': platform.python_version(), 'implementation': platform.python_implementation(),
                              'platform': platform.platform(), 'processor': platform.processor(),
                              'machine': platform.machine(), 'timer': 'perf_counter_ns'},
              'method': {'warmups_per_solver': 2, 'timed_repeats_per_variant': args.repeats,
                         'graph_seed': 20260912, 'oracle': 'synchronous Bellman-Ford integer micro-units, untimed',
                         'solver_only': 'Preconstructed Graph; graph parsing and construction excluded',
                         'json_to_json': 'solve_json; includes validation, graph construction, solve and JSON serialization',
                         'memory': 'Separate tracemalloc run; peak Python allocations, not complete process RAM',
                         'p95': 'Nearest-rank descriptive percentile; with 9 samples this equals maximum',
                         'scope': 'Single local Windows machine, CPython. Not a browser, real-time or vehicle guarantee.'},
              'source_hashes': {str(path.relative_to(ROOT)).replace('\\', '/'): digest(path) for path in paths},
              'workload_count': len(records) // 2, 'measured_variants': len(records), 'results': records}
    destination = ROOT / args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    fixtures = [{'id': name, 'graph': data, 'source': source, 'target': target}
                for name, data, source, target in workloads()]
    destination.with_name('benchmark_graphs.json').write_text(
        json.dumps({'seed': 20260912, 'graphs': fixtures}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
