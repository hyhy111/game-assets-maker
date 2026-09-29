import sys


def test_macos_subscription_window_uses_pywebview_child_window_dispatch(monkeypatch):
    from backend.main import API

    api = API()
    created = []

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(api, "_create_subscription_window", lambda url: created.append(url) or True)

    url = "https://example.com/subscription#token=test"
    assert api.open_subscription_window(url) is True
    assert created == [url]


def test_subscription_window_reports_cancelled_creation(monkeypatch):
    from backend import main

    api = main.API()
    monkeypatch.setattr(main.webview, "create_window", lambda *_args, **_kwargs: None)

    assert api.open_subscription_window("https://example.com/subscription") is False


class _LoadedEvent:
    def __init__(self) -> None:
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _SubscriptionWindow:
    def __init__(self) -> None:
        self.destroyed = 0
        self.scripts = []
        self.events = type("Events", (), {"loaded": _LoadedEvent(), "shown": _LoadedEvent()})()

    def destroy(self) -> None:
        self.destroyed += 1

    def evaluate_js(self, script: str) -> None:
        self.scripts.append(script)


def test_each_subscription_window_closes_itself(monkeypatch):
    from backend import main

    windows = [_SubscriptionWindow(), _SubscriptionWindow()]
    bridges = []

    def create_window(*_args, **kwargs):
        bridges.append(kwargs["js_api"])
        return windows[len(bridges) - 1]

    monkeypatch.setattr(main.webview, "create_window", create_window)
    api = main.API()

    assert api.open_subscription_window("https://example.com/first") is True
    assert api.open_subscription_window("https://example.com/second") is True
    assert bridges[0] is not bridges[1]

    assert bridges[0].close_subscription_window() is True
    assert windows[0].destroyed == 1
    assert windows[1].destroyed == 0


def test_subscription_window_injects_visible_close_button(monkeypatch):
    from backend import main

    window = _SubscriptionWindow()
    monkeypatch.setattr(main.webview, "create_window", lambda *_args, **_kwargs: window)

    assert main.API().open_subscription_window("https://example.com/subscription") is True
    assert len(window.events.loaded.handlers) == 1

    window.events.loaded.handlers[0]()

    assert len(window.scripts) == 1
    assert "gam-subscription-close" in window.scripts[0]
    assert "close_subscription_window" in window.scripts[0]


def test_subscription_window_hides_titlebar_text_when_shown(monkeypatch):
    from backend import main

    window = _SubscriptionWindow()
    monkeypatch.setattr(main.webview, "create_window", lambda *_args, **_kwargs: window)

    scheduled = []
    monkeypatch.setattr(main, "schedule_macos_window_controls", lambda w: scheduled.append(w))

    assert main.API().open_subscription_window("https://example.com/subscription") is True
    assert len(window.events.shown.handlers) == 1

    window.events.shown.handlers[0]()

    assert scheduled == [window]
