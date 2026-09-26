"""Atomic downloads for Seedream candidate images."""

import os
import urllib.request
from pathlib import Path
from typing import Protocol

from PIL import Image

from backend.seedream.repository import BatchRepository


class DownloadTransport(Protocol):
    def download(self, url: str) -> bytes: ...


class UrllibDownloadTransport:
    def download(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=60.0) as response:
            return response.read()


class ImageDownloader:
    def __init__(self, repository: BatchRepository, transport: DownloadTransport | None = None) -> None:
        self._repository = repository
        self._transport = transport or UrllibDownloadTransport()

    def download_image(self, batch_id: str, attempt_index: int, url: str) -> str:
        relative_path = f"images/{attempt_index}.jpg"
        destination = self._repository.resolve_asset(batch_id, relative_path)
        content = self._transport.download(url)
        if not content:
            raise ValueError("Downloaded image is empty")
        temporary_path = destination.with_suffix(".part")
        with temporary_path.open("wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        self._validate_image(temporary_path)
        os.replace(temporary_path, destination)
        return relative_path

    @staticmethod
    def _validate_image(path: Path) -> None:
        with Image.open(path) as image:
            image.verify()
