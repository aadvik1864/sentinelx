"""Bounded CONNECT-only proxy with exact destinations and DNS-to-public-IP pinning."""

import base64
import hmac
import ipaddress
import os
import selectors
import socket
import socketserver
import threading
import time


def public_addresses(host, port=443):
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("Destination resolved to an unauthorized address")
    return addresses


def destination(authority, allowed_hosts):
    if authority.count(":") != 1:
        raise ValueError("Only named HTTPS destinations are allowed")
    host, port = authority.rsplit(":", 1)
    if port != "443" or host.lower() not in allowed_hosts:
        raise ValueError("Destination is not allowlisted")
    return host.lower()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        upstream = None
        try:
            request = self.rfile.readline(4097).decode("ascii").rstrip("\r\n").split(" ")
            if (
                len(request) != 3
                or request[0] != "CONNECT"
                or request[2] not in {"HTTP/1.1", "HTTP/1.0"}
            ):
                raise ValueError("CONNECT required")
            host = destination(request[1], self.server.allowed_hosts)
            headers = {}
            size = 0
            while True:
                line = self.rfile.readline(4097)
                size += len(line)
                if not line or size > 16384 or len(line) > 4096:
                    raise ValueError("Invalid proxy headers")
                if line == b"\r\n":
                    break
                key, value = line.decode("ascii").split(":", 1)
                if key.lower() in headers:
                    raise ValueError("Repeated proxy header")
                headers[key.lower()] = value.strip()
            expected = (
                "Basic " + base64.b64encode(("sentinelx:" + self.server.password).encode()).decode()
            )
            if not hmac.compare_digest(headers.get("proxy-authorization", ""), expected):
                raise ValueError("Proxy authorization required")
            # Resolve once, reject private/mixed results, and connect to a checked literal IP.
            for family, kind, proto, _, address in public_addresses(host):
                candidate = socket.socket(family, kind, proto)
                candidate.settimeout(5)
                try:
                    candidate.connect(address)
                    upstream = candidate
                    break
                except OSError:
                    candidate.close()
            if upstream is None:
                raise OSError("Destination unavailable")
            self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            self.wfile.flush()
            deadline, transferred = time.monotonic() + 180, 0
            with selectors.DefaultSelector() as selector:
                selector.register(self.connection, selectors.EVENT_READ, upstream)
                selector.register(upstream, selectors.EVENT_READ, self.connection)
                while time.monotonic() < deadline and transferred <= 5 * 1024 * 1024:
                    for key, _ in selector.select(timeout=1):
                        data = key.fileobj.recv(16384)
                        if not data:
                            return
                        transferred += len(data)
                        key.data.sendall(data)
        except (OSError, ValueError, UnicodeError):
            if upstream is None:
                try:
                    self.wfile.write(
                        b"HTTP/1.1 403 Egress denied\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                except OSError:
                    pass
        finally:
            if upstream:
                upstream.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, password, allowed_hosts):
        if len(password) < 24 or not allowed_hosts:
            raise ValueError("Supply an independent proxy credential and exact allowed hosts")
        self.password, self.allowed_hosts = password, set(allowed_hosts)
        self.slots = threading.BoundedSemaphore(20)
        super().__init__(address, Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


def main():
    allowed = {
        item.strip().lower()
        for item in os.environ["EGRESS_ALLOWED_HOSTS"].split(",")
        if item.strip()
    }
    with Server(("0.0.0.0", 8081), os.environ["EGRESS_PROXY_PASSWORD"], allowed) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
