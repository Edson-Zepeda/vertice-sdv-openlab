"""Mide una entrada sintáctica máxima y el round-trip HTTP observado en código."""
import gc
import hashlib
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vertice.codec import MAX_JSON_BYTES, solve_json
from vertice.graph import ValidationError


def main():
    output = ROOT / "evidence/profiling"
    payload = (output / "import_500_4000.json").read_text(encoding="utf-8")
    response = solve_json(payload)
    duplicate, direct = [], []
    for _ in range(3):
        start = time.perf_counter_ns()
        encoded = json.dumps(json.loads(response), ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
        duplicate.append((time.perf_counter_ns() - start) / 1e6)
        start = time.perf_counter_ns()
        original = response.encode("utf-8")
        direct.append((time.perf_counter_ns() - start) / 1e6)
        assert encoded == original
    count = (MAX_JSON_BYTES - 2) // 3
    hostile = "[" + ",".join(["{}"] * count) + "]"
    gc.collect()
    tracemalloc.start()
    start = time.perf_counter_ns()
    try:
        solve_json(hostile)
    except ValidationError as error:
        rejection = str(error)
    else:
        raise AssertionError("Expected schema rejection")
    elapsed = (time.perf_counter_ns() - start) / 1e6
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report = {"python": sys.version, "platform": platform.platform(),
              "concurrent_workload": "Parent video render and browser endurance test; do not compare absolute latency with final benchmark.",
              "method": "Three HTTP conversion microtimings. Separate tracemalloc probe with one syntactically valid but schema-invalid JSON payload.",
              "response_bytes": len(original), "http_duplicate_samples_ms": duplicate,
              "http_duplicate_median_ms": statistics.median(duplicate),
              "direct_encode_samples_ms": direct, "direct_encode_median_ms": statistics.median(direct),
              "max_payload": {"bytes": len(hostile.encode()), "empty_objects": count,
                              "sha256": hashlib.sha256(hostile.encode()).hexdigest(),
                              "rejection": rejection, "tracemalloc_peak_bytes": peak,
                              "tracemalloc_current_bytes": current, "instrumented_elapsed_ms": elapsed},
              "limits": "Not process RSS. Allocation peak is measured, not an upper bound for all JSON forms or browsers."}
    (output / "json_memory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
