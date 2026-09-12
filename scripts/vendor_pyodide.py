"""Obtiene el runtime público fijado, valida su hash y conserva su procedencia."""
from pathlib import Path
import hashlib
import json
import tarfile
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
VERSION = "314.0.6"
URL = f"https://github.com/pyodide/pyodide/releases/download/{VERSION}/pyodide-core-{VERSION}.tar.bz2"
EXPECTED = "1016c31e39ce3764d9a418cbb491a392c802c1b86ccc1367f009f5c59bf8f5fd"
FILES = {"pyodide.asm.mjs", "pyodide.asm.wasm", "pyodide.mjs", "python_stdlib.zip", "pyodide-lock.json", "package.json"}

def main():
    cache = ROOT / "tmp" / f"pyodide-core-{VERSION}.tar.bz2"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        urllib.request.urlretrieve(URL, cache)
    digest = hashlib.sha256(cache.read_bytes()).hexdigest()
    if digest != EXPECTED:
        raise RuntimeError("El hash de la distribución no coincide con el publicado.")
    destination = ROOT / "web" / "vendor" / "pyodide"
    destination.mkdir(parents=True, exist_ok=True)
    extracted = set()
    with tarfile.open(cache, "r:bz2") as archive:
        for member in archive.getmembers():
            name = Path(member.name).name
            if name not in FILES or not member.isfile():
                continue
            if name in extracted:
                raise RuntimeError(f"Archivo duplicado: {name}")
            data = archive.extractfile(member).read()
            (destination / name).write_bytes(data)
            extracted.add(name)
    if extracted != FILES:
        raise RuntimeError(f"Runtime incompleto: {FILES - extracted}")
    license_url = f"https://raw.githubusercontent.com/pyodide/pyodide/{VERSION}/LICENSE"
    with urllib.request.urlopen(license_url) as response:
        (destination / "LICENSE").write_bytes(response.read())
    # CPython and bundled libraries retain their notices in this upstream license.
    python_version = json.loads((destination / "pyodide-lock.json").read_text(encoding="utf-8"))["info"]["python"]
    python_license = f"https://raw.githubusercontent.com/python/cpython/v{python_version}/LICENSE"
    with urllib.request.urlopen(python_license) as response:
        (destination / "CPYTHON-LICENSE").write_bytes(response.read())
    manifest = {
        "name": "Pyodide", "version": VERSION, "python_version": python_version, "source": URL,
        "archive_sha256": digest, "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "licenses": [license_url, python_license],
        "files": [{"path": str(p.relative_to(ROOT)).replace("\\", "/"),
                   "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                  for p in sorted(destination.iterdir()) if p.is_file()],
    }
    out = ROOT / "evidence" / "dependencies" / "pyodide.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"runtime_files": len(manifest["files"]), "bytes": sum(f["bytes"] for f in manifest["files"]), "sha256": digest}))

if __name__ == "__main__":
    main()
