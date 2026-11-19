"""Pinned single-file acquisition with durable, verified HTTP range recovery.

Callers own source selection, grouping and activation. This adapter never enables
an artifact until its expected size and SHA-256 have both been verified.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import requests

from src.core.model_download import ModelDownloadCancelledError
from src.utils.diagnostics import record_network_error
from src.utils.file_operations import DOWNLOAD_RENAME_DELAYS, rename_path


def _update_prefix(digest, stream, count):
    remaining = count
    while remaining:
        chunk = stream.read(min(1024 * 1024, remaining))
        if not chunk:
            raise ValueError("Partial resource is truncated")
        digest.update(chunk)
        remaining -= len(chunk)


@lru_cache(maxsize=8)
def _prefix_digest(path, modified, size, count):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        _update_prefix(digest, stream, count)
    return digest.hexdigest()


@dataclass(frozen=True)
class Resource:
    id: str
    size: int
    sha256: str


class ResumableResourceDownloader:
    def __init__(self, resource: Resource, destination: Path):
        self.resource = resource
        self.destination = destination
        self.partial = destination.with_name(destination.name + ".part")
        self.metadata = destination.with_name(destination.name + ".download.json")

    def _read(self):
        try:
            data = json.loads(self.metadata.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data):
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata.with_suffix(".tmp")
        temporary.write_text(json.dumps(data), encoding="utf-8")
        rename_path(temporary, self.metadata, replace=True, retry_delays=DOWNLOAD_RENAME_DELAYS)

    def _identity(self):
        return {"id": self.resource.id, "size": self.resource.size, "sha256": self.resource.sha256}

    def _offset(self, data, *, fresh=False):
        try:
            count = data.get("received", 0)
            if (
                data.get("resource") != self._identity()
                or not isinstance(count, int)
                or not 0 < count <= self.resource.size
            ):
                return 0
            stat = self.partial.stat()
            digest = _prefix_digest.__wrapped__ if fresh else _prefix_digest
            if digest(self.partial, stat.st_mtime_ns, stat.st_size, count) != data.get("prefix_sha256"):
                return 0
            return count
        except (OSError, ValueError):
            return 0

    def state(self):
        data = self._read()
        return {"source": data.get("source"), "downloaded_bytes": self._offset(data), "total_bytes": self.resource.size}

    def remember_source(self, source):
        data = self._read()
        data["source"] = source
        self._save(data)

    def _valid(self, path):
        try:
            if path.stat().st_size != self.resource.size:
                return False
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest() == self.resource.sha256
        except OSError:
            return False

    def acquire(self, url, source, progress, cancel_event=None, verifying=None):
        if self._valid(self.destination):
            return
        self.remember_source(source)
        # A complete file can be recovered even if its last checkpoint could not be saved.
        if self._valid(self.partial):
            if cancel_event is not None and cancel_event.is_set():
                raise ModelDownloadCancelledError()
            progress(self.resource.size, self.resource.size)
            if verifying:
                verifying()
            rename_path(self.partial, self.destination, replace=True, retry_delays=DOWNLOAD_RENAME_DELAYS)
            return
        data = self._read()
        offset = self._offset(data, fresh=True)
        etag = data.get("etag", "")
        # Weak validators and Last-Modified cannot prove byte-for-byte identity.
        if not isinstance(etag, str) or not etag.startswith('"') or not etag.endswith('"'):
            offset = 0
        # Resolve mirror indexes only when the verified local files cannot satisfy the request.
        if callable(url):
            if cancel_event is not None and cancel_event.is_set():
                raise ModelDownloadCancelledError()
            url = url()
        for _attempt in range(2):
            if cancel_event is not None and cancel_event.is_set():
                raise ModelDownloadCancelledError()
            headers = {"Accept-Encoding": "identity"}
            if offset:
                headers.update({"Range": f"bytes={offset}-", "If-Range": etag})
            try:
                with requests.get(url, headers=headers, stream=True, timeout=(10, 60)) as response:
                    code = response.status_code
                    if offset and code == 416:
                        offset = 0
                        continue
                    response.raise_for_status()
                    remote = response.headers.get("ETag", "")
                    if offset and code == 206:
                        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                        valid = match and tuple(map(int, match.groups())) == (
                            offset,
                            self.resource.size - 1,
                            self.resource.size,
                        )
                        if not valid or remote != etag:
                            offset = 0
                            continue
                    elif code == 200:
                        offset = 0
                    else:
                        if offset:
                            offset = 0
                            continue
                        raise ValueError("Unexpected resource range response")
                    expected = self.resource.size - offset
                    length = response.headers.get("Content-Length")
                    if length is not None and int(length) != expected:
                        raise ValueError("Unexpected resource content length")
                    if response.headers.get("Content-Encoding", "identity") != "identity":
                        raise ValueError("Encoded resource response is unsupported")
                    digest = hashlib.sha256()
                    if offset:
                        with self.partial.open("rb") as previous:
                            _update_prefix(digest, previous, offset)
                    with self.partial.open("r+b" if offset else "wb") as stream:
                        stream.truncate(offset)
                        stream.seek(offset)
                        progress(offset, self.resource.size)
                        for chunk in response.iter_content(1024 * 1024):
                            if cancel_event is not None and cancel_event.is_set():
                                raise ModelDownloadCancelledError()
                            if not chunk:
                                continue
                            if offset + len(chunk) > self.resource.size:
                                raise ValueError("Unexpected resource size")
                            stream.write(chunk)
                            stream.flush()
                            offset += len(chunk)
                            digest.update(chunk)
                            data.update(
                                resource=self._identity(),
                                received=offset,
                                prefix_sha256=digest.hexdigest(),
                                etag=remote,
                                source=source,
                            )
                            self._save(data)
                            progress(offset, self.resource.size)
                    if cancel_event is not None and cancel_event.is_set():
                        raise ModelDownloadCancelledError()
                    if verifying:
                        verifying()
                    if offset != self.resource.size or not self._valid(self.partial):
                        self.partial.unlink(missing_ok=True)
                        raise ValueError("Resource checksum or size mismatch")
                    rename_path(self.partial, self.destination, replace=True, retry_delays=DOWNLOAD_RENAME_DELAYS)
                    return
            except requests.RequestException as error:
                record_network_error("GET", url, error)
                raise
        raise ValueError("Unable to establish resource identity")
