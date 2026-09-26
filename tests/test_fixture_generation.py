from pathlib import Path

from backend.api.video_api import VideoAPI
from scripts.generate_test_fixtures import generate_compact_videos


def test_private_role_action_videos_become_limited_readable_regression_media(
    test_assets: Path, tmp_path: Path
) -> None:
    source = test_assets / "videos"
    output = tmp_path / "compact"

    generated = generate_compact_videos(source, output, max_frames=3, max_dimension=48)

    assert len(generated) >= 4
    for asset in generated:
        assert asset.output_path == output / asset.role / f"{asset.action}.mp4"
        info = VideoAPI().get_video_info(str(asset.output_path))
        assert info["success"] is True
        assert info["frame_count"] == 3
        assert max(info["width"], info["height"]) <= 48
