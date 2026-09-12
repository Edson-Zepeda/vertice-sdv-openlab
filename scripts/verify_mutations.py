"""Bounded semantic mutation audit against existing independent assertions.

Each candidate runs from its own temporary source tree. Production is not
patched, imported or served by a mutant. This is a sensitivity check, not a
proof of correctness or an exhaustive mutation-testing campaign.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 20
MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
JOB_HANDLE = None


MUTANTS = [
    {
        "id": "stop_when_discovered", "file": "vertice/dijkstra.py",
        "description": "Priorizar y finalizar el destino inmediatamente después de descubrirlo.",
        "old": '                emit("relax", source=node, target=neighbor, edge=edge.id,\n                     old_cost=decimal_or_none(previous), new_cost=canonical_decimal(candidate))',
        "new": '                emit("relax", source=node, target=neighbor, edge=edge.id,\n                     old_cost=decimal_or_none(previous), new_cost=canonical_decimal(candidate))\n                if neighbor == target:\n                    heap = [(candidate, neighbor)]\n                    break',
        "checks": ["named:cheaper_detour"],
    },
    {
        "id": "keep_first_predecessor", "file": "vertice/dijkstra.py",
        "description": "Mejorar la distancia sin sustituir un predecesor descubierto antes.",
        "old": "                predecessors[neighbor] = (node, edge.id)",
        "new": "                predecessors.setdefault(neighbor, (node, edge.id))",
        "checks": ["named:cheaper_detour"],
    },
    {
        "id": "allow_negative_numeric_weight", "file": "vertice/graph.py",
        "description": "Omitir el rechazo de pesos numéricos negativos.",
        "old": "if not result.is_finite() or result < 0 or result > MAX_WEIGHT:",
        "new": "if not result.is_finite() or result > MAX_WEIGHT:",
        "checks": ["method:ValidationBoundaryTests.test_invalid_weights_are_explicitly_rejected"],
    },
    {
        "id": "sum_through_float", "file": "vertice/dijkstra.py",
        "description": "Realizar la suma mediante float antes de convertir de nuevo a Decimal.",
        "old": "                candidate = cost + edge.weight",
        "new": "                candidate = Decimal(str(float(cost) + float(edge.weight)))",
        "checks": ["named:decimal_exact", "named:large_exact"],
    },
    {
        "id": "close_when_enqueued", "file": "vertice/dijkstra.py",
        "description": "Marcar cada vecino como cerrado al encolarlo, antes de extraer el mínimo.",
        "old": "                heapq.heappush(heap, (candidate, neighbor))",
        "new": "                heapq.heappush(heap, (candidate, neighbor))\n                closed.add(neighbor)",
        "checks": ["named:cheaper_detour"],
    },
    {
        "id": "ignore_direction", "file": "vertice/graph.py",
        "description": "Tratar como no dirigido un grafo que declara dirección.",
        "old": "        self._directed = directed",
        "new": "        self._directed = False",
        "checks": ["named:directed_no_reverse"],
    },
    {
        "id": "unreachable_cost_zero", "file": "vertice/dijkstra.py",
        "description": "Devolver costo cero cuando no existe una ruta.",
        "old": "        final_cost = decimal_or_none(distances[target]) if found else None",
        "new": '        final_cost = decimal_or_none(distances[target]) if found else "0"',
        "checks": ["named:disconnected", "named:single_node"],
    },
    {
        "id": "neighbors_in_insertion_order", "file": "vertice/graph.py",
        "description": "Eliminar el orden de vecinos y dejar que el orden de importación altere la traza.",
        "old": "sorted(self._adjacency[node_id].items())",
        "new": "self._adjacency[node_id].items()",
        "checks": ["method:IndependentAlgorithmTests.test_input_order_does_not_change_tie_route_or_trace"],
    },
    {
        "id": "replace_on_equal_cost", "file": "vertice/dijkstra.py",
        "description": "Reemplazar un predecesor también ante costos iguales.",
        "old": "candidate >= previous",
        "new": "candidate > previous",
        "checks": ["named:deterministic_tie"],
    },
    {
        "id": "remove_redundant_stale_distance_check", "file": "vertice/dijkstra.py",
        "description": "Quitar la comparación de costo obsoleto y conservar la comprobación del conjunto cerrado.",
        "old": "            if node in closed or cost != distances[node]:",
        "new": "            if node in closed:",
        "checks": ["named:*", "method:IndependentAlgorithmTests.test_decimal_context_cannot_erase_micro_difference", "method:IndependentAlgorithmTests.test_input_order_does_not_change_tie_route_or_trace"],
        "equivalence_reason": "Con pesos no negativos y relajaciones estrictas, una entrada vieja tiene un costo mayor que la entrada que la reemplazó. El heap extrae primero el costo menor para el mismo nodo; cuando extrae la entrada vieja, el nodo ya pertenece al conjunto cerrado. No se insertan duplicados por costo igual. Si se termina antes por el destino, ninguna entrada posterior se procesa. Por ello el otro término de la condición es redundante bajo las invariantes actuales.",
    },
]


def memory_guard():
    """Apply a hard per-process memory limit before importing the copied core."""
    global JOB_HANDLE
    if os.name == "nt":
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        JOB_HANDLE = kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x100 | 0x2000 | 0x8 | 0x2
        limits.BasicLimitInformation.ActiveProcessLimit = 1
        limits.BasicLimitInformation.PerProcessUserTimeLimit = TIMEOUT_SECONDS * 10_000_000
        limits.ProcessMemoryLimit = MEMORY_LIMIT_BYTES
        if not JOB_HANDLE or not kernel.SetInformationJobObject(JOB_HANDLE, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(JOB_HANDLE, kernel.GetCurrentProcess()):
            raise OSError(ctypes.get_last_error(), "Cannot enforce isolated process memory limit")
        return {"kind": "Windows Job Object", "memory_bytes": MEMORY_LIMIT_BYTES, "cpu_seconds": TIMEOUT_SECONDS, "processes": 1}
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_SECONDS, TIMEOUT_SECONDS))
    return {"kind": "RLIMIT_AS and RLIMIT_CPU", "memory_bytes": MEMORY_LIMIT_BYTES, "cpu_seconds": TIMEOUT_SECONDS}


def worker(worker_root, spec_path):
    guard = memory_guard()
    copied_root = Path(worker_root).resolve()
    sys.path.insert(0, str(copied_root))
    sys.path.insert(0, str(copied_root / "tests"))
    import copy
    import unittest
    import vertice
    import test_independent
    from independent_oracle import named_cases
    from vertice.codec import solve_payload

    loaded = Path(vertice.__file__).resolve()
    if not loaded.is_relative_to(copied_root):
        raise AssertionError("Mutant attempted to import production")
    selectors = json.loads(Path(spec_path).read_text(encoding="utf-8"))["checks"]
    checks = []
    cases = {case["id"]: case for case in named_cases()}
    for selector in selectors:
        if selector == "named:*":
            chosen = [f"named:{name}" for name in cases]
        else:
            chosen = [selector]
        for chosen_selector in chosen:
            item = {"selector": chosen_selector}
            start = time.perf_counter()
            if chosen_selector.startswith("named:"):
                case = cases[chosen_selector.split(":", 1)[1]]
                item["input"] = case["payload"]
                item["expected"] = case["expected"]
                try:
                    result = solve_payload(copy.deepcopy(case["payload"]))
                    item["actual"] = {key: result[key] for key in ("status", "path", "edge_path", "cost", "settled", "stats")}
                    # Reuse the real independent suite's entire black-box assertion,
                    # including integer Bellman-Ford and step-by-step trace invariants.
                    test = test_independent.IndependentAlgorithmTests("test_named_contract_scenarios")
                    test.assert_result(case["payload"], result)
                    if "path" in case["expected"]:
                        test.assertEqual(result["path"], case["expected"]["path"])
                except AssertionError as error:
                    item.update(status="assertion_failure", message=str(error)[:1600], traceback=traceback.format_exc()[-2400:])
                except Exception as error:
                    item.update(status="runtime_error", message=f"{type(error).__name__}: {error}"[:1600], traceback=traceback.format_exc()[-2400:])
                else:
                    item["status"] = "passed"
            else:
                class_name, method = chosen_selector.split(":", 1)[1].split(".")
                test = getattr(test_independent, class_name)(method)
                result = unittest.TestResult()
                test.run(result)
                item.update(status="assertion_failure" if result.failures else "runtime_error" if result.errors else "passed",
                            failures=[{"test": str(case), "message": message[-2400:]} for case, message in result.failures],
                            errors=[{"test": str(case), "message": message[-2400:]} for case, message in result.errors])
            item["elapsed_seconds"] = time.perf_counter() - start
            checks.append(item)
    print(json.dumps({"guard": guard, "loaded_core": str(loaded), "checks": checks}, ensure_ascii=True))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_isolated(workspace, name, checks, mutation=None):
    isolated = workspace / name
    (isolated / "vertice").mkdir(parents=True)
    (isolated / "tests").mkdir()
    for file in sorted((ROOT / "vertice").glob("*.py")):
        shutil.copyfile(file, isolated / "vertice" / file.name)
    for name in ("test_independent.py", "independent_oracle.py"):
        shutil.copyfile(ROOT / "tests" / name, isolated / "tests" / name)
    if mutation:
        path = isolated / mutation["file"]
        source = path.read_text(encoding="utf-8")
        if source.count(mutation["old"]) != 1:
            raise AssertionError(f"Expected unique mutation anchor: {mutation['id']}")
        changed = source.replace(mutation["old"], mutation["new"], 1)
        compile(changed, str(path), "exec")
        path.write_text(changed, encoding="utf-8", newline="")
        (isolated / "mutation.patch").write_text("".join(difflib.unified_diff(source.splitlines(True), changed.splitlines(True), fromfile="a/" + mutation["file"], tofile="b/" + mutation["file"])), encoding="utf-8")
    spec = isolated / "selection.json"
    spec.write_text(json.dumps({"checks": checks}), encoding="utf-8")
    process = [sys.executable, "-I", "-S", str(Path(__file__).resolve()), "--worker-root", str(isolated), "--spec", str(spec)]
    start = time.perf_counter()
    try:
        result = subprocess.run(process, cwd=isolated, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", timeout=TIMEOUT_SECONDS, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except subprocess.TimeoutExpired:
        return {"classification": "inconclusive_timeout", "wall_seconds": time.perf_counter() - start,
                "reason": "Process exceeded the 20 second wall-clock bound and was killed."}
    if result.returncode != 0:
        return {"classification": "inconclusive_process_failure", "wall_seconds": time.perf_counter() - start,
                "returncode": result.returncode, "stderr": result.stderr[-3000:], "stdout": result.stdout[-1000:]}
    payload = json.loads(result.stdout)
    payload["wall_seconds"] = time.perf_counter() - start
    payload["mutated_source_sha256"] = sha(isolated / mutation["file"]) if mutation else None
    failures = [check for check in payload["checks"] if check["status"] != "passed"]
    payload["classification"] = "detected_by_assertion" if any(check["status"] == "assertion_failure" for check in failures) else "detected_by_runtime_error" if failures else "survived_selection"
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-root")
    parser.add_argument("--spec")
    args = parser.parse_args()
    if args.worker_root:
        worker(args.worker_root, args.spec)
        return
    protected = list(sorted((ROOT / "vertice").glob("*.py"))) + [ROOT / name for name in ("server.py", "web/app.js", "web/engine.js", "web/index.html", "web/style.css", "tests/test_independent.py", "tests/independent_oracle.py")]
    before = {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path) for path in protected}
    temporary_root = ROOT / "tmp"
    temporary_root.mkdir(exist_ok=True)
    # Kept for inspection. No recursive deletion or cleanup of unrelated paths.
    workspace = Path(tempfile.mkdtemp(prefix="mutation-audit-", dir=temporary_root))
    baseline_checks = list(dict.fromkeys(selector for mutant in MUTANTS for selector in mutant["checks"] if selector != "named:*"))
    baseline_checks.insert(0, "named:*")
    baseline = run_isolated(workspace, "baseline", baseline_checks)
    if baseline["classification"] != "survived_selection":
        raise AssertionError("Unmodified isolated baseline must pass: " + json.dumps(baseline, ensure_ascii=True))
    rows = []
    for mutant in MUTANTS:
        outcome = run_isolated(workspace, mutant["id"], mutant["checks"], mutant)
        if outcome["classification"] == "survived_selection" and mutant.get("equivalence_reason"):
            outcome["classification"] = "equivalent_under_contract"
        rows.append({"id": mutant["id"], "description": mutant["description"], "file": mutant["file"],
                     "source_change": {"old": mutant["old"], "new": mutant["new"]},
                     "equivalence_reason": mutant.get("equivalence_reason"), **outcome})
    after = {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path) for path in protected}
    if before != after:
        raise AssertionError("Protected production/test files changed during isolated audit")
    counts = {kind: sum(row["classification"] == kind for row in rows) for kind in sorted({row["classification"] for row in rows})}
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
              "method": "Ten hand-selected semantic mutants, each applied to an isolated source copy; selected assertions copied unmodified from the independent Bellman-Ford suite. No network, browser, worker or running server involvement.",
              "limits": {"wall_seconds_per_subprocess": TIMEOUT_SECONDS, "memory_bytes_per_subprocess": MEMORY_LIMIT_BYTES, "largest_named_graph_nodes": 4,
                         "interpretation": "A selected defect detection count is evidence about this test selection, not a percentage of general correctness. Equivalent candidates are excluded from defect counts. Runtime/process failures and timeouts are reported separately."},
              "isolated_workspace": str(workspace), "production_sha256_before": before, "production_sha256_after": after,
              "source_sha256": sha(Path(__file__)), "protected_files_unchanged": before == after,
              "baseline": baseline, "summary": counts, "mutants": rows}
    destination = ROOT / "evidence" / "verification" / "mutations.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(destination), "summary": counts, "production_unchanged": before == after,
                      "mutants": [{"id": row["id"], "classification": row["classification"], "detected_by": [check["selector"] for check in row.get("checks", []) if check["status"] != "passed"]} for row in rows]}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
