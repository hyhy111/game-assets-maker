"""Exercise role-library scrollbar styling in the macOS desktop renderer."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or importlib.util.find_spec("WebKit") is None,
    reason="Requires the macOS WebKit desktop renderer",
)


def test_role_scrollbar_keeps_custom_width_and_native_scrolling():
    # Use a child process so Cocoa stays on its main thread without affecting other tests.
    probe = r'''
import json
import re
import sys
import time
from pathlib import Path

import AppKit
import Foundation
import WebKit

source = Path(sys.argv[1]).read_text(encoding="utf-8")
css = re.search(r"<style scoped>(.*?)</style>", source, re.S).group(1)
html = (
    '<html><head><style>body{margin:0;background:#1b1b1b}'
    '.role-nav{width:240px}.role-nav>div{height:60px;flex-shrink:0}'
    + css + '</style></head><body><nav class="role-nav">'
    + ''.join('<div>Role</div>' for _ in range(20)) + '</nav></body></html>'
)
app = AppKit.NSApplication.sharedApplication()
view = WebKit.WKWebView.alloc().initWithFrame_configuration_(
    ((0, 0), (1280, 800)), WebKit.WKWebViewConfiguration.new()
)
window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    ((0, 0), (1280, 800)), AppKit.NSWindowStyleMaskBorderless,
    AppKit.NSBackingStoreBuffered, False,
)
window.setContentView_(view)
view.loadHTMLString_baseURL_(html, None)


def wait_until(predicate):
    deadline = time.monotonic() + 15
    while not predicate() and time.monotonic() < deadline:
        Foundation.NSRunLoop.currentRunLoop().runUntilDate_(
            Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.02)
        )
    if not predicate():
        raise TimeoutError("WebKit did not finish the scrollbar fixture")


wait_until(lambda: not view.isLoading())
result = []
view.evaluateJavaScript_completionHandler_(
    """(() => {
        const nav = document.querySelector('.role-nav');
        nav.scrollTop = 80;
        return JSON.stringify({
            gutter: nav.offsetWidth - nav.clientWidth,
            scrollTop: nav.scrollTop,
            overflowing: nav.scrollHeight > nav.clientHeight
        });
    })()""",
    lambda value, error: result.append((value, error)),
)
wait_until(lambda: bool(result))
if result[0][1]:
    raise RuntimeError(str(result[0][1]))
print(result[0][0])
window.setContentView_(None)
'''
    source = Path(__file__).resolve().parents[1] / "frontend/src/views/ProjectManager.vue"
    result = subprocess.run(
        [sys.executable, "-c", probe, str(source)], capture_output=True, text=True, timeout=40, check=True
    )
    metrics = json.loads(result.stdout)
    assert metrics["gutter"] == 6, f"Native WebKit scrollbar overrode the custom 6px style: {metrics}"
    assert metrics["overflowing"] and metrics["scrollTop"] == 80
