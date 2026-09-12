"""Verify an exact published commit through packaging, extraction and local HTTP.

This is a delivery snapshot audit, not a release publisher. All clone/package/
extraction files remain under ignored tmp/; application sources are not edited.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import time
import zipfile


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COMMIT = "407cc98f4fded8b00daa7e16c50ebc52dc9b7a5e"
EXPECTED_PDF = "94484e9649de1fe9ec3bfa2800081045639e606ef01028878cbfea7647a30d25"
EXPECTED_VIDEO = "93a64bf31516a2b1027ab91555b459de0afb0ef9aa230d957c0efbf4e38c17eb"
PUBLIC_REPOSITORY = "https://github.com/Edson-Zepeda/vertice-sdv-openlab.git"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default=EXPECTED_COMMIT)
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    checks, commands = [], []
    report = {
        "generated_at": started.isoformat(),
        "status": "running",
        "scope": "Exact published commit before the final 45-minute soak and final publication. This audit does not certify later commits or publish a release.",
        "source_revision": args.commit,
        "source_repository": PUBLIC_REPOSITORY,
        "script_sha256": sha(Path(__file__).read_bytes()),
        "python": sys.version,
        "checks": checks,
        "commands": commands,
    }
    evidence = ROOT / "evidence/delivery/current_snapshot.json"
    environment = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONSAFEPATH"):
        environment.pop(key, None)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    child = None
    child_out = child_err = None

    def check(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            raise AssertionError(f"{name}: {detail}")

    def command(name, arguments, cwd, expected=0, timeout=300):
        result = subprocess.run(arguments, cwd=cwd, env=environment, capture_output=True,
                                encoding="utf8", errors="replace", timeout=timeout)
        commands.append({"name": name, "arguments": [str(v) for v in arguments],
                         "cwd": str(cwd), "exit": result.returncode,
                         "stdout": result.stdout[-6000:], "stderr": result.stderr[-3000:]})
        check(name, result.returncode == expected, {"expected_exit": expected, "exit": result.returncode})
        return result.stdout.strip()

    try:
        (ROOT / "tmp").mkdir(exist_ok=True)
        base = Path(tempfile.mkdtemp(prefix="Auditoría final Vértice con espacios-", dir=ROOT / "tmp")).resolve()
        check("isolated_path_with_spaces_and_accents", base.is_relative_to((ROOT / "tmp").resolve()) and " " in base.name and "é" in base.name, str(base))
        clone = base / "Clon limpio"
        extraction = base / "Entrega extraída"
        first_zip = base / "Vértice revisión uno.zip"
        second_zip = base / "Vértice revisión dos.zip"
        report.update({"base": str(base), "clone": str(clone), "extraction": str(extraction),
                       "review_zip": str(first_zip), "repeated_zip": str(second_zip)})
        command("clone_public_repository", ["git", "clone", "--no-checkout", "--single-branch", "--branch", "main", PUBLIC_REPOSITORY, str(clone)], ROOT, timeout=300)
        command("checkout_exact_commit", ["git", "checkout", "--detach", args.commit], clone)
        revision = command("read_clone_revision", ["git", "rev-parse", "HEAD"], clone)
        check("clone_revision_is_requested", revision == args.commit, revision)
        clean = command("read_clone_status", ["git", "status", "--porcelain"], clone)
        check("clone_is_clean_before_packaging", clean == "", clean)
        for name, expected in [("docs/VerticeSDV_Informe.pdf", EXPECTED_PDF), ("web/media/VerticeSDV_Demo.mp4", EXPECTED_VIDEO)]:
            actual = sha((clone / name).read_bytes())
            check("approved_asset_in_exact_commit:" + name, actual == expected, actual)
        for label, output in [("first", first_zip), ("repeat", second_zip)]:
            stdout = command("package_" + label, [sys.executable, "-S", "-B", "scripts/package_release.py", "--output", str(output)], clone, timeout=300)
            receipt = json.loads(stdout)
            report["receipt_" + label] = receipt
            check("package_" + label + "_source_is_clean_commit", receipt["source_revision"] == args.commit and receipt["source_dirty"] is False, receipt["source_revision"])
            check("package_" + label + "_receipt_hash_matches", receipt["sha256"] == sha(output.read_bytes()), receipt["sha256"])
            checksum = output.with_suffix(".sha256").read_text(encoding="utf8")
            check("package_" + label + "_unicode_checksum", checksum == f'{receipt["sha256"]}  {output.name}\n', checksum.strip())
        package_hash = sha(first_zip.read_bytes())
        check("same_commit_same_zip_bytes", first_zip.read_bytes() == second_zip.read_bytes(), package_hash)
        with zipfile.ZipFile(first_zip) as archive:
            check("all_zip_crc_valid", archive.testzip() is None)
            manifest = json.loads(archive.read("VerticeSDV/MANIFEST.json"))
            report["manifest"] = {key: value for key, value in manifest.items() if key != "files"}
            report["manifest_file_count"] = len(manifest["files"])
            check("manifest_identifies_exact_clean_commit", manifest["source_revision"] == args.commit and manifest["source_dirty"] is False and manifest["release_ready"] is True)
            expected_names = {"VerticeSDV/MANIFEST.json"} | {"VerticeSDV/" + entry["path"] for entry in manifest["files"]}
            check("manifest_covers_every_archive_member", set(archive.namelist()) == expected_names and len(archive.namelist()) == len(expected_names), len(expected_names))
            for name in archive.namelist():
                relative = PurePosixPath(name)
                if relative.is_absolute() or ".." in relative.parts or "\\" in name or not name.startswith("VerticeSDV/"):
                    raise AssertionError("Unsafe extraction path: " + name)
                destination = extraction.joinpath(*relative.parts).resolve()
                if not destination.is_relative_to(extraction.resolve()):
                    raise AssertionError("Escaping extraction path: " + name)
            archive.extractall(extraction)
        extracted = extraction / "VerticeSDV"
        mismatches = []
        for entry in manifest["files"]:
            data = (extracted / entry["path"]).read_bytes()
            if len(data) != entry["bytes"] or sha(data) != entry["sha256"] or data != (clone / entry["path"]).read_bytes():
                mismatches.append(entry["path"])
        check("every_extracted_file_matches_manifest_and_clone", not mismatches, {"files": len(manifest["files"]), "mismatches": mismatches})
        forbidden = [p for p in (".git", "media/render", "node_modules", ".venv", "tmp") if (extracted / p).exists()]
        check("no_git_or_development_cache_in_extraction", not forbidden, forbidden)
        command("extracted_server_check_without_site_packages", [sys.executable, "-S", "-B", str(extracted / "server.py"), "--check"], base)
        command("extracted_core_integrity_from_other_directory", [sys.executable, "-S", "-B", str(extracted / "scripts/check_web_core.py")], base)
        solved = json.loads(command("extracted_cli_solve", [sys.executable, "-S", "-B", "-m", "vertice.cli", "solve", "examples/desvio.json", "--source", "S", "--target", "T", "--json"], extracted))
        check("extracted_cli_cost_and_route", solved["cost"] == "11" and solved["path"] == ["S", "B", "D", "E", "T"], {"cost": solved["cost"], "path": solved["path"]})
        if os.name == "nt":
            command("extracted_windows_launcher", ["cmd", "/d", "/c", "Iniciar.cmd", "--check"], extracted)
        stdout_path, stderr_path = base / "server.stdout.txt", base / "server.stderr.txt"
        child_out = stdout_path.open("wb")
        child_err = stderr_path.open("wb")
        startup = "from server import LocalServer; s=LocalServer(('127.0.0.1',0)); print(s.server_port,flush=True); s.serve_forever(poll_interval=.1)"
        child = subprocess.Popen([sys.executable, "-S", "-B", "-c", startup], cwd=extracted, env=environment,
                                 stdin=subprocess.DEVNULL, stdout=child_out, stderr=child_err,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        deadline = time.monotonic() + 15
        port_text = ""
        while time.monotonic() < deadline:
            port_text = stdout_path.read_text(encoding="utf8").strip()
            if port_text:
                break
            if child.poll() is not None:
                raise RuntimeError("Extracted server failed: " + stderr_path.read_text(encoding="utf8"))
            time.sleep(.05)
        port = int(port_text.splitlines()[0])
        check("server_has_own_random_port", 0 < port <= 65535 and port != 8770, port)
        report["server"] = {"pid": child.pid, "port": port, "cwd": str(extracted), "site_packages_disabled": True}

        def request(method, path, body=None, headers=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
            try:
                connection.request(method, path, body=body, headers=headers or {})
                response = connection.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                connection.close()

        status, headers, data = request("GET", "/api/health")
        health = json.loads(data)
        expected_core = {name: sha((extracted / "vertice" / name).read_bytes())
                         for name in ("__init__.py", "graph.py", "dijkstra.py", "codec.py")}
        check("extracted_http_health", status == 200 and health.get("project") == "vertice-sdv"
              and health.get("engine") == "python" and health.get("core") == expected_core, health)
        graph = json.loads((extracted / "examples/desvio.json").read_text(encoding="utf8"))
        payload = json.dumps({"graph": graph, "source": "S", "target": "T", "trace": True}).encode("utf8")
        status, headers, data = request("POST", "/api/solve", payload, {"Content-Type": "application/json"})
        solution = json.loads(data)
        check("extracted_http_solve_11", status == 200 and solution["cost"] == "11" and solution["path"] == ["S", "B", "D", "E", "T"], {"status": status, "cost": solution.get("cost"), "path": solution.get("path")})
        status, headers, data = request("GET", "/docs/VerticeSDV_Informe.pdf")
        check("extracted_http_pdf_bytes", status == 200 and sha(data) == EXPECTED_PDF and data == (extracted / "docs/VerticeSDV_Informe.pdf").read_bytes(), {"status": status, "sha256": sha(data), "bytes": len(data), "content_type": headers.get("Content-Type")})
        media = (extracted / "web/media/VerticeSDV_Demo.mp4").read_bytes()
        status, headers, data = request("GET", "/media/VerticeSDV_Demo.mp4", headers={"Range": "bytes=1024-2047"})
        check("extracted_http_media_range_206_exact_bytes", status == 206 and data == media[1024:2048] and headers.get("Content-Range") == f"bytes 1024-2047/{len(media)}", {"status": status, "bytes": len(data), "content_range": headers.get("Content-Range")})
        check("video_remains_byte_identical_to_approved_export", sha(media) == EXPECTED_VIDEO, {"sha256": sha(media), "technical_checks_repeated": False, "reason": "The MP4 is byte-identical to the approved export. This audit checks transport and extraction; prior source-provenance checks retain their original scope."})
        check("clone_remains_clean", command("clone_status_after_audit", ["git", "status", "--porcelain"], clone) == "")
        unchanged = [entry["path"] for entry in manifest["files"] if sha((extracted / entry["path"]).read_bytes()) != entry["sha256"]]
        check("extracted_files_unchanged_by_execution", not unchanged, unchanged)
        report["status"] = "pass"
    except Exception as error:
        report["status"] = "fail"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if child is not None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)
            report.setdefault("server", {})["owned_process_stopped"] = child.poll() is not None
        if child_out is not None:
            child_out.close()
        if child_err is not None:
            child_err.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["duration_seconds"] = (datetime.now(timezone.utc) - started).total_seconds()
        report["checks_passed"] = sum(item["passed"] for item in checks)
        report["checks_total"] = len(checks)
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"status": report["status"], "checks_passed": report["checks_passed"], "checks_total": report["checks_total"], "error": report.get("error"), "evidence": str(evidence)}, ensure_ascii=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
