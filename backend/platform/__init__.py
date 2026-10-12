"""ForFuner platform (ruoyi-app) integration: client, config, and adapters."""

from backend.platform.client import (
    PlatformClient,
    PlatformError,
    PlatformUnauthorizedError,
    new_idem_key,
)
from backend.platform.config import PlatformConfig
from backend.platform.downloads import PlatformArtifactTransport
from backend.platform.images import PlatformImageClient
from backend.platform.last_frame import extract_last_frame
from backend.platform.video import ARTIFACT_URL_PREFIX, PlatformVideoClient

__all__ = [
    "ARTIFACT_URL_PREFIX",
    "PlatformArtifactTransport",
    "PlatformClient",
    "PlatformConfig",
    "PlatformError",
    "PlatformImageClient",
    "PlatformUnauthorizedError",
    "PlatformVideoClient",
    "extract_last_frame",
    "new_idem_key",
]
