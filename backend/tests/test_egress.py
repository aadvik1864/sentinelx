import base64
import socket
import socketserver
import threading

import pytest

from app.core.config import Settings
from app.egress_proxy import Server, destination, public_addresses


@pytest.mark.parametrize(
    "authority",
    [
        "evil.example:443",
        "api.openai.com:80",
        "api.openai.com:444",
        "localhost:443",
        "[::1]:443",
        "api.openai.com:443@evil.example",
        "api.openai.com",
    ],
)
def test_connect_proxy_rejects_unauthorized_authorities(authority):
    with pytest.raises(ValueError):
        destination(authority, {"api.openai.com"})


@pytest.mark.parametrize(
    "addresses",
    [["127.0.0.1"], ["10.0.0.1"], ["169.254.169.254"], ["::1"], ["8.8.8.8", "192.168.0.1"], []],
)
def test_dns_private_or_mixed_results_are_rejected(monkeypatch, addresses):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in addresses
        ],
    )
    with pytest.raises(ValueError):
        public_addresses("api.openai.com")


def test_dns_public_results_are_returned_as_literal_connect_targets(monkeypatch):
    result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: result)
    assert public_addresses("api.openai.com") == result
    assert destination("api.openai.com:443", {"api.openai.com"}) == "api.openai.com"


def test_external_provider_configuration_rejects_unapproved_and_plaintext_hosts():
    for url in (
        "http://api.openai.com/v1",
        "https://evil.example/v1",
        "https://user:secret@api.openai.com/v1",
    ):
        with pytest.raises(ValueError):
            Settings(
                _env_file=None, llm_provider="openai", llm_api_key="test-only-key", llm_base_url=url
            )


def test_proxy_requires_authentication_and_tunnels_to_the_checked_literal(monkeypatch):
    class Echo(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.sendall(self.request.recv(4096))

    password = "test-only-proxy-password-with-32-characters"
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Echo) as upstream:
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        checked = []

        def resolve(host):
            checked.append(host)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", upstream.server_address)]

        monkeypatch.setattr("app.egress_proxy.public_addresses", resolve)
        with Server(("127.0.0.1", 0), password, {"approved.example"}) as proxy:
            threading.Thread(target=proxy.serve_forever, daemon=True).start()
            try:
                with socket.create_connection(proxy.server_address, timeout=2) as client:
                    client.sendall(b"CONNECT approved.example:443 HTTP/1.1\r\n\r\n")
                    assert b"403" in client.recv(4096)
                assert not checked
                authorization = base64.b64encode(("sentinelx:" + password).encode())
                with socket.create_connection(proxy.server_address, timeout=2) as client:
                    client.sendall(
                        b"CONNECT approved.example:443 HTTP/1.1\r\nProxy-Authorization: Basic "
                        + authorization
                        + b"\r\n\r\n"
                    )
                    assert b"200 Connection established" in client.recv(4096)
                    client.sendall(b"fixture-tunnel-bytes")
                    assert client.recv(4096) == b"fixture-tunnel-bytes"
                assert checked == ["approved.example"]
            finally:
                proxy.shutdown()
        upstream.shutdown()
