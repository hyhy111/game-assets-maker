"""Atomic downloads for completed Seedance task results."""

import os
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import cv2
from PIL import Image

from backend.seedance.models import SeedanceTask
from backend.seedance.repository import TaskRepository


class DownloadTransport(Protocol):
    def download(self, url: str) -> bytes: ...


class UrllibDownloadTransport:
    def download(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=30.0) as response:
            return response.read()


class ResultDownloader:
    def __init__(self, repository: TaskRepository, transport: DownloadTransport | None = None) -> None:
        self._repository = repository
        self._transport = transport or UrllibDownloadTransport()

    def download_task(self, task: SeedanceTask) -> SeedanceTask:
        current, claimed = self._claim(task.local_id)
        if not claimed:
            return current

        downloaded_paths: dict[str, str] = {}
        try:
            content = current.remote.get("content")
            if not isinstance(content, dict) or not isinstance(content.get("video_url"), str):
                raise ValueError("Completed task is missing a video URL")

            video_path = self._repository.resolve_asset(current.local_id, "output/video.mp4")
            self._download_to(content["video_url"], video_path, self._validate_video)
            downloaded_paths["video"] = "output/video.mp4"

            last_frame_url = content.get("last_frame_url")
            if last_frame_url is not None:
                if not isinstance(last_frame_url, str):
                    raise ValueError("Completed task has an invalid last-frame URL")
                last_frame_path = self._repository.resolve_asset(current.local_id, "output/returned_last_frame.png")
                self._download_to(last_frame_url, last_frame_path, self._validate_image)
                downloaded_paths["returned_last_frame"] = "output/returned_last_frame.png"
            return self._finish(current.local_id, downloaded_paths, "downloaded")
        except Exception:
            self._finish(current.local_id, downloaded_paths, "failed")
            raise

    def is_download_confirmed(self, task: SeedanceTask) -> bool:
        """Return whether the persisted downloaded result is still readable locally."""
        if task.download_status != "downloaded":
            return False
        try:
            self._validate_downloaded_paths(task.local_id, task.output_paths)
        except (OSError, RuntimeError, ValueError):
            return False
        return True

    def _claim(self, local_id: str) -> tuple[SeedanceTask, bool]:
        with self._repository.task_lock(local_id):
            current = self._repository._read_unlocked(local_id)
            if current.download_status in {"downloading", "downloaded"}:
                return current, False
            current.download_status = "downloading"
            self._repository._write_unlocked(current)
            return current, True

    def _finish(self, local_id: str, downloaded_paths: dict[str, str], status: str) -> SeedanceTask:
        with self._repository.task_lock(local_id):
            current = self._repository._read_unlocked(local_id)
            if current.download_status != "downloading":
                return current
            if status == "downloaded":
                self._validate_downloaded_paths(local_id, downloaded_paths)
            current.output_paths.update(downloaded_paths)
            current.download_status = status
            if status == "downloaded":
                current.cache_status = "complete"
            self._repository._write_unlocked(current)
            return current

    def _validate_downloaded_paths(self, local_id: str, downloaded_paths: dict[str, str]) -> None:
        video_relative_path = downloaded_paths.get("video")
        if video_relative_path is None:
            raise RuntimeError("Downloaded video disappeared before finalization")
        video_path = self._repository.resolve_asset(local_id, video_relative_path)
        if not video_path.is_file():
            raise RuntimeError("Downloaded video disappeared before finalization")
        self._validate_video(video_path)

        last_frame_relative_path = downloaded_paths.get("returned_last_frame")
        if last_frame_relative_path is not None:
            last_frame_path = self._repository.resolve_asset(local_id, last_frame_relative_path)
            if not last_frame_path.is_file():
                raise RuntimeError("Downloaded last frame disappeared before finalization")
            self._validate_image(last_frame_path)

    def _download_to(self, url: str, destination: Path, validate: Callable[[Path], None]) -> None:
        content = self._transport.download(url)
        temporary_path = destination.with_suffix(f"{destination.suffix}.part")
        with temporary_path.open("wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        if not content:
            raise ValueError(f"Downloaded {destination.name} is empty")
        validate(temporary_path)
        os.replace(temporary_path, destination)

    @staticmethod
    def _validate_video(path: Path) -> None:
        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                raise ValueError("Downloaded video is not a readable MP4")
        finally:
            capture.release()

    @staticmethod
    def _validate_image(path: Path) -> None:
        with Image.open(path) as image:
            image.verify()
