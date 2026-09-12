"""Protect delivery inputs from the release verifier's output argument.

Fixtures live outside the repository. Network access is replaced by a failing
mock, including when deliberately exercising the historical unsafe verifier.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("VERTICE_RELEASE_GUARD_SOURCE", ROOT / "scripts/verify_release.py")).resolve()
loader = importlib.machinery.SourceFileLoader("release_verifier_output_test", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
verifier = importlib.util.module_from_spec(spec)
loader.exec_module(verifier)
SCENARIOS = []


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ReleaseOutputGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="Verificación Vértice externa-")
        self.base = Path(self.temporary.name).resolve()
        self.assertFalse(self.base.is_relative_to(ROOT))
        self.package = self.base / "Entrega Vértice.zip"
        self.receipt = self.package.with_suffix(".receipt.json")
        self.checksum = self.package.with_suffix(".sha256")
        # A deliberately invalid archive reaches the verifier's normal local
        # failure report, without needing to simulate a published release.
        self.package_bytes = b"Isolated invalid ZIP fixture: preserve these bytes.\n"
        self.original = {
            self.package: self.package_bytes,
            self.receipt: (json.dumps({"sha256": digest(self.package_bytes),
                                      "bytes": len(self.package_bytes),
                                      "source_dirty": False,
                                      "source_revision": "a" * 40}) + "\n").encode(),
            self.checksum: (digest(self.package_bytes) + "  " + self.package.name + "\n").encode("utf8"),
        }
        self.restore()

    def tearDown(self):
        # Only delete the exact generated external fixture directory.
        resolved = self.base.resolve()
        self.assertFalse(resolved.is_relative_to(ROOT))
        self.assertEqual(resolved.parent, Path(tempfile.gettempdir()).resolve())
        self.assertTrue(resolved.name.startswith("Verificación Vértice externa-"))
        self.temporary.cleanup()

    def restore(self):
        for path, data in self.original.items():
            path.write_bytes(data)

    def invoke(self, output, *, block_input_reads=False):
        observations = {"output": str(output), "fixture_outside_repository": not self.base.is_relative_to(ROOT)}
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("sys.argv", [str(SOURCE), str(self.package), "--output", str(output)]))
            # Historical snapshots retain the original checkout boundary.
            stack.enter_context(patch.object(verifier, "__file__", str(ROOT / "scripts/verify_release.py")))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            network = stack.enter_context(patch.object(verifier, "fetch", side_effect=AssertionError("Network disabled in output-guard tests")))
            direct_network = stack.enter_context(patch("urllib.request.urlopen", side_effect=AssertionError("Network disabled in output-guard tests")))
            readers = []
            if block_input_reads:
                readers = [stack.enter_context(patch.object(Path, name, side_effect=AssertionError("Input read before output validation")))
                           for name in ("read_bytes", "read_text")]
            try:
                observations["exit"] = verifier.main()
            except SystemExit as error:
                observations["exit"] = error.code
            except Exception as error:
                observations["exception"] = f"{type(error).__name__}: {error}"
            observations["fetch_calls"] = network.call_count
            observations["urlopen_calls"] = direct_network.call_count
            observations["input_read_calls"] = sum(reader.call_count for reader in readers) if block_input_reads else None
        observations["inputs"] = [{"name": path.name, "before_sha256": digest(data),
                                    "after_sha256": digest(path.read_bytes()), "unchanged": path.read_bytes() == data}
                                   for path, data in self.original.items()]
        SCENARIOS.append(observations)
        return observations

    def assert_rejected_and_preserved(self, observed):
        self.assertEqual(observed.get("exit"), 2, observed)
        self.assertNotIn("exception", observed)
        self.assertEqual(observed["fetch_calls"], 0)
        self.assertEqual(observed["urlopen_calls"], 0)
        self.assertTrue(all(item["unchanged"] for item in observed["inputs"]), observed)

    def test_zip_receipt_checksum_and_other_extension_preserve_bytes(self):
        other = self.base / "Existing evidence.txt"
        for output in (self.package, self.receipt, self.checksum, other):
            with self.subTest(output=output.name):
                self.restore()
                other.write_bytes(b"An unrelated existing file must remain intact.\n")
                before_other = other.read_bytes()
                result = self.invoke(output)
                self.assert_rejected_and_preserved(result)
                self.assertEqual(other.read_bytes(), before_other)

    def test_unsafe_output_is_rejected_before_input_reads_or_network(self):
        nested = self.base / "Nested directory"
        nested.mkdir()
        outputs = (self.package, self.receipt, self.checksum, self.base / "wrong.txt",
                   ROOT / "never-created-release-output.json",
                   nested / ".." / self.receipt.name)
        for output in outputs:
            with self.subTest(output=str(output)):
                result = self.invoke(output, block_input_reads=True)
                self.assert_rejected_and_preserved(result)
                self.assertEqual(result["input_read_calls"], 0)

    def test_existing_json_hardlink_to_receipt_preserves_receipt(self):
        alias = self.base / "Receipt alias.json"
        try:
            os.link(self.receipt, alias)
        except OSError as error:
            self.skipTest(f"Hard links unavailable: {error}")
        result = self.invoke(alias, block_input_reads=True)
        self.assert_rejected_and_preserved(result)
        self.assertEqual(result["input_read_calls"], 0)
        self.assertEqual(alias.read_bytes(), self.original[self.receipt])

    def test_json_symlink_to_receipt_resolves_to_protected_input(self):
        alias = self.base / "Receipt symbolic alias.json"
        try:
            alias.symlink_to(self.receipt)
        except OSError as error:
            self.skipTest(f"Symbolic links unavailable: {error}")
        result = self.invoke(alias, block_input_reads=True)
        self.assert_rejected_and_preserved(result)
        self.assertEqual(result["input_read_calls"], 0)

    def test_separate_json_can_record_a_local_failure_without_network(self):
        output = self.base / "Evidence with spaces" / "Verificación.json"
        result = self.invoke(output)
        self.assertEqual(result.get("exit"), 1, result)
        self.assertNotIn("exception", result)
        self.assertEqual(result["fetch_calls"], 0)
        self.assertEqual(result["urlopen_calls"], 0)
        self.assertTrue(all(item["unchanged"] for item in result["inputs"]))
        report = json.loads(output.read_text(encoding="utf8"))
        self.assertFalse(report["passed"])
        self.assertTrue(any("BadZipFile" in value for value in report["errors"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReleaseOutputGuardTests))
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "status": "pass" if result.wasSuccessful() else "fail", "tests": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
              "source": str(SOURCE), "source_sha256": digest(SOURCE.read_bytes()),
              "test_sha256": digest(Path(__file__).read_bytes()), "python": sys.version,
              "scope": "Output protection only; external synthetic files, no network and no published-release validation.",
              "scenarios": SCENARIOS, "test_output": stream.getvalue()}
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({key: report[key] for key in ("status", "tests", "failures", "errors", "skipped")}, ensure_ascii=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
