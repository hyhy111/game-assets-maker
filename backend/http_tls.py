"""Verified HTTPS contexts that also work without a host OpenSSL CA bundle."""

import ssl

import certifi


def create_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    # Keep system/SSL_CERT_FILE trust (including Windows roots), and add bundled public roots.
    context.load_verify_locations(cafile=certifi.where())
    return context
