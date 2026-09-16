"""HTTP(S) proxy for browser tests that rejects all external requests."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class DenyProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _target_host(self) -> str:
        target = self.path
        if self.command == "CONNECT":
            target = f"https://{target}"
        return urlsplit(target).hostname or "unknown"

    def _reject(self) -> None:
        # Deliberately retain only the hostname: API keys may appear in query
        # strings for some services, so request targets must never be logged.
        print(
            f"blocked egress method={self.command} host={self._target_host()}",
            flush=True,
        )
        self.send_response(403, "External egress disabled for browser tests")
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_CONNECT = _reject
    do_DELETE = _reject
    do_GET = _reject
    do_HEAD = _reject
    do_OPTIONS = _reject
    do_PATCH = _reject
    do_POST = _reject
    do_PUT = _reject
    do_TRACE = _reject

    def log_message(self, _format: str, *_args: object) -> None:
        # BaseHTTPRequestHandler logs full request targets, which can contain
        # provider keys. _reject emits a hostname-only diagnostic instead.
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 3128), DenyProxyHandler).serve_forever()
