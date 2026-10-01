# Proposal

## Why

Closing the macOS window during Seedream generation hangs the application. The native close callback synchronously calls `evaluate_js`, which waits for the same Cocoa main thread to run JavaScript. This blocks both the warning dialog and image download completion. After that fix, a second hang remains at process exit: pywebview runs every JS-bridge call on a non-daemon thread and delivers its result through `evaluate_js`, so a bridge call in flight when the window closes is never serviced once the Cocoa run loop stops, and interpreter finalization joins that thread forever. A user confirmed that saved images can be recovered after restart, but multiple images currently require separate retry clicks.

## What Changes

- Dispatch the existing Seedream close warning only after the native close callback returns.
- Exit the process without interpreter finalization once closed-event cleanup has completed, so an in-flight JS-bridge thread can no longer deadlock shutdown; keep the in-place restart ahead of the hard exit.
- Preserve the current choices: keep the app open and let generation finish, or confirm exit despite the risk of losing an image response that has not been saved.
- Keep interruption recovery unchanged: a saved image response remains eligible for download retry after restart; an unsaved response remains unknown and is never resubmitted automatically.
- Offer one batch-level retry action when multiple images in the same batch have recoverable download failures, so users do not need to click each image separately.

## Capabilities

### New Capabilities

- `seedream-window-close`: Safe window close behavior while image generation is active.

### Modified Capabilities

None.

## Impact

- Backend native window close handler in `backend/main.py`.
- Existing Seedream close-warning UI contract, batch detail view, localizations, and focused close tests.
- No provider API, persistence format, dependency, or paid-request behavior change.
