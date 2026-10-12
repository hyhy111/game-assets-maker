"""
Game Assets Maker - PyWebView Backend
Desktop application using PyWebView + Vue 3 frontend
"""

import json
import mimetypes
import os
import shutil
import sys
import threading
from collections.abc import Callable
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from queue import Empty, Queue
from socketserver import TCPServer
from typing import Any
from urllib.parse import unquote, urlsplit

import webview

from src.utils.app_config import current_storage_locations, save_app_config
from src.utils.data_paths import data_root
from src.utils.storage_migration import StorageMigrationCoordinator

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# API imports moved inside API class properties for lazy loading

# Top-level data directories the assets server may expose over HTTP. The data
# root also holds config.json (credentials), so nothing outside these
# allowlisted prefixes is served.
_STATIC_ASSET_PREFIXES = ("project", "cache")

_SUBSCRIPTION_CLOSE_BUTTON_SCRIPT = """
(() => {
  const id = 'gam-subscription-close';
  if (document.getElementById(id)) return;

  const button = document.createElement('button');
  button.id = id;
  button.type = 'button';
  button.setAttribute('aria-label', '关闭订阅窗口');
  button.title = '关闭';
  button.textContent = '×';
  Object.assign(button.style, {
    position: 'fixed',
    top: '12px',
    right: '12px',
    width: '34px',
    height: '34px',
    border: '1px solid rgba(255, 255, 255, 0.18)',
    borderRadius: '9999px',
    background: 'rgba(10, 10, 12, 0.82)',
    color: '#f5f2ea',
    font: '24px/30px -apple-system, BlinkMacSystemFont, sans-serif',
    cursor: 'pointer',
    zIndex: '2147483647',
    backdropFilter: 'blur(8px)',
  });
  button.addEventListener('click', () => {
    void window.pywebview.api.close_subscription_window();
  });
  document.body.appendChild(button);
})();
"""


def _configure_native_window_controls(window) -> None:
    """Hide the title text field and keep native window buttons active.

    On macOS 26 the title text field of an untreated window sits at the
    top-left of the titlebar and swallows clicks aimed at the native
    close/minimize/zoom buttons; hiding title visibility removes it from
    hit-testing. Must run on Cocoa's main thread.
    """
    try:
        import AppKit

        native_window = getattr(window, "native", None)
        if not native_window:
            return

        native_window.setTitleVisibility_(AppKit.NSWindowTitleHidden)

        button_types = (
            AppKit.NSWindowCloseButton,
            AppKit.NSWindowMiniaturizeButton,
            AppKit.NSWindowZoomButton,
        )
        for button_type in button_types:
            button = native_window.standardWindowButton_(button_type)
            if button:
                button.setHidden_(False)
                button.setEnabled_(True)
    except Exception as e:
        print(f"Failed to configure macOS window controls: {e}")


def schedule_macos_window_controls(window) -> None:
    """Apply _configure_native_window_controls on Cocoa's main thread."""
    if sys.platform != "darwin" or window is None:
        return

    try:
        from PyObjCTools import AppHelper

        AppHelper.callAfter(_configure_native_window_controls, window)
    except Exception as e:
        print(f"Failed to schedule macOS window controls configuration: {e}")


def build_restart_command() -> list[str]:
    """Build the os.execv command used to restart the app in place.

    Frozen builds re-exec the packaged executable with its original
    arguments; source runs re-exec the current interpreter as
    ``python -m backend.main`` so the module entry point is preserved (and
    dev_start.py keeps waiting on the same backend process instead of
    shutting the Vite dev server down early).
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, "-m", "backend.main", *sys.argv[1:]]


def start_assets_server(
    root_dir: str,
    port: int = 0,
    stop_event: threading.Event | None = None,
    seedance_media_resolver=None,
    seedream_media_resolver=None,
    startup_queue: Queue | None = None,
    project_media_root: Path | None = None,
):
    """Start a lightweight HTTP server for serving frame assets"""

    class CORSRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root_dir, **kwargs)

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

        def do_GET(self):
            if self._serve_seedance_media():
                return
            if self._serve_seedream_media():
                return
            if self._serve_project_media():
                return
            if not self._static_path_allowed():
                return
            super().do_GET()

        def do_HEAD(self):
            if self._serve_seedance_media(head_only=True):
                return
            if self._serve_seedream_media(head_only=True):
                return
            if self._serve_project_media(head_only=True):
                return
            if not self._static_path_allowed():
                return
            super().do_HEAD()

        def _static_path_allowed(self) -> bool:
            # Decode before splitting, then validate the same translated path
            # the file handler opens, including any symlink destinations.
            segments = unquote(urlsplit(self.path).path).split("/")
            try:
                root = Path(self.directory).resolve()
                relative = Path(self.translate_path(self.path)).resolve().relative_to(root)
                allowed = (
                    relative.parts
                    and relative.parts[0] in _STATIC_ASSET_PREFIXES
                    and not any(segment in (".", "..") for segment in segments)
                )
            except (OSError, RuntimeError, ValueError):
                allowed = False
            if not allowed:
                self.send_error(404)
                return False
            return True

        def _serve_seedance_media(self, head_only: bool = False) -> bool:
            parsed = urlsplit(self.path)
            segments = parsed.path.split("/")
            if len(segments) < 2 or segments[1] != "seedance-media":
                return False
            if len(segments) != 4:
                self.send_error(404)
                return True
            if seedance_media_resolver is None:
                self.send_error(404)
                return True
            local_id = unquote(segments[2])
            asset_key = unquote(segments[3])
            try:
                asset_path = seedance_media_resolver.resolve(local_id, asset_key)
                content_length = asset_path.stat().st_size
            except (FileNotFoundError, OSError, ValueError):
                self.send_error(404)
                return True

            mime_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(content_length))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not head_only:
                with asset_path.open("rb") as asset_file:
                    shutil.copyfileobj(asset_file, self.wfile)
            return True

        def _serve_seedream_media(self, head_only: bool = False) -> bool:
            parsed = urlsplit(self.path)
            segments = parsed.path.split("/")
            if len(segments) < 2 or segments[1] != "seedream-media":
                return False
            if len(segments) not in (4, 5):
                self.send_error(404)
                return True
            if seedream_media_resolver is None:
                self.send_error(404)
                return True
            local_id = unquote(segments[2])
            asset_key = unquote(segments[3])
            attempt_index = 0
            if len(segments) == 5:
                try:
                    attempt_index = int(unquote(segments[4]))
                except ValueError:
                    self.send_error(404)
                    return True
            try:
                asset_path = seedream_media_resolver.resolve(local_id, asset_key, attempt_index)
                content_length = asset_path.stat().st_size
            except (FileNotFoundError, OSError, ValueError):
                self.send_error(404)
                return True

            mime_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(content_length))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not head_only:
                with asset_path.open("rb") as asset_file:
                    shutil.copyfileobj(asset_file, self.wfile)
            return True

        def _serve_project_media(self, head_only: bool = False) -> bool:
            """Serve project media from the explicit, resolved project root.

            The project root may live outside the data root when the user
            configured a custom location; only resources that resolve inside
            that root are served, so the mapping never widens local file
            exposure to the chosen directory's parents or siblings.
            """
            parsed = urlsplit(self.path)
            prefix = "/project-media/"
            if not parsed.path.startswith(prefix):
                return False
            if project_media_root is None:
                self.send_error(404)
                return True
            raw_segments = parsed.path[len(prefix) :].split("/")
            decoded_segments = [unquote(segment) for segment in raw_segments]
            if not raw_segments or any(segment in ("", ".", "..") for segment in raw_segments + decoded_segments):
                self.send_error(404)
                return True
            try:
                root = Path(project_media_root).resolve()
                asset_path = root.joinpath(*decoded_segments).resolve()
                asset_path.relative_to(root)
            except (OSError, RuntimeError, ValueError):
                self.send_error(404)
                return True
            if not asset_path.is_file():
                self.send_error(404)
                return True

            mime_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(asset_path.stat().st_size))
            self.end_headers()
            if not head_only:
                with asset_path.open("rb") as asset_file:
                    shutil.copyfileobj(asset_file, self.wfile)
            return True

        def log_message(self, format, *args):
            # Suppress logs
            pass

    class ReusableTCPServer(TCPServer):
        allow_reuse_address = True

    started = False
    try:
        with ReusableTCPServer(("127.0.0.1", port), CORSRequestHandler) as httpd:
            actual_port = int(httpd.server_address[1])
            print(f"Assets server started at http://127.0.0.1:{actual_port}")
            if startup_queue is not None:
                startup_queue.put(actual_port)
            started = True
            httpd.timeout = 0.1
            while stop_event is None or not stop_event.is_set():
                httpd.handle_request()
    except OSError as e:
        if startup_queue is not None and not started:
            startup_queue.put(e)
        print(f"Failed to start assets server on port {port}: {e}")
        raise


class SubscriptionWindowBridge:
    """订阅落地页隔离窗专用 pywebview 桥。

    js_api 会把对象的所有公开方法暴露给页面，独立小类把暴露面物理限定为
    close_subscription_window 这一个无副作用函数；主窗 API 类（文件系统、
    项目等能力）结构上不可能被带进来。落地页为自有域名静态页。
    """

    def __init__(self):
        self._window = None

    def _set_window(self, window) -> None:
        self._window = window

    def close_subscription_window(self) -> bool:
        try:
            if self._window is not None:
                self._window.destroy()
            return True
        except Exception as e:
            # 用户可能已手动关闭窗口，destroy 抛异常属于正常竞态
            print(f"close_subscription_window: {e}")
            return False


class API:
    """
    Main API class exposed to JavaScript via PyWebView
    Combines all API modules into a single interface
    """

    def __init__(
        self,
        window=None,
        assets_base_url: str = "http://localhost:8080",
        restart_handler: Callable[[], dict[str, Any]] | None = None,
        close_handler: Callable[[], dict[str, Any]] | None = None,
    ):
        self._window = window
        self._assets_base_url = assets_base_url.rstrip("/")
        self._restart_handler = restart_handler
        self._close_handler = close_handler
        # Resolve storage roots once at startup; every consumer shares this
        # result until a migration-triggered restart replaces the process.
        self._storage_locations = current_storage_locations()
        self._project_api_instance = None
        self._video_api_instance = None
        self._frame_api_instance = None
        self._process_api_instance = None
        self._config_api_instance = None
        self._batch_trim_api_instance = None
        self._audio_api_instance = None
        self._seedance_api_instance = None
        self._seedream_api_instance = None
        self._seedream_exit_confirmed = False
        self._storage_settings_api_instance = None
        # One app-level coordinator owns the migration mutex, the one-shot
        # confirmation token and the post-commit restart-required state.
        # Activity providers read the lazily-created API instances directly so
        # a settings save never spawns managers just to check for activity.
        activity_attributes = {
            "process": "_process_api_instance",
            "batch_trim": "_batch_trim_api_instance",
            "seedream": "_seedream_api_instance",
            "seedance": "_seedance_api_instance",
        }
        self._storage_migration_coordinator = StorageMigrationCoordinator(
            commit_config=save_app_config,
            activity_providers={
                name: lambda attribute=attribute: self._api_has_active_writes(attribute)
                for name, attribute in activity_attributes.items()
            },
            progress_callback=self._dispatch_migration_progress,
        )

        self._subscription_bridge = SubscriptionWindowBridge()
        from backend.platform.config import PlatformConfig
        from backend.platform.trace import trace_event

        self._platform_config = PlatformConfig()
        self._platform_facade_instance = None
        self._trace_event = trace_event

    def _api_has_active_writes(self, instance_attribute: str) -> bool:
        instance = getattr(self, instance_attribute)
        return instance is not None and instance.has_active_writes()

    @property
    def _storage_settings_api(self):
        if self._storage_settings_api_instance is None:
            from backend.api.storage_settings_api import StorageSettingsAPI

            self._storage_settings_api_instance = StorageSettingsAPI(
                coordinator=self._storage_migration_coordinator,
                data_root=data_root(),
            )
        return self._storage_settings_api_instance

    def _dispatch_migration_progress(self, kind: str, copied: int, total: int) -> None:
        """Forward copy progress to the frontend as a DOM CustomEvent."""
        if self._window is None:
            return
        js_code = f"""
            window.dispatchEvent(new CustomEvent('storage-migration-progress', {{
                detail: {{ kind: '{kind}', copied: {copied}, total: {total} }}
            }}));
        """
        try:
            self._window.evaluate_js(js_code)
        except Exception as error:
            print(f"Failed to emit migration progress: {error}")

    @property
    def storage_locations(self):
        """The storage roots resolved once at startup and shared by all APIs."""
        return self._storage_locations

    @property
    def _platform_facade(self):
        """平台源级操作门面（能力清单等，不属于视频/图片任一媒体域）。"""
        if self._platform_facade_instance is None:
            from backend.api.platform_api import PlatformFacade

            self._platform_facade_instance = PlatformFacade(self._platform_config)
        return self._platform_facade_instance

    @property
    def _project_api(self):
        if self._project_api_instance is None:
            from backend.api.project_api import ProjectAPI

            self._project_api_instance = ProjectAPI(projects_root=self._storage_locations.projects_root)
        return self._project_api_instance

    @property
    def _video_api(self):
        if self._video_api_instance is None:
            from backend.api.video_api import VideoAPI

            self._video_api_instance = VideoAPI()
        return self._video_api_instance

    @property
    def _frame_api(self):
        if self._frame_api_instance is None:
            from backend.api.frame_api import FrameAPI

            self._frame_api_instance = FrameAPI(
                self._assets_base_url, projects_root=self._storage_locations.projects_root
            )
        return self._frame_api_instance

    @property
    def _process_api(self):
        if self._process_api_instance is None:
            from backend.api.process_api import ProcessAPI

            self._process_api_instance = ProcessAPI(self._window, projects_root=self._storage_locations.projects_root)
        return self._process_api_instance

    @property
    def _config_api(self):
        if self._config_api_instance is None:
            from backend.api.config_api import ConfigAPI

            self._config_api_instance = ConfigAPI()
        return self._config_api_instance

    @property
    def _batch_trim_api(self):
        if self._batch_trim_api_instance is None:
            from backend.api.batch_trim_api import BatchTrimAPI

            self._batch_trim_api_instance = BatchTrimAPI(projects_root=self._storage_locations.projects_root)
        return self._batch_trim_api_instance

    @property
    def _audio_api(self):
        if self._audio_api_instance is None:
            from backend.api.audio_api import AudioAPI

            self._audio_api_instance = AudioAPI(
                self._assets_base_url, projects_root=self._storage_locations.projects_root
            )
        return self._audio_api_instance

    @property
    def _seedance_api(self):
        if self._seedance_api_instance is None:
            from backend.api.seedance_api import SeedanceAPI

            self._seedance_api_instance = SeedanceAPI(
                project_api=self._project_api,
                window_getter=lambda: self._window,
                media_base_url=self._assets_base_url,
                storage_locations=self._storage_locations,
                platform_config=self._platform_config,
            )
        return self._seedance_api_instance

    @property
    def seedance_media_resolver(self):
        return self._seedance_api.media_resolver

    @property
    def _seedream_api(self):
        if self._seedream_api_instance is None:
            from backend.api.seedream_api import SeedreamAPI

            self._seedream_api_instance = SeedreamAPI(
                window_getter=lambda: self._window,
                media_base_url=self._assets_base_url,
                storage_locations=self._storage_locations,
                platform_config=self._platform_config,
            )
        return self._seedream_api_instance

    @property
    def seedream_media_resolver(self):
        return self._seedream_api.media_resolver

    def set_assets_base_url(self, assets_base_url: str) -> None:
        self._assets_base_url = assets_base_url.rstrip("/")
        if self._frame_api_instance is not None:
            self._frame_api_instance.set_assets_base_url(self._assets_base_url)
        if self._audio_api_instance is not None:
            self._audio_api_instance.set_assets_base_url(self._assets_base_url)
        if self._seedance_api_instance is not None:
            self._seedance_api_instance.set_media_base_url(self._assets_base_url)
        if self._seedream_api_instance is not None:
            self._seedream_api_instance.set_media_base_url(self._assets_base_url)

    def set_window(self, window):
        """Set window reference for evaluate_js"""
        self._window = window
        # Update process_api window only if it's already instantiated
        if self._process_api_instance is not None:
            self._process_api_instance._window = window
        self._seedance_api.set_window(window)
        self._seedream_api.set_window(window)

    def agent_acknowledge(self, request_id: str, result: dict[str, Any]) -> bool:
        """Confirm a completed UI operation from the WebView bridge."""
        operations = getattr(self, "_agent_operations", None)
        return operations is not None and operations.acknowledge(request_id, result)

    # ==================== Credential Crypto ====================
    #
    # 加密保护级别说明：
    # - Windows: DPAPI (CryptProtectData)，密钥派生自当前 Windows 用户主密钥，
    #   密文拷到其他用户/机器无法解密。
    # - 非 Windows 降级: Fernet 对称加密，密钥存当前 GAM User Data 的 .keystore。
    #   仅防"随手翻看"，不防能读本机文件的攻击者。

    @staticmethod
    def _credential_crypto():
        if not hasattr(API, "_credential_crypto_impl"):
            from backend.core.credential_crypto import CredentialCrypto

            API._credential_crypto_impl = CredentialCrypto()
        return API._credential_crypto_impl

    def encrypt_credential(self, plaintext: str) -> str:
        """Encrypt a credential string for local storage (DPAPI on Windows)."""
        return self._credential_crypto().encrypt(plaintext)

    def decrypt_credential(self, ciphertext: str) -> str:
        """Decrypt a credential string previously produced by encrypt_credential."""
        return self._credential_crypto().decrypt(ciphertext)

    # ==================== Project API ====================

    def get_projects(self) -> list[dict[str, Any]]:
        """Get list of all projects"""
        return self._project_api.get_projects()

    def get_roles(self) -> list[dict[str, Any]]:
        """Get list of all roles"""
        return self._project_api.get_roles()

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        """Get project by ID (name)"""
        return self._project_api.get_project(project_id)

    def create_project(self, role: str, action: str, video_path: str, frame_interval: int = 1) -> dict[str, Any]:
        """Create a new project"""
        return self._project_api.create_project(role, action, video_path, frame_interval)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project"""
        return self._project_api.delete_project(project_id)

    def delete_role(self, role: str) -> bool:
        """Delete a role and all action projects under it"""
        return self._project_api.delete_role(role)

    def update_project(self, project_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update project metadata"""
        return self._project_api.update_project(project_id, data)

    def migrate_legacy_projects(self, migrations: Any = "未知") -> dict[str, Any]:
        """Migrate legacy flat projects into role/action directories"""
        return self._project_api.migrate_legacy_projects(migrations)

    def import_legacy_project_directory(self, source_directory: str) -> dict[str, Any]:
        """Copy projects from a user-selected legacy project directory."""
        return self._project_api.import_legacy_project_directory(source_directory)

    # ==================== Video API ====================

    def get_video_info(self, video_path: str) -> dict[str, Any]:
        """Get video file information"""
        return self._video_api.get_video_info(video_path)

    def validate_video(self, video_path: str) -> dict[str, Any]:
        """Validate video for processing"""
        return self._video_api.validate_video(video_path)

    # ==================== Frame API ====================

    def get_frames(
        self, project_id: str, step: int, page: int = 1, page_size: int = 50, use_cache: bool = True
    ) -> dict[str, Any]:
        """Get frames for a project at specific step"""
        return self._frame_api.get_frames(project_id, step, page, page_size, use_cache)

    def get_frame_image(self, frame_path: str) -> str:
        """Get frame image as base64 encoded string"""
        return self._frame_api.get_frame_image(frame_path)

    def get_frame_thumbnail(self, frame_path: str, size: int = 128) -> str:
        """Get frame thumbnail as base64 encoded string"""
        return self._frame_api.get_frame_thumbnail(frame_path, size)

    def get_frame_url(self, frame_path: str) -> str:
        """Get frame image URL for HTTP access"""
        return self._frame_api.get_frame_url(frame_path)

    def get_hidden_frames(self, project_id: str) -> list[str]:
        """Get project frames hidden from Step 2/3 preview and export."""
        return self._frame_api.get_hidden_frames(project_id)

    def set_frame_hidden(self, project_id: str, filename: str, hidden: bool = True) -> dict[str, Any]:
        """Hide or restore one frame without deleting its image file."""
        return self._frame_api.set_frame_hidden(project_id, filename, hidden)

    def restore_hidden_frames(self, project_id: str) -> dict[str, Any]:
        """Restore all project frames to Step 2/3 preview and export."""
        return self._frame_api.restore_hidden_frames(project_id)

    # ==================== Process API ====================

    def start_processing(self, project_id: str, step: int, params: dict[str, Any]) -> str:
        """Start processing task, returns task ID"""
        return self._process_api.start_processing(project_id, step, params)

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get task status and progress"""
        return self._process_api.get_task_status(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        return self._process_api.cancel_task(task_id)

    def get_step_params(self, project_id: str, step: int) -> dict[str, Any]:
        """Get saved parameters for a step"""
        return self._process_api.get_step_params(project_id, step)

    def save_step_params(self, project_id: str, step: int, params: dict[str, Any]) -> bool:
        """Save parameters for a step"""
        return self._process_api.save_step_params(project_id, step, params)

    def get_background_color(self, project_id: str) -> dict[str, Any]:
        """Get background color for a project"""
        return self._process_api.get_background_color(project_id)

    def get_model_status(self, model: str = "u2net") -> dict[str, Any]:
        """Return the shared rembg model preparation state."""
        return self._process_api.get_model_status(model)

    def preload_model(self, model: str = "u2net", source: str | None = None) -> dict[str, Any]:
        """Preload rembg model in background"""
        return self._process_api.preload_model(model, source)

    def retry_model(self, model: str = "u2net", source: str | None = None) -> dict[str, Any]:
        """Retry a failed rembg model preparation."""
        return self._process_api.retry_model(model, source)

    # ==================== Config API ====================

    def get_config(self) -> dict[str, Any]:
        """Get application configuration"""
        return self._config_api.get_config()

    def save_config(self, config: dict[str, Any]) -> bool:
        """Save application configuration"""
        return self._config_api.save_config(config)

    def save_cli_generation_enabled(self, enabled: bool, confirmed: bool = False) -> dict[str, Any]:
        """Save the GUI-confirmed immediate CLI generation preference."""
        from src.utils.app_config import save_cli_generation_enabled

        try:
            config = save_cli_generation_enabled(enabled, confirmed)
            return {"success": True, "cli_generation_enabled": config["cli_generation_enabled"]}
        except (OSError, ValueError):
            return {"success": False}

    def agent_validate_draft(self, kind: str, values: dict[str, Any]) -> dict[str, Any]:
        from backend.agent_control.drafts import validate_draft

        try:
            validate_draft(kind, values)
            return {"success": True}
        except (ValueError, TypeError, OSError) as error:
            return {"success": False, "error": str(error)}

    def agent_submit_generation(self, request_id: str, source: str) -> dict[str, Any]:
        """Submit a registered CLI request through the live application APIs."""
        operations = getattr(self, "_agent_operations", None)
        if operations is None:
            return {"success": False, "error": {"code": "UI_NOT_RUNNING"}}
        return operations.submit_generation(request_id, source)

    def save_ark_audit_enabled(self, enabled: bool) -> dict[str, Any]:
        """Save only the immediate development audit toggle."""
        from src.utils.app_config import save_ark_audit_enabled

        try:
            config = save_ark_audit_enabled(enabled)
            return {"success": True, "ark_audit_enabled": config["ark_audit_enabled"]}
        except (OSError, ValueError):
            return {"success": False}

    # ==================== Storage Settings & Migration API ====================

    def storage_get_settings(self) -> dict[str, Any]:
        """Read persisted storage values plus resolved display paths."""
        return self._storage_settings_api.get_settings()

    def storage_save_settings(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Save the settings draft, or precheck a storage migration."""
        return self._storage_settings_api.save_settings(draft)

    def storage_execute_migration(self, token: str) -> dict[str, Any]:
        """Run the confirmed migration and commit the settings draft."""
        return self._storage_settings_api.execute_migration(token)

    def storage_migration_state(self) -> dict[str, Any]:
        """Report whether a committed migration makes this runtime stale."""
        return {
            "success": True,
            "restart_required": self._storage_migration_coordinator.restart_required,
        }

    def get_available_sizes(self) -> list[int]:
        """Get available pixelization sizes"""
        return [64, 128, 256, 512]

    # ==================== System API ====================

    def select_video_file(self) -> str | None:
        """Open file dialog to select video file"""
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=("Video files (*.mp4;*.avi;*.mov;*.mkv;*.webm)",)
        )
        return result[0] if result else None

    def select_directory(self) -> str | None:
        """Open directory dialog"""
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

    def open_project_folder(self, project_path: str) -> bool:
        """Open project folder in system file manager"""
        try:
            from src.utils.system_paths import open_directory

            open_directory(Path(project_path))
            return True
        except Exception as e:
            print(f"Error opening folder: {e}")
            return False

    def get_app_version(self) -> str:
        """Get application version"""
        return "2.0.0"

    # ==================== App Lifecycle API ====================

    def request_app_restart(self) -> dict[str, Any]:
        """Request a one-shot in-place application restart.

        Called by the settings page after a successful storage migration.
        The bridge only records the restart intent and starts the window
        close flow; the actual restart happens in MainApp.run() once the
        regular closed-event cleanup has completed.
        """
        if self._restart_handler is None:
            return {"success": False, "error": "restart handler unavailable"}
        return self._restart_handler()

    def close_app(self) -> dict[str, Any]:
        """Close the main window without requesting a restart.

        Called from the restart-required overlay when the user chooses to
        close instead of restarting. Routing through the backend keeps the
        regular closed-event cleanup (local server, agent server, managers)
        instead of relying on JS ``window.close()``, which PyWebView does not
        reliably route to native window destruction.
        """
        if self._close_handler is None:
            return {"success": False, "error": "close handler unavailable"}
        return self._close_handler()

    def open_subscription_window(self, url: str) -> bool:
        """Open subscription landing page in an isolated PyWebView window.

        js_api=SubscriptionWindowBridge() so the landing page can close this
        window via the one exposed function (security: bridge carries no other
        capability; token travels in the URL fragment, not the bridge).
        """
        try:
            if not url or not url.startswith(("http://", "https://")):
                print(f"open_subscription_window: invalid url {url!r}")
                return False
            # PyWebView's Cocoa backend schedules child-window creation on the
            # AppKit main thread. Keep this call on the JS API worker thread so
            # PyWebView recognizes it as a child window and creates it now.
            return self._create_subscription_window(url)
        except Exception as e:
            print(f"Error opening subscription window: {e}")
            return False

    def _create_subscription_window(self, url: str) -> bool:
        try:
            bridge = SubscriptionWindowBridge()
            window = webview.create_window(
                "",
                url,
                js_api=bridge,
                width=520,
                height=720,
                resizable=True,
            )
            if window is None:
                return False
            bridge._set_window(window)
            # Remove the titlebar text field from hit-testing as soon as the
            # window is shown, so the native close button stays clickable.
            window.events.shown += lambda: schedule_macos_window_controls(window)
            window.events.loaded += lambda: self._inject_subscription_close_button(window)
            return True
        except Exception as e:
            print(f"Error creating subscription window: {e}")
            return False

    @staticmethod
    def _inject_subscription_close_button(window) -> None:
        try:
            window.evaluate_js(_SUBSCRIPTION_CLOSE_BUTTON_SCRIPT)
        except Exception as e:
            print(f"Error adding subscription window close button: {e}")

    # ==================== Batch Trim API ====================

    def check_projects_for_trim(self, project_ids: list[str]) -> list[dict[str, Any]]:
        """Check whether multiple projects are available for trimming."""
        return self._batch_trim_api.check_projects(project_ids)

    def execute_batch_trim(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute batch trimming."""
        return self._batch_trim_api.execute_trim(params)

    # ==================== Audio API ====================

    def extract_source_audio(self, project_id: str) -> dict[str, Any]:
        """抽取源视频音轨为 wav 并缓存，返回 wav URL + source_fps + total_frames。"""
        return self._audio_api.extract_source_audio(project_id)

    def load_timeline(self, project_id: str) -> dict[str, Any]:
        """读取 audio_timeline.json，返回 AudioTimeline 对象（未保存返空默认）。"""
        return self._audio_api.load_timeline(project_id)

    def save_timeline(self, project_id: str, timeline: dict[str, Any]) -> dict[str, Any]:
        """写入 audio_timeline.json，缺失的元数据从 source_meta.json 回填。"""
        return self._audio_api.save_timeline(project_id, timeline)

    # ==================== Seedance API ====================

    def seedance_select_image_file(self) -> str | None:
        return self._seedance_api.select_image_file()

    def seedance_get_editable_image(self, source_path: str) -> dict[str, Any]:
        return self._seedance_api.get_editable_image(source_path)

    def seedance_save_edited_image(
        self,
        source_path: str,
        image_data_url: str,
        edit_source_data_url: str,
        generation_layout: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._seedance_api.save_edited_image(
            source_path, image_data_url, edit_source_data_url, generation_layout
        )

    def seedance_save_video(self, local_id: str) -> dict[str, Any]:
        return self._seedance_api.save_video(local_id)

    def seedance_open_video_directory(self, local_id: str) -> dict[str, Any]:
        return self._seedance_api.open_video_directory(local_id)

    def seedance_create_task(self, request: dict[str, Any], source: str = "api-key") -> dict[str, Any]:
        return self._seedance_api.create_task(request, source)

    def seedance_quote_video(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._seedance_api.quote_video(request)

    def get_platform_capabilities(self) -> dict[str, Any]:
        """平台可售能力清单（视频/图片共用一份）。"""
        return self._platform_facade.capabilities()

    def seedream_quote_image(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._seedream_api.quote_image(request)

    def seedance_validate_request(self, request: dict[str, Any], source: str = "api-key") -> dict[str, Any]:
        return self._seedance_api.validate_request(request, source)

    def seedance_list_tasks(self) -> dict[str, Any]:
        return self._seedance_api.list_tasks()

    def seedance_get_task(self, local_id: str) -> dict[str, Any]:
        return self._seedance_api.get_task(local_id)

    def seedance_get_regeneration_draft(self, local_id: str) -> dict[str, Any]:
        return self._seedance_api.get_regeneration_draft(local_id)

    def seedance_get_continuation_draft(self, local_id: str) -> dict[str, Any]:
        return self._seedance_api.get_continuation_draft(local_id)

    def seedance_cancel_task(self, local_id: str) -> dict[str, Any]:
        return self._seedance_api.cancel_task(local_id)

    def seedance_retry_task(self, local_id: str) -> dict[str, Any]:
        return self._seedance_api.retry_task(local_id)

    def seedance_retry_download(self, local_id: str) -> dict[str, Any]:
        return self._seedance_api.retry_download(local_id)

    def seedance_continue_task(self, local_id: str) -> dict[str, Any]:
        return self._seedance_api.continue_task(local_id)

    def seedance_delete_task(self, local_id: str, allow_protected: bool = False) -> dict[str, Any]:
        return self._seedance_api.delete_task(local_id, allow_protected)

    def seedance_handoff(self, local_id: str, role: str, action: str) -> dict[str, Any]:
        return self._seedance_api.handoff(local_id, role, action)

    def seedance_get_settings(self) -> dict[str, Any]:
        return self._seedance_api.get_settings()

    def seedance_save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        result = self._seedance_api.save_settings(settings)
        # The shared Ark key also backs image generation, but the Seedance
        # save only rebuilds the video manager. Swap the Seedream client
        # too so new batches use the new key without an app restart.
        if (
            result.get("success")
            and isinstance(settings, dict)
            and "api_key" in settings
            and self._seedream_api_instance is not None
        ):
            self._seedream_api_instance.refresh_client()
        return result

    def seedance_test_connection(self, api_key: str | None = None) -> dict[str, Any]:
        return self._seedance_api.test_connection(api_key)

    def seedance_cache_status(self) -> dict[str, Any]:
        return self._seedance_api.cache_status()

    def seedance_clean_cache(self, older_than_days: int | None = None) -> dict[str, Any]:
        return self._seedance_api.clean_cache(older_than_days)

    # ==================== Seedream API ====================

    def seedream_select_image_file(self) -> str | None:
        return self._seedream_api.select_image_file()

    def seedream_import_reference_image(self, image_data_url: str, filename: str = "") -> dict[str, Any]:
        return self._seedream_api.import_reference_image(image_data_url, filename)

    def seedream_create_batch(self, request: dict[str, Any], source: str = "api-key") -> dict[str, Any]:
        return self._seedream_api.create_batch(request, source)

    # ==================== Platform (ForFuner AI) ====================

    def set_platform_config(self, base_url: str, token: str | None) -> dict[str, Any]:
        """Push platform base URL + app JWT into the Python backend.

        Called by the frontend whenever auth state changes. Token lives only in
        process memory and is never persisted or logged.
        """
        try:
            self._seedance_api.update_platform(base_url, token)
            self._seedream_api.update_platform(base_url, token)
            # 只记"有没有 token"，绝不记 token 本身——这条日志用于确认前端推送是否到达。
            self._trace_event(
                f"platform config updated base_url={base_url or '(empty)'} token={'present' if token else 'absent'}"
            )
            return {"success": True}
        except Exception as error:
            self._trace_event(f"platform config update FAILED: {error}")
            return {"success": False, "error": str(error)}

    def seedream_get_batch(self, local_id: str) -> dict[str, Any]:
        return self._seedream_api.get_batch(local_id)

    def seedream_list_batches(self) -> dict[str, Any]:
        return self._seedream_api.list_batches()

    def seedream_save_image(self, local_id: str, attempt_index: int = 0) -> dict[str, Any]:
        return self._seedream_api.save_image(local_id, attempt_index)

    def seedream_open_image_directory(self, local_id: str, attempt_index: int = 0) -> dict[str, Any]:
        return self._seedream_api.open_image_directory(local_id, attempt_index)

    def seedream_resize_character(
        self,
        local_id: str,
        attempt_index: int,
        top: int,
        bottom: int,
        target_height: int,
        bottom_distance: int | None = None,
    ) -> dict[str, Any]:
        return self._seedream_api.resize_character(local_id, attempt_index, top, bottom, target_height, bottom_distance)

    def seedream_restore_character(self, local_id: str, attempt_index: int) -> dict[str, Any]:
        return self._seedream_api.restore_character(local_id, attempt_index)

    def seedream_apply_eraser(
        self,
        local_id: str,
        attempt_index: int,
        image_data_url: str,
        edit_source_data_url: str,
        generation_layout: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._seedream_api.apply_eraser(
            local_id, attempt_index, image_data_url, edit_source_data_url, generation_layout
        )

    def seedream_get_handoff_image(self, local_id: str, attempt_index: int = 0) -> dict[str, Any]:
        return self._seedream_api.get_handoff_image(local_id, attempt_index)

    def seedream_delete_batch(self, local_id: str) -> dict[str, Any]:
        return self._seedream_api.delete_batch(local_id)

    def seedream_get_regeneration_draft(self, local_id: str) -> dict[str, Any]:
        return self._seedream_api.get_regeneration_draft(local_id)

    def seedream_retry_download(self, local_id: str, attempt_index: int = 0) -> dict[str, Any]:
        return self._seedream_api.retry_download(local_id, attempt_index)

    def seedream_get_settings(self) -> dict[str, Any]:
        return self._seedream_api.get_settings()

    def seedream_save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        return self._seedream_api.save_settings(settings)

    def seedream_get_active_attempt_count(self) -> dict[str, Any]:
        """Return the number of currently active image-generation attempts."""
        return self._seedream_api.get_active_attempt_count()

    def seedream_confirm_exit(self) -> dict[str, Any]:
        """Allow the window to close despite active image-generation attempts.

        Called by the frontend after the user explicitly accepts the risk of
        losing unrecoverable results. Guards against repeated cleanup: once
        confirmed, subsequent calls are no-ops and the single ``closed`` event
        drives all shutdown work.
        """
        if self._seedream_exit_confirmed:
            return {"success": True}
        self._seedream_exit_confirmed = True
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception as error:
                print(f"Failed to destroy window during confirmed exit: {error}")
        return {"success": True}


class MainApp:
    """Main application class"""

    def __init__(self):
        self.is_dev = os.environ.get("DEV_MODE") == "1"
        # One-shot restart intent set via the bridge after a storage
        # migration; consumed in run() once webview.start() returns.
        self.restart_requested = False
        self.api = API(restart_handler=self._handle_restart_request, close_handler=self._handle_close_request)
        self.assets_port = 0
        self.stop_event = threading.Event()
        # Signaled by on_window_closed once all shutdown steps were attempted;
        # run() waits for it before the hard process exit.
        self._closed_cleanup_done = threading.Event()
        self._closed_cleanup_failed = False
        self.assets_thread = None
        self.window = None
        self.agent_control_server = None

    def get_url(self) -> str:
        """Get frontend URL based on environment"""
        if self.is_dev:
            return "http://localhost:5173"
        else:
            # Production: use bundled frontend (support PyInstaller onefile/onedir)
            if hasattr(sys, "_MEIPASS"):
                frontend_path = Path(sys._MEIPASS) / "frontend" / "dist" / "index.html"
            else:
                frontend_path = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
            if frontend_path.exists():
                return str(frontend_path)
            else:
                # Fallback to dev server if dist not built
                print(f"Warning: Frontend build not found at {frontend_path}")
                return "http://localhost:5173"

    def _handle_restart_request(self) -> dict[str, Any]:
        """Record the one-shot restart intent and start the close flow.

        Repeated requests are idempotent: the state is set once and the main
        window is destroyed once, while every call reports success so
        duplicate clicks from the settings page are harmless.
        """
        if not self.restart_requested:
            self.restart_requested = True
            if self.window is not None:
                try:
                    self.window.destroy()
                except Exception as error:
                    print(f"Failed to destroy window for restart: {error}")
        return {"success": True, "restart_requested": True}

    def _handle_close_request(self) -> dict[str, Any]:
        """Destroy the main window without setting the restart intent.

        The closed event then runs the regular cleanup and ``webview.start()``
        returns normally, so the process exits instead of restarting.
        """
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception as error:
                print(f"Failed to destroy window for close: {error}")
        return {"success": True, "close_requested": True}

    def _restart_in_place(self) -> None:
        """Replace this process with a fresh app instance via os.execv.

        Replacing the process image (rather than spawning a second instance)
        avoids two instances sharing the WebView profile, config, and caches.
        os.execv inherits the current environment. A failure must not raise:
        migrated data and configuration were already committed, so the user
        can start the app manually and the new configuration takes effect on
        the next launch.
        """
        command = build_restart_command()
        print(f"Restarting application in place: {command}")
        try:
            os.execv(command[0], command)
        except OSError as error:
            print(
                f"In-place restart failed: {error}. "
                "Please start Game Assets Maker manually; "
                "the saved configuration will be applied on the next launch."
            )

    def on_window_closed(self):
        """Handle window closed event"""
        print("Window closed, shutting down...")
        try:
            self.stop_event.set()
            shutdown_steps = (
                (
                    "agent control server",
                    lambda: self.agent_control_server.stop() if self.agent_control_server else None,
                ),
                ("process API", lambda: self.api._process_api.shutdown()),
                (
                    "Seedance API",
                    lambda: self.api._seedance_api_instance.shutdown() if self.api._seedance_api_instance else None,
                ),
                (
                    "Seedream API",
                    lambda: self.api._seedream_api_instance.shutdown() if self.api._seedream_api_instance else None,
                ),
            )
            for name, shutdown in shutdown_steps:
                try:
                    shutdown()
                except Exception as error:
                    self._closed_cleanup_failed = True
                    print(f"Failed to shut down {name}: {error!r}", file=sys.stderr)
        finally:
            # The closed event has finished attempting every cleanup step.
            self._closed_cleanup_done.set()

    def _exit_after_cleanup(self, cleanup_timeout: float = 30.0) -> None:
        """Finish the process after webview.start() has returned.

        pywebview 6.1/Cocoa runs every JS-bridge call on a non-daemon thread
        and delivers its result through ``evaluate_js``, which blocks until
        the Cocoa main thread evaluates it. A bridge call in flight when the
        window closes — the confirm-exit call that destroys the window, or a
        frontend poll racing the close — is never evaluated once the run loop
        stops, so that thread waits forever and interpreter finalization hangs
        joining it. Exit without interpreter finalization after cleanup ends.
        """
        cleanup_finished = self._closed_cleanup_done.wait(timeout=cleanup_timeout)
        if not cleanup_finished:
            print("Timed out waiting for shutdown cleanup; exiting with failure", file=sys.stderr)
        elif self._closed_cleanup_failed:
            print("Shutdown cleanup failed; exiting with failure", file=sys.stderr)
        if self.restart_requested and cleanup_finished and not self._closed_cleanup_failed:
            self._restart_in_place()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0 if cleanup_finished and not self._closed_cleanup_failed else 1)

    def on_window_closing(self):
        """Intercept window close while image-generation attempts are active.

        Returns False to cancel the close when active attempts exist and the
        user has not explicitly confirmed exiting. The frontend shows a warning
        dialog; "still exit" calls ``seedream_confirm_exit`` which sets the
        confirmation flag and destroys the window. In-app navigation never
        reaches this handler, so generation is not interrupted.
        """
        if self.api._seedream_exit_confirmed:
            return None
        seedream_api = self.api._seedream_api_instance
        if seedream_api is None:
            return None
        try:
            result = seedream_api.get_active_attempt_count()
        except Exception:
            return None
        if not isinstance(result, dict) or not result.get("success"):
            return None
        count = 0
        data = result.get("data")
        if isinstance(data, dict):
            raw_count = data.get("active_count")
            if isinstance(raw_count, int):
                count = raw_count
        if count <= 0 or self.window is None:
            return None
        # Cocoa calls this handler on its main thread. evaluate_js waits for that
        # thread, so dispatch the warning only after this callback can return.
        payload = json.dumps({"count": count})
        window = self.window
        threading.Thread(
            target=self._dispatch_seedream_close_warning,
            args=(window, payload),
            name="seedream-close-warning",
            daemon=True,
        ).start()
        return False

    @staticmethod
    def _dispatch_seedream_close_warning(window, payload: str) -> None:
        try:
            window.evaluate_js(
                "window.dispatchEvent(new CustomEvent('seedream-close-requested', { detail: " + payload + " }));"
            )
        except Exception as error:
            print(f"Failed to dispatch seedream close warning: {error}")

    def configure_macos_window_controls(self):
        """Schedule native macOS window control changes on Cocoa's main thread."""
        schedule_macos_window_controls(self.window)

    def run(self):
        """Run the application"""
        # Create main window
        self.window = webview.create_window(
            "Game Assets Maker",
            self.get_url(),
            js_api=self.api,
            width=1400,
            height=900,
            min_size=(1200, 700),
            easy_drag=False,
            text_select=True,
        )

        # Bind the assets server before WebView starts loading media URLs.
        # The server root is the resolved data root, so installed releases
        # serve the same media regardless of the launch directory. Project
        # media is served through an explicit restricted mapping so a custom
        # project root outside the data root stays the only exposed boundary.
        project_root = str(data_root())
        startup_queue = Queue(maxsize=1)
        self.assets_thread = threading.Thread(
            target=start_assets_server,
            args=(
                project_root,
                0,
                self.stop_event,
                self.api.seedance_media_resolver,
                self.api.seedream_media_resolver,
                startup_queue,
            ),
            kwargs={"project_media_root": self.api.storage_locations.projects_root},
            daemon=True,
        )
        self.assets_thread.start()
        try:
            startup_result = startup_queue.get(timeout=5)
        except Empty as error:
            raise RuntimeError("Assets server did not start") from error
        if isinstance(startup_result, OSError):
            raise RuntimeError("Assets server failed to start") from startup_result
        self.assets_port = startup_result
        self.api.set_assets_base_url(f"http://127.0.0.1:{self.assets_port}")
        self.api.set_window(self.window)
        from backend.agent_control.server import AgentControlServer

        self.agent_control_server = AgentControlServer(self.window, api=self.api)
        self.agent_control_server.start()

        if sys.platform == "darwin":
            self.window.events.loaded += self.configure_macos_window_controls

        # Register window closed handler
        self.window.events.closed += self.on_window_closed
        # Intercept close while image-generation attempts are active (#6).
        self.window.events.closing += self.on_window_closing

        # On Windows, debug=True can freeze WebView2, so enable debug only off Windows.
        debug_mode = self.is_dev and sys.platform != "win32"
        # 默认 private_mode=True 会让 WebView2 用临时 profile，
        # localStorage(token/加密凭证)重启即丢；显式指定持久化目录。
        webview.start(
            debug=debug_mode,
            private_mode=False,
            storage_path=str(data_root() / "webview_profile"),
        )

        # webview.start() returns once the window is destroyed; the epilogue
        # waits for the closed-event cleanup, restarts in place when the
        # bridge requested it, and exits without interpreter finalization
        # (see _exit_after_cleanup for why finalization can hang).
        self._exit_after_cleanup()


def main():
    """Entry point"""
    app = MainApp()
    app.run()


def installed_main():
    """Run the installed application against the stable per-user GAM data root."""
    os.environ.setdefault("GAM_DATA_MODE", "installed")
    return main()


if __name__ == "__main__":
    main()
