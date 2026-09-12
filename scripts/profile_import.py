"""Diagnóstico acotado de importación; no modifica el núcleo ni el benchmark."""
from __future__ import annotations

import cProfile
import argparse
import gc
import hashlib
import json
import platform
import pstats
import random
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vertice.codec import load_json, solve_json
from vertice.dijkstra import DijkstraSolver
from vertice.graph import Graph

OUT = ROOT / "evidence" / "profiling"


def generate(n: int, m: int) -> dict:
    rng = random.Random(20260912)
    pairs = {(i, i + 1): "1" for i in range(n - 1)}
    while len(pairs) < m:
        source, target = rng.randrange(n), rng.randrange(n)
        if source != target and (source, target) not in pairs:
            pairs[source, target] = str(rng.randint(0, 200) / 10)
    return {"schema_version": 1, "directed": True,
            "nodes": [{"id": f"N{i:03}", "label": f"Nodo {i}", "x": i % 25 * 40,
                       "y": i // 25 * 40} for i in range(n)],
            "edges": [{"id": f"e{i}", "source": f"N{a:03}", "target": f"N{b:03}",
                       "weight": weight} for i, ((a, b), weight) in enumerate(pairs.items())]}


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def measure(callback):
    start = time.perf_counter_ns()
    value = callback()
    return value, (time.perf_counter_ns() - start) / 1e6


def allocation_peak(callback):
    gc.collect()
    tracemalloc.start()
    value = callback()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"current_bytes": current, "peak_bytes": peak}, value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrent-workload", default="unspecified")
    parser.add_argument("--output-name", default="import_profile")
    options = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    saved = json.loads((ROOT / "evidence/verification/benchmark_graphs.json").read_text(encoding="utf-8"))
    original = next(item for item in saved["graphs"] if item["id"] == "directed_500_4000")
    cases = [("scaled_50_400", generate(50, 400)), ("scaled_200_1600", generate(200, 1600))]
    for m in (500, 2000, 4000):
        data = original["graph"] | {"edges": original["graph"]["edges"][:m]}
        cases.append((f"same_500_{m}", data))
    report = {"schema_version": 1, "python": sys.version, "platform": platform.platform(),
              "processor": platform.processor(), "repetitions": 3, "trace": True,
              "method": "Fresh stage timings; one warm-up; profiling and tracemalloc separate from timing.",
              "scope": "CPython allocations, not process RSS or browser/Wasm memory.",
              "concurrent_workload": options.concurrent_workload,
              "source_hashes": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted((ROOT / "vertice").glob("*.py"))}, "workloads": []}
    for name, data in cases:
        payload = {"graph": data, "source": data["nodes"][0]["id"],
                   "target": data["nodes"][-1]["id"], "trace": True}
        text = dump(payload)
        reference = solve_json(text)
        samples = {key: [] for key in ("parse", "graph", "solve", "serialize", "whole")}
        for _ in range(3):
            loaded, elapsed = measure(lambda: load_json(text))
            samples["parse"].append(elapsed)
            native, elapsed = measure(lambda: Graph.from_dict(loaded["graph"]))
            samples["graph"].append(elapsed)
            solved, elapsed = measure(lambda: DijkstraSolver(native).solve(payload["source"], payload["target"], True))
            samples["solve"].append(elapsed)
            encoded, elapsed = measure(lambda: dump(solved))
            samples["serialize"].append(elapsed)
            assert encoded == reference
            encoded, elapsed = measure(lambda: solve_json(text))
            samples["whole"].append(elapsed)
            assert encoded == reference
        whole_memory, _ = allocation_peak(lambda: solve_json(text))
        solver_memory, _ = allocation_peak(lambda: DijkstraSolver(native).solve(payload["source"], payload["target"], True))
        item = {"id": name, "nodes": len(data["nodes"]), "edges": len(data["edges"]),
                "input_bytes": len(text.encode()), "output_bytes": len(reference.encode()),
                "trace_events": len(solved["trace"]), "stats": solved["stats"],
                "samples_ms": samples, "median_ms": {k: round(statistics.median(v), 4) for k, v in samples.items()},
                "whole_allocations": whole_memory, "solver_allocations": solver_memory}
        report["workloads"].append(item)
        if name == "same_500_4000":
            profiler = cProfile.Profile()
            profiler.runcall(solve_json, text)
            profiler.dump_stats(str(OUT / "import_500_4000.prof"))
            stats = pstats.Stats(profiler)
            rows = []
            for (file, line, function), (primitive, calls, total, cumulative, _) in stats.stats.items():
                rows.append({"file": file, "line": line, "function": function, "calls": calls,
                             "primitive_calls": primitive, "total_ms": total * 1000, "cumulative_ms": cumulative * 1000})
            report["profile"] = {"total_calls": stats.total_calls, "total_ms": stats.total_tt * 1000,
                                 "functions": sorted(rows, key=lambda row: row["cumulative_ms"], reverse=True)}
            (OUT / "import_500_4000.json").write_text(text, encoding="utf-8")
        print(json.dumps({"id": name, "median_ms": item["median_ms"], "whole_peak_bytes": whole_memory["peak_bytes"]}))
    (OUT / f"{options.output_name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["profile"]["functions"][:25], indent=2))


if __name__ == "__main__":
    main()
