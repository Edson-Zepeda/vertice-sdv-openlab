"""Publica una copia byte a byte del núcleo Python junto con su manifiesto."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
FILES = ("__init__.py", "graph.py", "dijkstra.py", "codec.py")

def main():
    destination = ROOT / "web" / "python" / "vertice"
    destination.mkdir(parents=True, exist_ok=True)
    files = []
    for name in FILES:
        data = (ROOT / "vertice" / name).read_bytes()
        (destination / name).write_bytes(data)
        files.append({"name": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    result = {"schema_version": 1, "package": "vertice", "files": files}
    (destination.parent / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Sincronizados {len(files)} archivos Python sin modificar sus bytes.")

if __name__ == "__main__":
    main()
