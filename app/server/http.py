"""A tiny JSON router on the standard library's threading HTTP server."""
from __future__ import annotations

import json
import re
import traceback
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

PREFIX = "/studio-api"


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, str]
    params: dict[str, str]
    body: bytes
    handler: BaseHTTPRequestHandler

    def json(self) -> Any:
        try:
            return json.loads(self.body or b"{}")
        except json.JSONDecodeError as e:
            raise HttpError(400, f"bad JSON: {e}") from e


@dataclass
class FileResponse:
    """Stream a file (with byte ranges, which Spark and media elements use)."""
    path: Path
    content_type: str = "application/octet-stream"


@dataclass
class Router:
    routes: list[tuple[str, re.Pattern, Callable]] = field(default_factory=list)

    def route(self, method: str, pattern: str):
        # "/projects/{name}/clips/{clip}" -> named groups; {rest*} matches across slashes.
        rx = re.sub(r"\{(\w+)\*\}", r"(?P<\1>.+)", pattern)
        rx = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", rx)

        def deco(fn):
            self.routes.append((method, re.compile(f"^{rx}$"), fn))
            return fn
        return deco

    def dispatch(self, req: Request):
        allowed = False
        for method, rx, fn in self.routes:
            m = rx.match(req.path)
            if m:
                allowed = True
                if method == req.method:
                    req.params = {k: unquote(v) for k, v in m.groupdict().items()}
                    return fn(req)
        raise HttpError(405 if allowed else 404, f"{req.method} {req.path}")


def serve(router: Router, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quiet: the studio polls every second
            pass

        def _handle(self):
            url = urlparse(self.path)
            path = url.path[len(PREFIX):] if url.path.startswith(PREFIX) else url.path
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            req = Request(self.command, path or "/", {k: v[-1] for k, v in parse_qs(url.query).items()}, {}, body, self)
            try:
                out = router.dispatch(req)
                if isinstance(out, FileResponse):
                    return self._file(out)
                self._json(200, out if out is not None else {"ok": True})
            except HttpError as e:
                self._json(e.status, {"error": str(e)})
            except SystemExit as e:  # pipeline helpers raise SystemExit with a user-facing message
                self._json(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

        def _json(self, status: int, obj) -> None:
            data = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _file(self, f: FileResponse) -> None:
            if not f.path.is_file():
                return self._json(404, {"error": f"not found: {f.path.name}"})
            size = f.path.stat().st_size
            start, end = 0, size - 1
            m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
            if m:
                start = int(m[1]) if m[1] else max(0, size - int(m[2]))
                end = min(int(m[2]), size - 1) if m[1] and m[2] else size - 1
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", f.content_type)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with open(f.path, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                try:
                    while left > 0:
                        chunk = fh.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
                except (ConnectionResetError, BrokenPipeError):
                    pass

        do_GET = do_POST = do_PUT = do_DELETE = _handle

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    print(f"studio server on http://{host}:{port}{PREFIX}  (open the studio via the Vite dev server: "
          f"http://127.0.0.1:5173/studio.html)", flush=True)
    httpd.serve_forever()
