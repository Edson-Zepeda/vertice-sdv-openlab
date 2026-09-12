"""Independent, bounded review of the isolated JSON allocation proposal.

Run directly. This does not modify or monkeypatch the application's loader.
The reference scanner uses a character/state machine instead of quote searching.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import difflib
import gc
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from experiment_json_preflight import preflight
from vertice.codec import load_json, solve_json, solve_payload
from vertice.graph import Graph, ValidationError

OUT = ROOT / "evidence" / "profiling"
RNG = random.Random(260912)
COUNTS = {}
CHECKS = []


def record(group, name, condition):
    COUNTS[group] = COUNTS.get(group, 0) + 1
    if not condition:
        raise AssertionError(f"{group}: {name}")


def reference_counts(raw):
    string = False
    escaped = False
    containers = punctuation = depth = max_depth = 0
    for char in raw:
        if string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                string = False
        elif char == '"':
            string = True
        elif char in "[{":
            containers += 1
            depth += 1
            max_depth = max(max_depth, depth)
        elif char in "}]":
            depth -= 1
        elif char in ",:":
            punctuation += 1
    return containers, punctuation, max_depth


def proposal_rejects(raw):
    try:
        preflight(raw)
    except ValidationError:
        return True
    return False


def verify_scanner(name, raw):
    containers, punctuation, _ = reference_counts(raw)
    record("scanner_equivalence", name,
           proposal_rejects(raw) == (containers > 5000 or punctuation > 50000))


def parse_graph(raw, with_preflight):
    if with_preflight:
        preflight(raw)
    try:
        return ("ok", Graph.from_dict(load_json(raw)).to_dict())
    except ValidationError as error:
        return ("rejected", str(error))


def graph_equivalence(name, raw, expected_ok=True):
    old = parse_graph(raw, False)
    new = parse_graph(raw, True)
    record("graph_equivalence", name, old == new and (old[0] == "ok") == expected_ok)
    verify_scanner(name, raw)


def random_label(length=None):
    alphabet = "abcXYZ09 áéíóúΩ漢字🧭♟[{}],:\\\"/"
    return "".join(RNG.choice(alphabet) for _ in range(length if length is not None else RNG.randrange(81)))


def random_graph():
    n = RNG.randrange(1, 18)
    directed = bool(RNG.getrandbits(1))
    nodes = []
    for index in range(n):
        node = {"id": f"N{index}"}
        for key, value in (("label", random_label()), ("x", RNG.uniform(-10000, 10000)),
                           ("y", RNG.randrange(-10000, 10001))):
            if RNG.getrandbits(1):
                node[key] = value
        nodes.append(node)
    pairs = [(a, b) for a in range(n) for b in range(n) if directed or a <= b]
    RNG.shuffle(pairs)
    edges = []
    for i, (a, b) in enumerate(pairs[:RNG.randrange(min(50, len(pairs)) + 1)]):
        weight = RNG.choice(["0", "0.000001", "1000000000000", "1.250000", RNG.randrange(100)])
        edges.append({"id": f"E{i}", "source": f"N{a}", "target": f"N{b}", "weight": weight})
    return {"schema_version": 1, "directed": directed, "nodes": nodes, "edges": edges}


def median_ms(callback, n=7):
    callback()
    samples = []
    for _ in range(n):
        start = time.perf_counter_ns()
        callback()
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return {"samples_ms": samples, "median_ms": statistics.median(samples)}


def measure_guarded_rejection(raw):
    gc.collect()
    tracemalloc.start()
    start = time.perf_counter_ns()
    try:
        # Match the intended integration point, after the loader's UTF-8 guard.
        if len(raw.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValidationError("size")
        preflight(raw)
        solve_json(raw)
    except ValidationError as error:
        rejection = str(error)
    else:
        raise AssertionError("Expected rejection")
    elapsed = (time.perf_counter_ns() - start) / 1e6
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"input_utf8_bytes": len(raw.encode("utf-8")), "peak_python_bytes": peak,
            "instrumented_ms": elapsed, "rejection": rejection,
            "structural_counts": reference_counts(raw)}


def main():
    production = ["vertice/codec.py", "vertice/graph.py", "server.py", "web/app.js", "web/engine.js", "web/index.html", "web/style.css"]
    hashes_before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in production}

    # Variations include both raw UTF-8 and escaped Unicode, optional fields,
    # legal punctuation inside strings, full label length, and decimal limits.
    for i in range(350):
        graph = random_graph()
        for ascii_only in (False, True):
            for pretty in (False, True):
                raw = json.dumps(graph, ensure_ascii=ascii_only, indent=2 if pretty else None)
                graph_equivalence(f"random {i} ascii={ascii_only} pretty={pretty}", raw)

    fixture = json.loads((OUT / "import_500_4000.json").read_text(encoding="utf-8"))
    maximum = fixture["graph"]
    extremes = []
    for label in ("[" * 80, "," * 80, "\\\"" * 40, "🧭" * 80, "漢字Ω [{,:}]\\\"" * 5, "" ):
        graph = deepcopy(maximum)
        for node in graph["nodes"]:
            node["label"] = label
        for ascii_only in (False, True):
            raw = json.dumps(graph, ensure_ascii=ascii_only, separators=(",", ":"))
            graph_equivalence(f"max label {label[:8]!r} ascii={ascii_only}", raw)
            request = {"graph": graph, "source": graph["nodes"][0]["id"], "target": graph["nodes"][-1]["id"], "trace": True}
            request_raw = json.dumps(request, ensure_ascii=ascii_only, separators=(",", ":"))
            verify_scanner("maximum request", request_raw)
            extremes.append({"label_prefix": repr(label[:8]), "ascii": ascii_only,
                             "bytes": len(request_raw.encode()), "counts": reference_counts(request_raw),
                             "raw_brackets": request_raw.count("[") + request_raw.count("{"),
                             "raw_punctuation": request_raw.count(",") + request_raw.count(":"),
                             "preflight": median_ms(lambda: preflight(request_raw), 5)})

    base = {"schema_version": 1, "directed": True, "nodes": [{"id": "A"}, {"id": "B"}],
            "edges": [{"id": "E", "source": "A", "target": "B", "weight": "REPLACE"}]}
    values = [
        ('"0"', True), ('"0.' + "0" * 98 + '"', True),
        ('"1000000000000.' + "0" * 86 + '"', True),
        ('0.000001', True), ('1e-6', True), ('1e12', True), ('0e999999', True),
        ('-0.0', True), ('"0.0000001"', False), ('"1e-6"', False),
        ('1000000000001', False), ('-1', False), ('true', False), ('null', False),
        ('1' * 101, False), ('1e9999999999999999999999999999', False),
        ('"' + "0" * 101 + '"', False), ('Infinity', False), ('NaN', False),
    ]
    for i, (token, valid) in enumerate(values):
        raw = json.dumps(base).replace('"REPLACE"', token)
        graph_equivalence(f"numeric boundary {i}", raw, valid)

    # Exact structural limits with strings that force the slower branch and
    # many escaped quote/backslash combinations; counts come from independent FSM.
    for objects in (4998, 4999, 5000, 5001, 6000):
        for label in ("", "[" * 6000, "\\\"" * 3000, "," * 50010):
            raw = "[" + ",".join(["{}"] * objects + [json.dumps(label)]) + "]"
            verify_scanner(f"containers {objects} label={label[:2]!r}", raw)
    for numbers in (49999, 50000, 50001, 50002, 60000):
        for label in ("", "\\", '"', "🧭[{,:}]\\\"" * 1000):
            raw = "[" + ",".join(["0"] * numbers + [json.dumps(label)]) + "]"
            verify_scanner(f"punctuation {numbers} label={label[:2]!r}", raw)
    alphabet = '[{}],:"\\0true null 🧭'
    for i in range(2400):
        # Mutated fragments deliberately need not be valid JSON. The parser is
        # still responsible for grammar; this only compares lexical limits.
        noise = "".join(RNG.choice(alphabet) for _ in range(RNG.randrange(200)))
        prefix = RNG.choice(["[" * 4990, "[0," * 16664, '"' + "[" * 5001 + '"', ""])
        raw = prefix + noise + RNG.choice(["", '"', "\\", "]" * 20])
        verify_scanner(f"bounded lexical fuzz {i}", raw)

    # Values with many digits are intentionally retained: punctuation protection
    # is an allocation reduction, not a universal 2 MiB peak-memory promise.
    hostile = {
        "699050_empty_objects": "[" + ",".join(["{}"] * 699050) + "]",
        "500000_integers": "[" + ",".join(["0"] * 500000) + "]",
        "allowed_50000_decimals": "[" + ",".join(["1.23456789"] * 50000) + "]",
        "allowed_24999_field_object": "{" + ",".join(f'"key{i}":"🧭"' for i in range(24999)) + "}",
        "depth_900": "[" * 900 + "]" * 900,
        "depth_1500": "[" * 1500 + "]" * 1500,
        "unterminated_large_string": '"' + "{}" * 500000,
    }
    hostile_results = {name: measure_guarded_rejection(raw) for name, raw in hostile.items()}

    # Validate the proposed HTTP one-serialization path without modifying Handler.
    http = []
    for file in sorted((ROOT / "examples").glob("*.json")):
        graph = json.loads(file.read_text(encoding="utf-8"))
        if not graph["nodes"]:
            continue
        request = json.dumps({"graph": graph, "source": graph["nodes"][0]["id"], "target": graph["nodes"][-1]["id"]}, ensure_ascii=False)
        old_result = json.loads(solve_json(request))
        new_result = solve_payload(load_json(request))
        old_bytes = json.dumps(old_result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        new_bytes = json.dumps(new_result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        record("http_equivalence", file.name, old_bytes == new_bytes)
        http.append({"name": file.name, "bytes": len(new_bytes), "sha256": hashlib.sha256(new_bytes).hexdigest()})
    server_before = (ROOT / "server.py").read_text(encoding="utf-8")
    server_after = server_before.replace("MAX_JSON_BYTES, solve_json, load_json", "MAX_JSON_BYTES, solve_payload, load_json").replace("result = json.loads(solve_json(text))", "result = solve_payload(load_json(text))")
    proposal = "".join(difflib.unified_diff(server_before.splitlines(True), server_after.splitlines(True), fromfile="a/server.py", tofile="b/server.py"))
    (OUT / "server_single_serialization.patch").write_text(proposal, encoding="utf-8")
    hashes_after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in production}
    record("freeze", "production unmodified", hashes_before == hashes_after)
    report = {
        "proposal_only": True, "created_utc": datetime.now(timezone.utc).isoformat(), "seed": 260912,
        "python": sys.version, "groups": COUNTS, "checks_passed": sum(COUNTS.values()),
        "all_checks_passed": True, "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reviewed_proposal_sha256": hashlib.sha256((ROOT / "scripts/experiment_json_preflight.py").read_bytes()).hexdigest(),
        "production_sha256": hashes_before, "maximum_variants": extremes, "hostile": hostile_results,
        "http_byte_equivalence": http,
        "limits": "Isolated CPython allocations and seeded cases, not exhaustive Unicode proof, process RSS or real browser measurement. Production and the active endurance server remain unchanged. No universal RAM ceiling follows from punctuation limits. Concurrent browser endurance test can affect timings.",
    }
    (OUT / "json_preflight_review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["checks_passed"], "groups": COUNTS, "hostile": hostile_results, "maximum_variants": extremes}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
