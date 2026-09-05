"""Deterministic local OpenAI-compatible reranker fixture for integration tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
MAX_BODY_BYTES = 2_000_000

REQUEST_COUNT = 0
RERANK_COUNT = 0
LAST_DOCUMENT_COUNT = 0
LAST_MODEL = ""
LAST_QUERY = ""
LAST_AUTHORIZATION_PRESENT = False
FAIL_NEXT_PROVIDER_ERROR = False


class FixtureServer(ThreadingHTTPServer):
    model: str


def _tokens(value: str) -> set[str]:
    return set(TOKEN_RE.findall(value.casefold()))


def _score(query: str, document: str, index: int) -> float:
    try:
        decoded = json.loads(document)
        searchable = json.dumps(decoded, ensure_ascii=False, sort_keys=True)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        searchable = document
    overlap = len(_tokens(query) & _tokens(searchable))
    digest = hashlib.sha256(f"{query}\0{document}\0{index}".encode()).digest()
    tie_break = int.from_bytes(digest[:4], "big") / 4_294_967_296
    if "__fixture_rerank_challenge__" in query and "src/durability.py" in searchable:
        return 10.0
    return float(overlap) + tie_break / 1000


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "HIVE-Rerank-Fixture/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, payload: object) -> None:
        encoded = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _raw(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/stats"}:
            self._json(
                200,
                {
                    "status": "ok",
                    "request_count": REQUEST_COUNT,
                    "rerank_count": RERANK_COUNT,
                    "last_document_count": LAST_DOCUMENT_COUNT,
                    "last_model": LAST_MODEL,
                    "last_query": LAST_QUERY,
                    "last_authorization_present": LAST_AUTHORIZATION_PRESENT,
                },
            )
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        global LAST_AUTHORIZATION_PRESENT, LAST_DOCUMENT_COUNT, LAST_MODEL, LAST_QUERY
        global FAIL_NEXT_PROVIDER_ERROR, REQUEST_COUNT, RERANK_COUNT
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
        if self.path != "/rerank":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(413, {"error": "request_too_large"})
            return
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
            model = payload["model"]
            query = payload["query"]
            documents = payload["documents"]
            top_n = payload["top_n"]
            if (
                not isinstance(model, str)
                or not isinstance(query, str)
                or not isinstance(documents, list)
                or not all(isinstance(item, str) for item in documents)
                or not isinstance(top_n, int)
                or top_n != len(documents)
                or not documents
            ):
                raise ValueError("shape")
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            self._json(400, {"error": "invalid_request"})
            return

        REQUEST_COUNT += 1
        RERANK_COUNT += 1
        LAST_DOCUMENT_COUNT = len(cast(list[str], documents))
        LAST_MODEL = model
        LAST_QUERY = query[:256]
        LAST_AUTHORIZATION_PRESENT = bool(self.headers.get("Authorization"))
        if FAIL_NEXT_PROVIDER_ERROR or "__fixture_rerank_provider_error__" in query:
            FAIL_NEXT_PROVIDER_ERROR = False
            self._json(503, {"error": "fixture_provider_error"})
            return
        if "__fixture_rerank_timeout__" in query:
            time.sleep(2.0)
        if "__fixture_rerank_malformed__" in query:
            self._raw(200, b"{malformed")
            return
        if "__fixture_rerank_http__" in query:
            self._json(503, {"error": "fixture_http_error"})
            return

        document_values = cast(list[str], documents)
        results: list[dict[str, object]] = [
            {"index": index, "relevance_score": _score(query, document, index)}
            for index, document in enumerate(document_values)
        ]
        if "__fixture_rerank_duplicate__" in query and results:
            results[-1]["index"] = results[0]["index"]
        elif "__fixture_rerank_missing__" in query and results:
            results = results[:-1]
        elif "__fixture_rerank_out_of_range__" in query and results:
            results[0]["index"] = len(results)
        elif "__fixture_rerank_nan__" in query and results:
            results[0]["relevance_score"] = float("nan")
            self._raw(
                200,
                json.dumps(
                    {"model": model, "results": results},
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=True,
                ).encode("utf-8"),
            )
            return
        elif "__fixture_rerank_infinity__" in query and results:
            results[0]["relevance_score"] = float("inf")
            self._raw(
                200,
                json.dumps(
                    {"model": model, "results": results},
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=True,
                ).encode("utf-8"),
            )
            return
        elif "__fixture_rerank_invalid_score__" in query and results:
            results[0]["relevance_score"] = "not-a-score"
        elif "__fixture_rerank_model_mismatch__" in query:
            self._json(200, {"model": "unexpected-fixture-model", "results": results})
            return
        if "__fixture_rerank_reversed__" in query:
            results.reverse()
        self._json(200, {"model": model, "results": results})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--model", default="hive-rerank-fixture-v1")
    args = parser.parse_args()
    server = FixtureServer((args.host, args.port), FixtureHandler)
    server.model = args.model
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
