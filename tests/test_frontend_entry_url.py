"""Keep packaged frontend upgrades separate from a persistent WebView cache."""

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
    assert parse_qs(query) == {"v": [version]}


def test_development_frontend_keeps_vite_url():
    from backend.main import MainApp

    app = MainApp.__new__(MainApp)
    app.is_dev = True
    assert app.get_url() == "http://localhost:5173"
