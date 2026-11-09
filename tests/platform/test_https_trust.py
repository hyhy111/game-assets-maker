"""Exercise platform HTTPS with the default CA store missing, as in frozen runtimes."""

from __future__ import annotations

import ipaddress
import json
import ssl
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import certifi
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from backend.api.platform_api import PlatformFacade
from backend.platform.config import PlatformConfig
from backend.platform.downloads import UrllibFallbackTransport


@pytest.fixture
def https_platform(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "GAM test CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_path, cert_path, key_path = (tmp_path / name for name in ("ca.pem", "server.pem", "server.key"))
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"code": 200, "data": {"video": {"models": []}}}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    try:
        yield f"https://127.0.0.1:{server.server_port}", ca_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def capabilities(url):
    config = PlatformConfig()
    config.set(url, "test-token")
    return PlatformFacade(config).capabilities()


def test_capabilities_with_missing_default_ca_store(https_platform, monkeypatch):
    url, ca_path = https_platform
    monkeypatch.setattr(ssl.SSLContext, "load_default_certs", lambda self, purpose=ssl.Purpose.SERVER_AUTH: None)
    monkeypatch.setattr(certifi, "where", lambda: str(ca_path))

    result = capabilities(url)

    assert result["success"], result
    assert result["data"]["video"]["models"] == []


def test_artifact_download_with_missing_default_ca_store(https_platform, monkeypatch):
    url, ca_path = https_platform
    monkeypatch.setattr(ssl.SSLContext, "load_default_certs", lambda self, purpose=ssl.Purpose.SERVER_AUTH: None)
    monkeypatch.setattr(certifi, "where", lambda: str(ca_path))

    assert json.loads(UrllibFallbackTransport().download(url))["code"] == 200


def test_capabilities_still_rejects_untrusted_certificate(https_platform):
    url, _ = https_platform
    result = capabilities(url)

    assert not result["success"]
    assert "CERTIFICATE_VERIFY_FAILED" in result["error"]["message"]


def test_capabilities_preserves_custom_ca_file(https_platform, monkeypatch):
    url, ca_path = https_platform
    monkeypatch.setenv("SSL_CERT_FILE", str(ca_path))

    assert capabilities(url)["success"]


def test_capabilities_still_checks_hostname(https_platform, monkeypatch):
    url, ca_path = https_platform
    monkeypatch.setattr(certifi, "where", lambda: str(ca_path))
    result = capabilities(url.replace("127.0.0.1", "localhost"))

    assert not result["success"]
    assert "CERTIFICATE_VERIFY_FAILED" in result["error"]["message"]
    assert "mismatch" in result["error"]["message"]
