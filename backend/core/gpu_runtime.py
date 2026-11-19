"""Explicit acquisition and verified activation of the optional Windows CUDA runtime."""

import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from contextlib import suppress
from functools import lru_cache, partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import requests

from src.utils.data_paths import DATA_ROOT_ENV_VAR, INSTALLED_MODE, data_mode, data_root
from src.utils.file_operations import DOWNLOAD_RENAME_DELAYS, rename_path

GPU_COMPONENTS = tuple(json.loads(Path(__file__).with_name("gpu_components.json").read_text()))
_GPU_MIRROR_INDEXES = {
    "huawei": "https://repo.huaweicloud.com/repository/pypi/simple/",
}
GPU_SOURCES = {"aliyun", "pypi", *_GPU_MIRROR_INDEXES}
_LOCK = threading.RLock()
_STATUS = {}
# Cover preparation probes and all project tasks with one native session budget.
_WORKER_SLOT = threading.BoundedSemaphore(1)
_WORKERS = set()


class GPURuntimeError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def runtime_root() -> Path:
    if (
        sys.platform == "win32"
        and getattr(sys, "frozen", False)
        and data_mode() == INSTALLED_MODE
        and not os.environ.get(DATA_ROOT_ENV_VAR)
    ):
        return Path(sys.executable).resolve().parent / "runtime" / "cuda13-cp312"
    return data_root() / "runtime" / "cuda13-cp312"


def runtime_cache_dir():
    return runtime_root() / "wheels"


def normalize_gpu_source(source):
    # Older clients sent "tuna" as an alias for the Aliyun source.
    return "aliyun" if source == "tuna" else source


class _WheelLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and (href := dict(attrs).get("href")):
            self.links.append(href)


def _component_url(record, source):
    if source == "aliyun":
        return record["mirror_url"]
    if source == "pypi":
        return record["url"]

    index = f"{_GPU_MIRROR_INDEXES[source]}{record['name']}/"
    with requests.get(index, headers={"Accept": "text/html"}, timeout=(10, 20)) as response:
        response.raise_for_status()
        links = _WheelLinks()
        links.feed(response.text)
        for href in links.links:
            url = urlsplit(urljoin(response.url, href))
            if url.scheme != "https" or not url.hostname or unquote(url.path.rsplit("/", 1)[-1]) != record["filename"]:
                continue
            digest = url.fragment.removeprefix("sha256=") if url.fragment.startswith("sha256=") else None
            if digest is None or digest.lower() == record["sha256"]:
                return url._replace(fragment="").geturl()
    raise ValueError(f"Selected mirror does not have the pinned file: {record['filename']}")


@lru_cache(maxsize=2048)
def _digest(path, size, modified, created):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _identity(path):
    stat = path.stat()
    return _digest(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def runtime_status():
    root = runtime_root()
    with _LOCK:
        status = _STATUS.get(str(root))
        status = dict(status) if status else None
    ready = False
    marker = root / "active.json"
    try:
        active = json.loads(marker.read_text())
        directory = root / active["directory"]
        evidence = json.loads((directory / "verified.json").read_text())
        if (
            evidence.get("cuda_nodes", 0) > 0
            and all(
                (directory / item["path"]).is_file()
                and (directory / item["path"]).stat().st_size == item["size"]
                and _identity(directory / item["path"]) == item["sha256"]
                for item in evidence.get("files", [])
            )
            and evidence.get("files")
        ):
            ready = True
    except (OSError, ValueError, KeyError):
        pass
    result = status or {"phase": "ready" if ready else "needs_download", "error": None}
    if result["phase"] == "ready" and not ready:
        result["phase"] = "needs_download"
    result.update(gpu_ready=ready, total_bytes=sum(r["size"] for r in GPU_COMPONENTS))
    try:
        saved = json.loads((root / "download-state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    source = normalize_gpu_source(saved.get("source"))
    result["source"] = source if isinstance(source, str) and source in GPU_SOURCES else "aliyun"
    result["downloaded_bytes"] = saved.get("downloaded_bytes", 0)
    if not status and not ready and result["downloaded_bytes"]:
        result["phase"] = "paused"
    return result


def prepare_runtime(source, model=None, cancel_event=None):
    """Acquire only pinned resources after explicit consent, then reuse activation."""
    from src.core.model_download import ModelDownloadCancelledError
    from src.core.resumable_download import Resource, ResumableResourceDownloader

    source = normalize_gpu_source(source)
    if source not in GPU_SOURCES:
        raise ValueError("Unknown GPU component source")
    root = runtime_root()
    downloaders = [
        ResumableResourceDownloader(
            Resource(record["filename"], record["size"], record["sha256"]),
            runtime_cache_dir() / record["filename"],
        )
        for record in GPU_COMPONENTS
    ]
    counts = [downloader.state()["downloaded_bytes"] for downloader in downloaders]

    def update(phase="downloading"):
        temporary = root / ".download-state.tmp"
        temporary.write_text(json.dumps({"source": source, "downloaded_bytes": sum(counts)}), encoding="utf-8")
        rename_path(temporary, root / "download-state.json", replace=True, retry_delays=DOWNLOAD_RENAME_DELAYS)
        _status(phase)

    try:
        root.mkdir(parents=True, exist_ok=True)
        update("verifying")
        for index, (record, downloader) in enumerate(zip(GPU_COMPONENTS, downloaders, strict=True)):
            _cancel(cancel_event)
            path = downloader.destination
            if path.is_file() and path.stat().st_size == record["size"] and _identity(path) == record["sha256"]:
                counts[index] = record["size"]
            elif path.is_file():
                counts[index] = 0
        update()
        for index, (record, downloader) in enumerate(zip(GPU_COMPONENTS, downloaders, strict=True)):
            _cancel(cancel_event)
            downloader.remember_source(source)

            def progress(received, total, index=index):
                counts[index] = received
                update()

            downloader.acquire(
                partial(_component_url, record, source),
                source,
                progress,
                cancel_event=cancel_event,
                verifying=lambda: update("verifying"),
            )
            counts[index] = record["size"]
            update()
        return activate_runtime(model=model, cancel_event=cancel_event)
    except Exception as error:
        cancelled = isinstance(error, ModelDownloadCancelledError) or getattr(error, "code", None) == "GPU_CANCELLED"
        for index, (record, downloader) in enumerate(zip(GPU_COMPONENTS, downloaders, strict=True)):
            path = downloader.destination
            counts[index] = (
                record["size"]
                if path.is_file() and path.stat().st_size == record["size"] and _identity(path) == record["sha256"]
                else downloader.state()["downloaded_bytes"]
            )
        # A progress file that stays locked must not hide the original error from the UI.
        with suppress(OSError):
            update("verifying")
        return _status(
            "paused" if cancelled else "failed",
            {
                "code": "GPU_CANCELLED" if cancelled else "GPU_DOWNLOAD_FAILED",
                "message": str(error),
            },
        )


def _status(phase, error=None):
    result = {"phase": phase, "error": error, "total_bytes": sum(r["size"] for r in GPU_COMPONENTS)}
    with _LOCK:
        _STATUS[str(runtime_root())] = result
    return dict(result)


def _cancel(event):
    if event is not None and event.is_set():
        raise GPURuntimeError("GPU_CANCELLED", "GPU preparation cancelled; CPU remains available")


def activate_runtime(cache_dir=None, model=None, cancel_event=None):
    """Validate a complete fixed wheel cache, probe CUDA, then atomically enable it."""
    from backend.core.birefnet_onnx import model_path, weights_available

    _status("initializing")
    root = runtime_root()
    staging = None
    try:
        if sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32 or sys.platform != "win32":
            raise GPURuntimeError("GPU_ABI_MISMATCH", "CUDA worker requires Windows x64 CPython 3.12")
        cache = Path(cache_dir) if cache_dir is not None else runtime_cache_dir()
        for record in GPU_COMPONENTS:
            _cancel(cancel_event)
            path = cache / record["filename"]
            if not path.is_file() or path.stat().st_size != record["size"]:
                raise GPURuntimeError("GPU_COMPONENT_INVALID", f"Missing or incomplete component: {path.name}")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != record["sha256"]:
                raise GPURuntimeError("GPU_COMPONENT_INVALID", f"Component checksum mismatch: {path.name}")
        if not (weights_available() if model is None else weights_available(model)):
            raise GPURuntimeError("GPU_MODEL_INVALID", "Prepare the selected model before validating GPU")
        root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".prepare-", dir=root))
        for record in GPU_COMPONENTS:
            with zipfile.ZipFile(cache / record["filename"]) as archive:
                for member in archive.infolist():
                    _cancel(cancel_event)
                    name = PurePosixPath(member.filename)
                    if (
                        name.is_absolute()
                        or ".." in name.parts
                        or "\\" in member.filename
                        or ":" in member.filename
                        or (member.external_attr >> 16) & 0o170000 == 0o120000
                    ):
                        raise GPURuntimeError("GPU_UNPACK_FAILED", "Unsafe wheel member")
                    destination = staging.joinpath(*name.parts)
                    if member.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, destination.open("wb") as target:
                            shutil.copyfileobj(source, target)
        _cancel(cancel_event)
        with GPUWorker(staging, cancel_event=cancel_event) as worker:
            evidence = worker.request(
                {"op": "probe", "model_path": str(model_path() if model is None else model_path(model))}
            )
        if evidence.get("cuda_nodes", 0) <= 0:
            raise GPURuntimeError("GPU_DEVICE_INCOMPATIBLE", "No verified CUDA execution")
        evidence["files"] = [
            {"path": str(path.relative_to(staging)), "size": path.stat().st_size, "sha256": _identity(path)}
            for path in staging.rglob("*")
            if path.is_file()
        ]
        _cancel(cancel_event)
        (staging / "verified.json").write_text(json.dumps(evidence), encoding="utf-8")
        destination = root / ("verified-" + uuid.uuid4().hex)
        rename_path(staging, destination, replace=True, retry_delays=DOWNLOAD_RENAME_DELAYS)
        staging = None
        temporary = root / (".active-" + uuid.uuid4().hex)
        temporary.write_text(json.dumps({"directory": destination.name}), encoding="utf-8")
        rename_path(temporary, root / "active.json", replace=True, retry_delays=DOWNLOAD_RENAME_DELAYS)
        return _status("ready")
    except Exception as error:
        code = getattr(error, "code", "GPU_UNPACK_FAILED")
        return _status("paused" if code == "GPU_CANCELLED" else "failed", {"code": code, "message": str(error)})
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def close_cancelled_workers(events):
    """Reap this owner's workers before the desktop host can call os._exit."""
    with _LOCK:
        workers = [worker for worker in _WORKERS if worker.cancel_event in events]
    for worker in workers:
        worker.close()


class GPUWorker:
    """A task-owned external process; no GPU module is imported in the host."""

    def __init__(self, runtime_dir=None, *, cancel_event=None, command=None):
        if runtime_dir is None:
            root = runtime_root()
            runtime_dir = root / json.loads((root / "active.json").read_text())["directory"]
        self.runtime_dir = Path(runtime_dir)
        self.cancel_event = cancel_event
        if command is None:
            if getattr(sys, "frozen", False):
                executable = Path(sys._MEIPASS) / "gpu-worker" / "gam-gpu-worker.exe"
                command = [str(executable)]
            else:
                command = [sys.executable, "-I", str(Path(__file__).parents[2] / "scripts/gam_gpu_worker.py")]
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "CUDA"))}
        if sys.platform == "win32":
            env["PATH"] = os.pathsep.join(
                [env.get("SystemRoot", "C:\\Windows") + "\\System32", env.get("SystemRoot", "C:\\Windows")]
            )
        self.process = None
        self._reader = None
        self._close_lock = threading.Lock()
        self._owns_slot = False
        while not _WORKER_SLOT.acquire(timeout=0.1):
            _cancel(cancel_event)
        self._owns_slot = True
        try:
            with _LOCK:
                _cancel(cancel_event)
                self._start(command, env)
                _WORKERS.add(self)
        except Exception as error:
            self.close()
            if isinstance(error, GPURuntimeError):
                raise
            raise GPURuntimeError("GPU_PROCESS_FAILED", str(error)) from error

    def _start(self, command, env):
        self.process = subprocess.Popen(
            [*command, str(self.runtime_dir)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self.responses = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.responses.put(json.loads(line))
                except ValueError:
                    self.responses.put({"error": {"code": "GPU_PROTOCOL_FAILED", "message": "Invalid GPU response"}})
        except (OSError, ValueError):
            pass
        self.responses.put(
            {"error": {"code": "GPU_PROCESS_FAILED", "message": f"GPU worker exited ({self.process.poll()})"}}
        )

    def request(self, message, timeout=180):
        try:
            return self._request(message, timeout)
        except Exception:
            self.close()
            raise

    def _request(self, message, timeout):
        import time

        _cancel(self.cancel_event)
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise GPURuntimeError("GPU_PROCESS_FAILED", str(error)) from error
        deadline = time.monotonic() + timeout
        while True:
            _cancel(self.cancel_event)
            if time.monotonic() > deadline:
                raise GPURuntimeError("GPU_PROCESS_FAILED", "GPU worker timed out")
            try:
                response = self.responses.get(timeout=0.1)
                break
            except queue.Empty:
                pass
        if not isinstance(response, dict):
            raise GPURuntimeError("GPU_PROTOCOL_FAILED", "Invalid GPU response object")
        if "error" in response:
            error = response["error"]
            if (
                not isinstance(error, dict)
                or not isinstance(error.get("code"), str)
                or not isinstance(error.get("message"), str)
            ):
                raise GPURuntimeError("GPU_PROTOCOL_FAILED", "Invalid GPU error response")
            raise GPURuntimeError(error["code"], error["message"])
        if message.get("op") == "infer" and (
            response.get("output") != message.get("output") or response.get("finite_alpha") is not True
        ):
            raise GPURuntimeError("GPU_PROTOCOL_FAILED", "Invalid GPU frame response")
        if message.get("op") == "probe" and not isinstance(response.get("cuda_nodes"), int):
            raise GPURuntimeError("GPU_PROTOCOL_FAILED", "Invalid CUDA probe response")
        return response

    def remove_background(self, path, model=None):
        from PIL import Image

        from backend.core.birefnet_onnx import model_path, weights_available

        if not (weights_available() if model is None else weights_available(model)):
            self.close()
            raise GPURuntimeError("GPU_MODEL_INVALID", "BiRefNet model checksum mismatch")

        with tempfile.TemporaryDirectory(prefix="gpu-frame-", dir=data_root()) as temporary:
            output = Path(temporary) / "frame.png"
            self.request(
                {
                    "op": "infer",
                    "input": str(path),
                    "output": str(output),
                    "model_path": str(model_path() if model is None else model_path(model)),
                }
            )
            try:
                with Image.open(output) as image, Image.open(path) as source:
                    if image.mode != "RGBA" or image.size != source.size:
                        raise ValueError("GPU frame dimensions or alpha mode do not match input")
                    return image.copy()
            except (OSError, ValueError) as error:
                self.close()
                raise GPURuntimeError("GPU_PROTOCOL_FAILED", str(error)) from error

    def close(self):
        with self._close_lock:
            try:
                if self.process is not None:
                    if self.process.poll() is None:
                        self.process.terminate()
                        try:
                            self.process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            self.process.kill()
                            self.process.wait()
                    if self._reader is not None:
                        self._reader.join(timeout=2)
                    for stream in (self.process.stdin, self.process.stdout):
                        stream.close()
            finally:
                with _LOCK:
                    _WORKERS.discard(self)
                if self._owns_slot:
                    self._owns_slot = False
                    _WORKER_SLOT.release()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
