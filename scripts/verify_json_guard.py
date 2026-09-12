"""Verify the integrated JSON guard, retaining the original memory baseline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
SUBPROCESS_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from vertice.codec import (_guard_json_structure, MAX_JSON_BYTES, MAX_JSON_CONTAINERS,
                           MAX_JSON_PUNCTUATION, load_json, solve_json, solve_payload)
from vertice.graph import ValidationError
from experiment_json_preflight import preflight
from review_json_preflight import reference_counts
from test_json_guard import maximum_graph


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def outcome(callback, raw):
    try:
        callback(raw)
    except ValidationError:
        return "rejected"
    return "accepted"


def check_equivalence():
    rng = random.Random(260913)
    counts = {"small_graphs": 0, "large_graphs": 0, "lexical_mutations": 0, "threshold_cases": 0}
    samples = []

    def verify(raw, group):
        containers, punctuation, _ = reference_counts(raw)
        expected = "rejected" if containers > MAX_JSON_CONTAINERS or punctuation > MAX_JSON_PUNCTUATION else "accepted"
        actual = outcome(_guard_json_structure, raw)
        proposal = outcome(preflight, raw)
        if actual != expected or actual != proposal:
            raise AssertionError(f"Mismatch in {group}: {actual}, {proposal}, {expected}")
        counts[group] += 1

    alphabet = 'áéΩ🧭漢字[{}],:\\"abc09'
    for i in range(300):
        data = {"schema_version": 1, "directed": bool(i % 2),
                "nodes": [{"id": "A", "label": "".join(rng.choice(alphabet) for _ in range(rng.randrange(81)))}], "edges": []}
        for ascii_only in (True, False):
            verify(json.dumps(data, ensure_ascii=ascii_only, indent=2 if i % 3 == 0 else None), "small_graphs")
    for label in ("[" * 80, "," * 80, "\\\"" * 40, "🧭" * 80, '🧭[{,:}]\\"' * 8):
        for ascii_only in (False, True):
            request = {"graph": maximum_graph(label), "source": "N000", "target": "N499", "trace": False}
            raw = json.dumps(request, ensure_ascii=ascii_only, separators=(",", ":"))
            verify(raw, "large_graphs")
            samples.append({"label_prefix": repr(label[:9]), "ascii": ascii_only,
                            "bytes": len(raw.encode()), "counts": reference_counts(raw)})
    for n in (4999, 5000, 5001):
        for noisy in ("", "[" * 6000, "\\\"" * 8000):
            verify("[" + ",".join(["{}"] * n + [json.dumps(noisy)]) + "]", "threshold_cases")
    for n in (49999, 50000, 50001):
        for noisy in ("", "," * 50001, '🧭\\"[{,:]' * 10000):
            verify("[" + ",".join(["0"] * n + [json.dumps(noisy)]) + "]", "threshold_cases")
    for i in range(1000):
        prefix = rng.choice(["[" * 4990, "[0," * 16664, '"' + "[" * 5001 + '"', ""])
        noise = "".join(rng.choice(alphabet + " ]0true null") for _ in range(rng.randrange(180)))
        verify(prefix + noise + rng.choice(['"', "\\", "", "]" * 40]), "lexical_mutations")
    return {"seed": 260913, "all_passed": True, "counts": counts, "total": sum(counts.values()),
            "large_valid_counts": samples,
            "limits": "Proposal and production outcomes compared with an independently implemented lexical state machine. Malformed fragments only test structural accounting; grammar remains the standard parser's responsibility."}


def rejection_memory(raw):
    encoded = raw.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    size = len(encoded)
    del encoded
    gc.collect()
    tracemalloc.start()
    try:
        solve_json(raw)
    except ValidationError as error:
        rejection = str(error)
    else:
        raise AssertionError("Expected schema or structural rejection")
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"input_utf8_bytes": size, "sha256": digest, "tracemalloc_peak_bytes": peak, "rejection": rejection}


def matrix(runtimes):
    results = []
    for executable in runtimes:
        version = subprocess.run([executable, "-S", "--version"], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        run = {"version": version, "executable": executable, "suites": []}
        log = []
        for filename in ("test_core.py", "test_independent.py", "test_json_guard.py"):
            start = time.perf_counter()
            completed = subprocess.run([executable, "-S", "-m", "unittest", "discover", "-s", "tests", "-p", filename, "-v"],
                                       cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
                                       env=SUBPROCESS_ENV)
            output = completed.stdout + completed.stderr
            match = re.search(r"Ran (\d+) tests? in", output)
            run["suites"].append({"name": filename, "passed": completed.returncode == 0,
                                  "tests": int(match.group(1)) if match else None,
                                  "wall_seconds": time.perf_counter() - start, "exit_code": completed.returncode})
            log.append(filename + "\n" + output)
        name = "json_guard_" + version.lower().replace(" ", "_").replace(".", "") + ".log"
        (ROOT / "evidence/verification" / name).write_text("\n".join(log), encoding="utf-8")
        run["log"] = "evidence/verification/" + name
        run["all_passed"] = all(suite["passed"] for suite in run["suites"])
        print(version, run["suites"], flush=True)
        results.append(run)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", action="append", dest="runtimes")
    args = parser.parse_args()
    source_files = ["vertice/__init__.py", "vertice/graph.py", "vertice/dijkstra.py", "vertice/codec.py", "vertice/cli.py", "server.py"]
    baseline_files = ["evidence/profiling/json_memory.json", "evidence/profiling/import_profile.json", "scripts/profile_import.py", "scripts/profile_json_memory.py"]
    protected = {name: sha(ROOT / name) for name in source_files + baseline_files}
    baseline = json.loads((ROOT / "evidence/profiling/json_memory.json").read_text(encoding="utf-8"))
    count = (MAX_JSON_BYTES - 2) // 3
    hostile = "[" + ",".join(["{}"] * count) + "]"
    observed = rejection_memory(hostile)
    before = baseline["max_payload"]
    if observed["sha256"] != before["sha256"] or observed["input_utf8_bytes"] != before["bytes"]:
        raise AssertionError("Memory comparison must use exactly the preserved baseline payload")
    residual = {
        "field_object_below_punctuation_limit": rejection_memory("{" + ",".join(f'"key{i}":"🧭"' for i in range(24999)) + "}"),
        "decimals_below_punctuation_limit": rejection_memory("[" + ",".join(["1.23456789"] * 50000) + "]"),
    }
    equivalence = check_equivalence()
    response_checks = []
    for file in sorted((ROOT / "examples").glob("*.json")):
        graph = json.loads(file.read_text(encoding="utf-8"))
        request = json.dumps({"graph": graph, "source": graph["nodes"][0]["id"], "target": graph["nodes"][-1]["id"]})
        old = json.loads(solve_json(request))
        new = solve_payload(load_json(request))
        encode = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        if encode(old) != encode(new):
            raise AssertionError("Response serialization changed")
        response_checks.append({"example": file.name, "identical_bytes": True, "sha256": hashlib.sha256(encode(new)).hexdigest()})
    runtimes = matrix(args.runtimes or [sys.executable])
    web = subprocess.run([sys.executable, "scripts/check_web_core.py"], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", timeout=10, env=SUBPROCESS_ENV)
    unchanged = protected == {name: sha(ROOT / name) for name in protected}
    if not unchanged:
        raise AssertionError("Core/server or preserved baseline changed during this verification")
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "python_for_memory": sys.version,
        "status": "integrated", "all_passed": all(run["all_passed"] for run in runtimes) and web.returncode == 0,
        "source_sha256": sha(Path(__file__)), "test_source_sha256": sha(ROOT / "tests/test_json_guard.py"),
        "protected_sha256": protected, "protected_unchanged": unchanged,
        "limits": {"json_bytes": MAX_JSON_BYTES, "containers": MAX_JSON_CONTAINERS, "punctuation": MAX_JSON_PUNCTUATION},
        "memory": {"baseline_source": "evidence/profiling/json_memory.json", "baseline_python": baseline["python"],
                   "before": before, "after": observed, "reduction_percent": (1 - observed["tracemalloc_peak_bytes"] / before["tracemalloc_peak_bytes"]) * 100,
                   "residual_examples": residual,
                   "interpretation": "Before is the preserved historical measurement, not a rerun in the current environment. Identical input bytes and SHA-256. Python allocation peaks are not process RSS, browser RAM, a general upper bound or a benchmark. Existing baseline files were not overwritten."},
        "equivalence": equivalence, "matrix": runtimes, "http_serialization_byte_equivalence": response_checks,
        "http_scope": "The applied server calls solve_payload(load_json(text)) and retains _json. This check compares serialized bodies locally; it is not an HTTP request suite or a deployment check.",
        "web_core_sync": {"passed": web.returncode == 0, "message": (web.stdout + web.stderr).strip()},
    }
    (ROOT / "evidence/verification/json_guard.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_passed": report["all_passed"], "memory_after": observed, "residual": residual, "equivalence": equivalence["counts"], "core_unchanged": unchanged}, ensure_ascii=True, indent=2))
    if not report["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
