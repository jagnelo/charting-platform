"""Fixed-destination host port relay for the network-isolated E2E stack.

This service receives no provider credentials and never interprets or logs
HTTP payloads. Its only destinations are the worktree's frontend and backend
on the internal Compose network.
"""

from __future__ import annotations

import select
import socket
import socketserver
import threading


class RelayServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, listen_port: int, upstream: tuple[str, int]) -> None:
        super().__init__(("0.0.0.0", listen_port), RelayHandler)
        self.upstream = upstream


class RelayHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        try:
            upstream = socket.create_connection(self.server.upstream, timeout=10)
        except OSError:
            return

        try:
            self.request.settimeout(None)
            upstream.settimeout(None)
            sockets = (self.request, upstream)
            while True:
                readable, _, _ = select.select(sockets, (), ())
                for source in readable:
                    destination = upstream if source is self.request else self.request
                    try:
                        payload = source.recv(65_536)
                        if not payload:
                            return
                        destination.sendall(payload)
                    except OSError:
                        return
        finally:
            upstream.close()


def main() -> None:
    destinations = {
        80: ("frontend", 80),
        8000: ("backend", 8000),
    }
    servers = [RelayServer(port, target) for port, target in destinations.items()]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Event().wait()


if __name__ == "__main__":
    main()
