"""Process-wide safeguards loaded only by the zero-cost test runner."""

from __future__ import annotations

import os
import sys
from ipaddress import ip_address

import backend.seedance.client as seedance_client
import backend.seedance.downloader as seedance_downloader

if os.environ.get("GAM_ZERO_COST") == "1":
    def _is_loopback(host: object) -> bool:
        if host == "localhost":
            return True
        try:
            return isinstance(host, str) and ip_address(host).is_loopback
        except ValueError:
            return False


    def _block_network(event: str, arguments: tuple[object, ...]) -> None:
        if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex"}:
            if not _is_loopback(arguments[0]):
                raise RuntimeError("external network is disabled by the zero-cost test runner")
            return
        if event != "socket.connect":
            return
        address = arguments[1]
        if isinstance(address, str):
            return
        host = address[0] if isinstance(address, tuple) and address else None
        if not _is_loopback(host):
            raise RuntimeError("external network is disabled by the zero-cost test runner")


    sys.addaudithook(_block_network)

    class _BlockedSeedanceTransport:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("real Seedance transport is disabled by the zero-cost test runner")


    seedance_client.UrllibTransport = _BlockedSeedanceTransport
    seedance_downloader.UrllibDownloadTransport = _BlockedSeedanceTransport
