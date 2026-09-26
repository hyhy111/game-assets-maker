from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

MODEL_CAPABILITIES = {
    "standard": {
        "id": "doubao-seedance-2-0-260128",
        "resolutions": ("480p", "720p", "1080p"),
    },
    "fast": {
        "id": "doubao-seedance-2-0-fast-260128",
        "resolutions": ("480p", "720p"),
    },
    "mini": {
        "id": "doubao-seedance-2-0-mini-260615",
        "resolutions": ("480p", "720p"),
    },
}


@dataclass(slots=True)
class SeedanceRequest:
    first_frame: Path
    last_frame: Path | None = None
    prompt: str = ""
    model: str = "standard"
    resolution: str = "720p"
    ratio: str = "adaptive"
    duration: int = 5
    generate_audio: bool = False
    return_last_frame: bool = False
    priority: int = 0
    execution_expires_after: int = 172800

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["first_frame"] = str(self.first_frame)
        data["last_frame"] = str(self.last_frame) if self.last_frame is not None else None
        return data

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "SeedanceRequest":
        if not isinstance(values, dict):
            raise ValueError("Seedance request must be an object")
        allowed = {field.name for field in fields(cls)}
        if "first_frame" not in values:
            raise ValueError("Missing required Seedance request field: first_frame")
        data = {key: value for key, value in values.items() if key in allowed}
        data["first_frame"] = Path(data["first_frame"])
        if data.get("last_frame") is not None:
            data["last_frame"] = Path(data["last_frame"])
        return cls(**data)


@dataclass(slots=True)
class SeedanceTask:
    local_id: str
    remote_id: str | None
    remote_status: str
    sync_status: dict[str, Any]
    download_status: str
    cache_status: str
    request: dict[str, Any]
    input_paths: dict[str, str]
    output_paths: dict[str, str]
    created_at: str
    updated_at: str
    finished_at: str | None
    remote: dict[str, Any]
    error: dict[str, Any] | None
    retry_of: str | None
    handoffs: list[dict[str, Any]]
    download_url_received_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "SeedanceTask":
        if not isinstance(values, dict):
            raise ValueError("Seedance task must be an object")
        allowed = {field.name for field in fields(cls)}
        data = {key: value for key, value in values.items() if key in allowed}
        data.setdefault("download_url_received_at", None)
        missing = sorted(allowed - data.keys())
        if missing:
            raise ValueError(f"Missing required Seedance task field: {missing[0]}")
        return cls(**data)
