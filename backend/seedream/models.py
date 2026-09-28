from dataclasses import asdict, dataclass, fields
from typing import Any

MODEL_CAPABILITIES = {
    "pro": {
        "id": "doubao-seedream-5-0-pro-260628",
        "resolutions": ("1K", "1.5K", "2K"),
    },
    "flash": {
        "id": "doubao-seedream-5-0-flash-260915",
        "resolutions": ("1K", "1.5K", "2K"),
    },
    "lite": {
        "id": "doubao-seedream-5-0-260128",
        "resolutions": ("2K",),
    },
}


def platform_model_id(model: str) -> str:
    """平台源下发给上游的模型标识。

    平台源下 model 有两类取值：直连模式的本地短键（"pro", "flash", "lite"），
    以及能力清单返回的上游 ID。这里把两者统一归一到上游 ID，
    且**上游 ID 原样透传**——否则运营上新模型时，客户端会因本地表查不到而失败。
    """
    capability = MODEL_CAPABILITIES.get(model)
    return capability["id"] if capability else model


@dataclass(slots=True)
class SeedreamRequest:
    prompt: str = ""
    model: str = "pro"
    resolution: str = "1K"
    ratio: str = "16:9"
    count: int = 2
    reference_image: str | None = None
    # 'api-key' = direct Ark with the user's own key; 'forfuner-ai' = platform.
    source: str = "api-key"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "SeedreamRequest":
        if not isinstance(values, dict):
            raise ValueError("Seedream request must be an object")
        allowed = {field.name for field in fields(cls)}
        data = {key: value for key, value in values.items() if key in allowed}
        return cls(**data)


@dataclass(slots=True)
class ImageAttempt:
    local_id: str
    index: int
    status: str
    request: dict[str, Any]
    response: dict[str, Any]
    local_path: str | None
    created_at: str
    updated_at: str
    finished_at: str | None
    error: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "ImageAttempt":
        if not isinstance(values, dict):
            raise ValueError("Image attempt must be an object")
        required = {field.name for field in fields(cls)}
        missing = sorted(required - values.keys())
        if missing:
            raise ValueError(f"Missing required Image attempt field: {missing[0]}")
        return cls(**{key: values[key] for key in required})


@dataclass(slots=True)
class ImageBatch:
    local_id: str
    request: dict[str, Any]
    attempts: list[ImageAttempt]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_id": self.local_id,
            "request": self.request,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "ImageBatch":
        if not isinstance(values, dict):
            raise ValueError("Image batch must be an object")
        attempts = [
            ImageAttempt.from_dict(item) if isinstance(item, dict) else item
            for item in values.get("attempts", [])
        ]
        return cls(
            local_id=values["local_id"],
            request=values["request"],
            attempts=attempts,
            created_at=values["created_at"],
            updated_at=values["updated_at"],
        )
