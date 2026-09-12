"""Servidor local de VÉRTICE. Python 3.10+, sin paquetes adicionales.

Escucha exclusivamente en loopback; sirve únicamente web/ y una API JSON acotada.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import sys
import threading
from urllib.parse import unquote, urlsplit
import webbrowser

from vertice import __version__, Graph, ValidationError
from vertice.codec import MAX_JSON_BYTES, solve_payload, load_json

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"
    request_queue_size = 16

    def __init__(self, address, handler=None, *, web_root=WEB):
        self.web_root = Path(web_root).resolve()
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, handler or Handler)

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(SimpleHTTPRequestHandler):
    server_version = "VerticeLocal/1.0"
    protocol_version = "HTTP/1.1"
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm",
                      ".json": "application/json", ".vtt": "text/vtt; charset=utf-8"}

    def __init__(self, request, client_address, server):
        request.settimeout(5)
        super().__init__(request, client_address, server, directory=str(server.web_root))

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        super().end_headers()

    def log_message(self, format, *args):
        # No graph contents, labels or uploaded data in server logs.
        return

    def _json(self, status, value, *, head=False):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def _reject(self, status, message):
        self.close_connection = True
        self._json(status, {"error": message}, head=self.command == "HEAD")

    def _trusted_request(self):
        hosts = {f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"}
        if self.headers.get("Host", "").lower() not in hosts or len(self.headers.get_all("Host", [])) != 1:
            self._reject(403, "Host no autorizado.")
            return False
        if len(self.headers.get_all("Origin", [])) > 1:
            self._reject(403, "Origen ambiguo.")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin.lower() not in {f"http://{host}" for host in hosts}:
            self._reject(403, "Origen no autorizado.")
            return False
        return True

    def _path(self):
        try:
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc:
                return None
            path = unquote(parsed.path, errors="strict")
            if "\x00" in path or "\\" in path:
                return None
            return path
        except (ValueError, UnicodeError):
            return None

    def do_GET(self):
        self._get(head=False)

    def do_HEAD(self):
        self._get(head=True)

    def _get(self, *, head):
        if not self._trusted_request():
            return
        path = self._path()
        if path == "/api/health":
            core = {name: hashlib.sha256((ROOT / "vertice" / name).read_bytes()).hexdigest()
                    for name in ("__init__.py", "graph.py", "dijkstra.py", "codec.py")}
            self._json(200, {"project": "vertice-sdv", "version": __version__, "engine": "python", "core": core}, head=head)
            return
        if path is None or path.startswith("/api/"):
            self._reject(404, "Página no encontrada.")
            return
        resolved = (self.server.web_root / path.lstrip("/")).resolve()
        if not resolved.is_relative_to(self.server.web_root):
            self._reject(403, "Ruta no permitida.")
            return
        if resolved.is_dir():
            resolved = resolved / "index.html"
        # Check the final target too, including symlinked index files.
        resolved = resolved.resolve()
        if not resolved.is_relative_to(self.server.web_root) or not resolved.is_file():
            self._reject(404, "Página no encontrada.")
            return
        try:
            stream = resolved.open("rb")
        except OSError:
            self._reject(404, "No se pudo abrir el archivo.")
            return
        with stream:
            size = resolved.stat().st_size
            start, end, partial = 0, size - 1, False
            # HEAD ignores Range. We publish no validators, so an If-Range
            # condition cannot be established: send the complete representation.
            value = self.headers.get("Range") if not head and self.headers.get("If-Range") is None else None
            if value is not None and not value.startswith("bytes="):
                value = None  # Unknown range units are ignored (RFC 9110, 14.2).
            if value is not None:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
                valid = bool(match and (match[1] or match[2]) and size)
                if valid:
                    left, right = match.groups()
                    if len(left) > 20 or len(right) > 20:
                        valid = False
                    elif not left:
                        suffix = int(right)
                        valid = suffix > 0
                        start = max(0, size - suffix)
                    else:
                        start = int(left)
                        end = min(int(right), size - 1) if right else size - 1
                        valid = start <= end and start < size
                if not valid:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                partial = True
            length = max(0, end - start + 1)
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", self.guess_type(str(resolved)))
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-cache")
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if not head:
                stream.seek(start)
                remaining = length
                try:
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError, socket.timeout):
                    pass

    def do_POST(self):
        if not self._trusted_request():
            return
        path = self._path()
        if path not in ("/api/solve", "/api/validate"):
            self._reject(404, "Operación no encontrada.")
            return
        if self.headers.get("Transfer-Encoding") is not None:
            self._reject(400, "Envía un cuerpo JSON de longitud definida.")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"\d{1,10}", lengths[0]):
            self._reject(411, "Falta una longitud válida.")
            return
        length = int(lengths[0])
        if length > MAX_JSON_BYTES:
            self._reject(413, "El JSON excede 2 MiB.")
            return
        if len(self.headers.get_all("Content-Type", [])) != 1 or self.headers.get_content_type() != "application/json":
            self._reject(415, "Se requiere application/json.")
            return
        try:
            data = self.rfile.read(length)
            if len(data) != length:
                self._reject(400, "El JSON está incompleto.")
                return
            text = data.decode("utf-8")
            if path == "/api/solve":
                result = solve_payload(load_json(text))
            else:
                result = Graph.from_dict(load_json(text)).to_dict()
            self._json(200, result)
        except (UnicodeError, ValidationError) as error:
            self._reject(400, str(error) if isinstance(error, ValidationError) else "El archivo debe usar UTF-8.")
        except (socket.timeout, TimeoutError):
            self._reject(408, "Se agotó el tiempo para recibir el JSON.")

    def do_OPTIONS(self):
        self._reject(405, "Operación no admitida.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Abre el estudio de grafos VÉRTICE / SDV.")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--open", action="store_true", help="Abrir el navegador")
    parser.add_argument("--no-open", action="store_false", dest="open", help="No abrir el navegador")
    parser.add_argument("--check", action="store_true", help="Comprobar Python y núcleo sin iniciar un servidor")
    args = parser.parse_args(argv)
    if args.check:
        print(f"VERTICE {__version__} / Python {sys.version.split()[0]} / listo")
        return 0
    if not 1 <= args.port <= 65535:
        parser.error("El puerto debe estar entre 1 y 65535.")
    try:
        server = LocalServer(("127.0.0.1", args.port))
    except OSError as error:
        parser.exit(1, f"No se pudo iniciar: {error}. Prueba otro puerto con --port.\n")
    address = f"http://127.0.0.1:{server.server_port}/"
    print(f"VERTICE / SDV - {address}\nCierra con Ctrl+C.", flush=True)
    if args.open:
        webbrowser.open(address)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
