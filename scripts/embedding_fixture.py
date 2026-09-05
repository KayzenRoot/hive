"""Deterministic local OpenAI-compatible embedding fixture for integration tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
CONCEPTS = (
    {
        "durable",
        "retention",
        "ledger",
        "restart",
        "resilient",
        "recovery",
        "recoverable",
        "continuation",
        "replay",
        "checkpoint",
    },
    {"order", "orderservice", "project", "symbol", "service", "route"},
    {"checkout", "manifest", "watermark", "provenance"},
    {"health", "api", "status", "worker"},
    {"task", "text", "structured", "duplicate"},
    {"repository", "source", "file", "index", "corpus"},
    {"security", "secret", "bounded", "provider", "embedding"},
    {"race", "stale", "current", "sync", "generation"},
)

REQUEST_COUNT = 0
EMBEDDING_COUNT = 0
FAIL_NEXT_PROVIDER_ERROR = False


def vector_for(text: str, dimensions: int) -> list[float]:
    tokens = set(TOKEN_RE.findall(text.casefold()))
    vector = [0.0] * dimensions
    for index, concept in enumerate(CONCEPTS):
        if index >= dimensions:
            break
        vector[index] += float(len(tokens & concept))
    if not any(vector):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        for index in range(dimensions):
            vector[index] = (digest[index % len(digest)] + 1) / 256.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [round(value / norm, 8) for value in vector]


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "HIVE-Embedding-Fixture/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health" or self.path == "/stats":
            self._json(
                200,
                {
                    "status": "ok",
                    "request_count": REQUEST_COUNT,
                    "embedding_count": EMBEDDING_COUNT,
                },
            )
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        global EMBEDDING_COUNT, FAIL_NEXT_PROVIDER_ERROR, REQUEST_COUNT
        if self.path == "/control":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self._json(400, {"error": "invalid_request"})
                return
            FAIL_NEXT_PROVIDER_ERROR = payload.get("fail_next_provider_error") is True
            self._json(200, {"fail_next_provider_error": FAIL_NEXT_PROVIDER_ERROR})
            return
        if self.path != "/embeddings":
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(min(length, 2_000_000))
        try:
            payload = json.loads(body.decode("utf-8"))
            inputs = payload["input"]
            model = payload["model"]
            dimensions = int(self.server.dimensions)  # type: ignore[attr-defined]
            if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
                raise ValueError("input")
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            self._json(400, {"error": "invalid_request"})
            return

        REQUEST_COUNT += 1
        EMBEDDING_COUNT += len(inputs)
        if (
            FAIL_NEXT_PROVIDER_ERROR
            or "error" in str(model)
            or any("__fixture_provider_error__" in item for item in inputs)
        ):
            FAIL_NEXT_PROVIDER_ERROR = False
            self._json(503, {"error": "fixture_provider_error"})
            return
        if "malformed" in str(model):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{malformed")
            return

        data: list[dict[str, Any]] = []
        for index, item in enumerate(cast(list[str], inputs)):
            vector = vector_for(item, dimensions)
            if "dimension" in str(model):
                vector = vector[:-1]
            if "nan" in str(model):
                vector[0] = float("nan")
            data.append({"object": "embedding", "index": index, "embedding": vector})
        if "ordering" in str(model):
            data.reverse()
        if "duplicate" in str(model) and data:
            data[-1]["index"] = data[0]["index"]
        self._json(200, {"object": "list", "model": model, "data": data})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--dimensions", type=int, default=8)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), FixtureHandler)
    server.dimensions = args.dimensions  # type: ignore[attr-defined]
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
