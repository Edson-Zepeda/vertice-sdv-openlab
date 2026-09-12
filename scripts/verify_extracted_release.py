"""Run the actual delivered ZIP without installed Python packages.

The ZIP, checksum and receipt are read-only inputs. Evidence is written outside
the checkout. Only an automatically created temporary fixture is extracted and
executed; its loopback server is always stopped before fixture cleanup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import time
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "VerticeSDV/"
FIXTURE_PREFIX = "Vértice entrega extraída con espacios-"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package, output = args.package.resolve(), args.output.resolve()
    protected = (package, package.with_suffix(".receipt.json"), package.with_suffix(".sha256"))
    # Validate before input reads, fixture creation, process startup or writes.
    if package.suffix.lower() != ".zip":
        parser.error("The package must be a .zip file.")
    if output.suffix.lower() != ".json" or output.is_relative_to(ROOT):
        parser.error("Save JSON evidence outside the source checkout.")
    if any(output == path.resolve() or
           (output.exists() and path.exists() and output.samefile(path)) for path in protected):
        parser.error("Evidence must not replace the ZIP, receipt or checksum.")

    report = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": [], "errors": [],
              "scope": "Actual local ZIP integrity, extraction and runtime smoke on the recorded interpreter; no browser, physical or public-release verification.",
              "script_sha256": sha(Path(__file__).read_bytes()), "python": sys.version,
              "package": str(package), "commands": []}
    child = child_out = child_err = temporary = base = None
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONSAFEPATH"):
        environment.pop(name, None)
    environment.update(PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")

    def check(name, passed, **details):
        report["checks"].append({"name": name, "passed": bool(passed), **details})
        if not passed:
            raise AssertionError(name)

    def command(name, arguments, cwd):
        result = subprocess.run(arguments, cwd=cwd, env=environment, capture_output=True,
                                encoding="utf8", errors="replace", timeout=45)
        report["commands"].append({"name": name, "arguments": [str(arg) for arg in arguments],
                                   "exit_code": result.returncode, "stdout": result.stdout[-6000:],
                                   "stderr": result.stderr[-3000:]})
        check(name, result.returncode == 0)
        return result.stdout.strip()

    try:
        originals = {path: path.read_bytes() for path in protected}
        data, receipt = originals[package], json.loads(originals[protected[1]])
        checksum = originals[protected[2]].decode("utf8")
        package_hash = sha(data)
        check("receipt_matches_exact_clean_zip", receipt["sha256"] == package_hash
              and receipt["bytes"] == len(data) and receipt["source_dirty"] is False)
        check("checksum_matches_zip_and_filename", checksum == f"{package_hash}  {package.name}\n")
        report.update(package_sha256=package_hash, package_bytes=len(data), source_revision=receipt["source_revision"])
        with zipfile.ZipFile(package) as archive:
            check("all_archive_crc_valid", archive.testzip() is None)
            manifest = json.loads(archive.read(PREFIX + "MANIFEST.json"))
            check("manifest_identifies_clean_source", manifest["source_revision"] == receipt["source_revision"]
                  and bool(re.fullmatch(r"[0-9a-f]{40}", manifest["source_revision"]))
                  and manifest["source_dirty"] is False and manifest["release_ready"] is True)
            rows = manifest["files"]
            names = [PREFIX + row["path"] for row in rows]
            expected = set(names) | {PREFIX + "MANIFEST.json"}
            check("manifest_covers_archive_exactly", len(names) == len(set(names))
                  and len({name.casefold() for name in expected}) == len(expected)
                  and archive.namelist().count(PREFIX + "MANIFEST.json") == 1
                  and len(archive.namelist()) == len(expected) and set(archive.namelist()) == expected
                  and receipt["files"] == len(rows), files=len(rows))
            contents = {}
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                invalid = (not item.filename.startswith(PREFIX) or path.is_absolute()
                           or str(path) != item.filename or ".." in path.parts
                           or any(character in '\\<>:"|?*' or ord(character) < 32 for character in item.filename)
                           or item.is_dir() or stat.S_ISLNK(item.external_attr >> 16))
                if invalid:
                    raise ValueError("Unsafe archive member: " + repr(item.filename))
                for part in path.parts:
                    if part.endswith((".", " ")) or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?", part):
                        raise ValueError("Nonportable archive member: " + repr(item.filename))
                contents[item.filename] = archive.read(item)
            mismatches = [row["path"] for row in rows if sha(contents[PREFIX + row["path"]]) != row["sha256"]
                          or len(contents[PREFIX + row["path"]]) != row["bytes"]]
            check("every_zip_file_matches_manifest", not mismatches, mismatches=mismatches)

        temporary = tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX)
        base = Path(temporary.name).resolve()
        check("owned_fixture_is_external_and_has_spaces_and_accents", base.parent == Path(tempfile.gettempdir()).resolve()
              and not base.is_relative_to(ROOT) and base.name.startswith(FIXTURE_PREFIX)
              and " " in base.name and "é" in base.name)
        report["fixture_directory"] = str(base)
        for name, body in contents.items():
            destination = base.joinpath(*PurePosixPath(name).parts).resolve()
            if not destination.is_relative_to(base):
                raise ValueError("Archive member escapes its fixture.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        extracted = base / "VerticeSDV"
        check("extracted_bytes_match_every_archive_member", all(base.joinpath(*PurePosixPath(name).parts).read_bytes() == body
                                                               for name, body in contents.items()))
        python = [sys.executable, "-S", "-B"]
        command("extracted_server_check_without_site_packages", [*python, str(extracted / "server.py"), "--check"], base)
        command("extracted_web_core_integrity", [*python, str(extracted / "scripts/check_web_core.py")], base)
        graph = json.loads((extracted / "examples/desvio.json").read_text(encoding="utf8"))
        validation = command("extracted_cli_validate", [*python, "-m", "vertice.cli", "validate", "examples/desvio.json"], extracted)
        check("cli_validates_supplied_graph_counts", validation == f'Grafo válido: {len(graph["nodes"])} nodos, {len(graph["edges"])} conexiones.')
        solved = json.loads(command("extracted_cli_solve", [*python, "-m", "vertice.cli", "solve", "examples/desvio.json",
                                                          "--source", "S", "--target", "T", "--json"], extracted))
        check("cli_returns_known_cost_and_route", solved["status"] == "ok" and solved["cost"] == "11"
              and solved["path"] == ["S", "B", "D", "E", "T"])
        if os.name == "nt":
            command("extracted_windows_launcher", ["cmd", "/d", "/c", "Iniciar.cmd", "--check"], extracted)

        stdout_path, stderr_path = base / "server.stdout.txt", base / "server.stderr.txt"
        child_out, child_err = stdout_path.open("wb"), stderr_path.open("wb")
        startup = "from server import LocalServer; s=LocalServer(('127.0.0.1',0)); print(s.server_port,flush=True); s.serve_forever(poll_interval=.1)"
        child = subprocess.Popen([*python, "-c", startup], cwd=extracted, env=environment,
                                 stdin=subprocess.DEVNULL, stdout=child_out, stderr=child_err,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            port_text = stdout_path.read_text(encoding="utf8").strip()
            if port_text:
                break
            if child.poll() is not None:
                raise RuntimeError("Extracted server exited: " + stderr_path.read_text(encoding="utf8"))
            time.sleep(.05)
        else:
            raise TimeoutError("Extracted server did not announce its port.")
        port = int(port_text.splitlines()[0])
        check("server_uses_own_random_loopback_port", 0 < port <= 65535 and port != 8770, port=port)
        report["server"] = {"pid": child.pid, "port": port, "site_packages_disabled": True}

        def request(method, path, body=None, headers=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
            try:
                connection.request(method, path, body=body, headers={"Connection": "close", **(headers or {})})
                response = connection.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                connection.close()

        status, headers, body = request("GET", "/api/health")
        health = json.loads(body)
        expected_core = {name: sha((extracted / "vertice" / name).read_bytes())
                         for name in ("__init__.py", "graph.py", "dijkstra.py", "codec.py")}
        check("http_health_identifies_exact_python_core", status == 200 and health.get("project") == "vertice-sdv"
              and health.get("engine") == "python" and health.get("core") == expected_core, core=expected_core)
        payload = json.dumps({"graph": graph, "source": "S", "target": "T", "trace": True}).encode("utf8")
        status, headers, body = request("POST", "/api/solve", payload, {"Content-Type": "application/json"})
        result = json.loads(body)
        check("http_solves_known_graph_with_actual_trace", status == 200 and result["status"] == "ok"
              and result["cost"] == "11" and result["path"] == ["S", "B", "D", "E", "T"] and len(result["trace"]) == 43)
        status, headers, body = request("GET", "/docs/VerticeSDV_Informe.pdf")
        pdf = contents[PREFIX + "web/docs/VerticeSDV_Informe.pdf"]
        check("http_pdf_equals_manifest_bytes_and_document_copy", status == 200 and body == pdf
              and pdf == contents[PREFIX + "docs/VerticeSDV_Informe.pdf"], sha256=sha(pdf), bytes=len(pdf))
        media = contents[PREFIX + "web/media/VerticeSDV_Demo.mp4"]
        status, headers, body = request("GET", "/media/VerticeSDV_Demo.mp4", headers={"Range": "bytes=1024-2047"})
        check("http_media_range_is_206_with_exact_bytes", status == 206 and body == media[1024:2048]
              and headers.get("Content-Range") == f"bytes 1024-2047/{len(media)}", sha256=sha(media), bytes=len(media))
        check("extracted_files_unchanged_by_execution", all(base.joinpath(*PurePosixPath(name).parts).read_bytes() == body
                                                          for name, body in contents.items()))
        check("original_zip_and_sidecars_unchanged", all(path.read_bytes() == body for path, body in originals.items()))
    except Exception as error:
        report["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        if child is not None:
            try:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)
                report.setdefault("server", {})["owned_process_stopped"] = child.poll() is not None
            except Exception as error:
                report["errors"].append(f"Server cleanup: {type(error).__name__}: {error}")
        for handle in (child_out, child_err):
            if handle is not None:
                handle.close()
        if temporary is not None:
            try:
                if base != Path(temporary.name).resolve() or base.parent != Path(tempfile.gettempdir()).resolve() or not base.name.startswith(FIXTURE_PREFIX):
                    raise ValueError("Refusing cleanup of an unrecognized fixture.")
                temporary.cleanup()
                report["owned_fixture_removed"] = not base.exists()
            except Exception as error:
                report["errors"].append(f"Fixture cleanup: {type(error).__name__}: {error}")
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["passed"] = not report["errors"] and bool(report["checks"]) and all(row["passed"] for row in report["checks"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"passed": report["passed"], "checks": len(report["checks"]), "errors": report["errors"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
