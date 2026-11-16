"""Keep packaged multiprocessing helpers out of the desktop startup path."""

import multiprocessing
import runpy
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("is_helper", [True, False])
def test_desktop_entry_dispatches_multiprocessing_before_startup(monkeypatch, is_helper):
    calls = []

    def freeze_support():
        calls.append("dispatch")
        if is_helper:
            raise SystemExit(0)

    monkeypatch.setattr(multiprocessing, "freeze_support", freeze_support)
    monkeypatch.setitem(sys.modules, "backend.main", SimpleNamespace(main=lambda: calls.append("desktop")))

    if is_helper:
        with pytest.raises(SystemExit) as result:
            runpy.run_module("backend.__main__", run_name="__main__")
        assert result.value.code == 0
        assert calls == ["dispatch"]
    else:
        runpy.run_module("backend.__main__", run_name="__main__")
        assert calls == ["dispatch", "desktop"]
