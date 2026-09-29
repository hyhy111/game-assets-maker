from pathlib import Path

from src.utils.ai_cache_paths import ai_cache_root, ai_pic_cache_root, ai_video_cache_root


def test_ai_cache_paths_share_one_root_and_use_media_specific_subdirectories(tmp_path: Path):
    assert ai_cache_root(None, base_dir=tmp_path) == tmp_path / "cache"
    assert ai_pic_cache_root(None, base_dir=tmp_path) == tmp_path / "cache" / "ai-pic-cache"
    assert ai_video_cache_root(None, base_dir=tmp_path) == tmp_path / "cache" / "ai-video-cache"


def test_configured_ai_cache_directory_is_treated_as_the_shared_root(tmp_path: Path):
    configured = str(tmp_path / "custom-cache")
    assert ai_pic_cache_root(configured) == tmp_path / "custom-cache" / "ai-pic-cache"
    assert ai_video_cache_root(configured) == tmp_path / "custom-cache" / "ai-video-cache"


def test_ai_cache_root_normalizes_equivalent_spellings(tmp_path: Path):
    """Migration change-detection compares paths across both resolver layers."""
    assert ai_cache_root("./cache", base_dir=tmp_path) == tmp_path / "cache"
    assert ai_cache_root("nested/../cache/", base_dir=tmp_path) == tmp_path / "cache"
    assert ai_cache_root(str(tmp_path / "cache"), base_dir=tmp_path) == ai_cache_root("cache", base_dir=tmp_path)
