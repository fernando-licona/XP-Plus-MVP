"""XP Plus API: JSON over `core` for the XP Plus web app (`xp_plus_web/`, proxied at /xpp).

    python -m xp_plus api            # http://127.0.0.1:8765/xpp/api/...

Standard library only; binds to localhost. FlowLab's own backend keeps serving /api.
"""
from __future__ import annotations

import json
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import core

PREFIX = "/xpp/api"


def _preset(pid: str) -> dict:
    for p in core.available_presets():
        if p["id"] == pid:
            return p
    raise LookupError(f"unknown experiment {pid!r}")


def _summary(p: dict) -> dict:
    _, extraction, resolutions = core.load(p)
    f = extraction.features
    return {"id": p["id"], "label": p["label"], "title": f.paper.title, "doi": f.paper.doi, "year": f.paper.year,
            "authors": f.paper.authors, "experiment": f.experiment, "models": [m.id for m in f.models],
            "n_claims": len(f.claims), "n_components": len(f.rig.components), "n_resolutions": len(resolutions),
            "options": {k: p[k] for k in ("black_box", "backend", "bodenstein") if k in p},
            "has_observations": bool(p.get("observations"))}


def experiments() -> list[dict]:
    return [_summary(p) for p in core.available_presets()]


def experiment(pid: str) -> dict:
    p = _preset(pid)
    _, extraction, resolutions = core.load(p)
    return {**_summary(p), "extraction": json.loads(extraction.model_dump_json()),
            "resolutions": [json.loads(r.model_dump_json()) for r in resolutions]}


def gate(pid: str) -> dict:
    extraction, report = core.gate(_preset(pid))
    return {"passed": report.passed,
            "gaps": [json.loads(g.model_dump_json()) for g in extraction.gaps + report.gaps]}


def run(pid: str, body: dict) -> dict:
    std = core.run(_preset(pid), apply_resolutions=body.get("apply_resolutions", True),
                   black_box=body.get("black_box", True), backend=body.get("backend"),
                   paper_bodenstein=body.get("paper_bodenstein", False), reactor_only=body.get("reactor_only", False))
    return json.loads(std.model_dump_json())


class Handler(BaseHTTPRequestHandler):
    server_version = "XPPlusAPI/0.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, status=HTTPStatus.OK):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _route(self, method: str):
        path = self.path.split("?")[0]
        if not path.startswith(PREFIX):
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        parts = [p for p in path[len(PREFIX):].split("/") if p]
        try:
            if method == "GET" and parts == ["experiments"]:
                return self._json(experiments())
            if method == "GET" and len(parts) == 2 and parts[0] == "experiments":
                return self._json(experiment(parts[1]))
            if method == "POST" and len(parts) == 3 and parts[0] == "experiments" and parts[2] in ("gate", "run"):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                return self._json(gate(parts[1]) if parts[2] == "gate" else run(parts[1], body))
            if method == "GET" and parts == ["health"]:
                return self._json({"status": "ok"})
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except LookupError as exc:
            return self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # surface to the page instead of dropping the connection
            return self._json({"error": str(exc), "trace": traceback.format_exc()}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"XP Plus API at http://{host}:{port}{PREFIX}  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
