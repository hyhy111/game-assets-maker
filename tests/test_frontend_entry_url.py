"""Keep packaged frontend upgrades separate from a persistent WebView cache."""

import hashlib
from urllib.parse import parse_qs

import pytest


@pytest.mark.parametrize("version", ["1.0.1", "1.0.2"])
def test_packaged_frontend_entry_uses_current_version_query(tmp_path, monkeypatch, version):
    from backend import main

    bundle = tmp_path / "Game Assets Maker"
    entry = bundle / "frontend" / "dist" / "index.html"
    entry.parent.mkdir(parents=True)
    entry.write_text("<html></html>")
    monkeypatch.setattr(main.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(main, "app_version", lambda: version)
    app = main.MainApp.__new__(main.MainApp)
    app.is_dev = False

    url = app.get_url()
    path, _, query = url.partition("?")
    assert path == str(entry)
    assert parse_qs(query) == {"v": [version], "ui": [hashlib.sha256(entry.read_bytes()).hexdigest()[:16]]}


def test_development_frontend_keeps_vite_url():
    from backend.main import MainApp

    app = MainApp.__new__(MainApp)
    app.is_dev = True
    assert app.get_url() == "http://localhost:5173"


def test_same_version_rebuild_changes_entry_cache_key_without_changing_storage_path(tmp_path, monkeypatch):
    from backend import main

    entry = tmp_path / "frontend" / "dist" / "index.html"
    entry.parent.mkdir(parents=True)
    monkeypatch.setattr(main.sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(main, "app_version", lambda: "1.0.2")
    app = main.MainApp.__new__(main.MainApp)
    app.is_dev = False
    entry.write_text('<script src="assets/old.js"></script>')
    before = app.get_url()
    assert app.get_url() == before, "Unchanged UI must have a stable cache key"
    entry.write_text('<script src="assets/new.js"></script>')
    after = app.get_url()
    assert after != before
    old_path, _, old_query = before.partition("?")
    new_path, _, new_query = after.partition("?")
    assert old_path == new_path == str(entry)
    assert parse_qs(old_query)["v"] == parse_qs(new_query)["v"] == ["1.0.2"]
    assert parse_qs(old_query)["ui"] != parse_qs(new_query)["ui"]
    assert after != f"{entry}?v=1.0.2", "Older version-only cached HTML must not be reused"


def test_non_frozen_frontend_build_also_gets_content_cache_key(tmp_path, monkeypatch):
    from backend import main

    entry = tmp_path / "frontend" / "dist" / "index.html"
    entry.parent.mkdir(parents=True)
    entry.write_text("<html>local build</html>")
    monkeypatch.delattr(main.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(main, "__file__", str(tmp_path / "backend/main.py"))
    app = main.MainApp.__new__(main.MainApp)
    app.is_dev = False
    path, _, query = app.get_url().partition("?")
    assert path == str(entry)
    assert parse_qs(query)["ui"] == [hashlib.sha256(entry.read_bytes()).hexdigest()[:16]]
