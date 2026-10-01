# Design

## Context

See [proposal.md](proposal.md). PyWebView calls the `closing` event handler synchronously from Cocoa's main thread. `window.evaluate_js()` posts work to that thread and waits for its result. The current handler calls it before returning, causing a deadlock. The frontend already handles `seedream-close-requested` and offers continue or confirmed exit. Seedream already persists a remote response before downloading and reclassifies interrupted attempts on startup.

A second, independent hang surfaces after the first fix: pywebview 6.1 runs every JS-bridge call on a non-daemon thread and delivers the return value through `evaluate_js`, which blocks until the Cocoa main thread evaluates it. A bridge call in flight when the window closes — the confirm-exit call that destroys the window, or a frontend poll racing the close — is queued via `AppHelper.callAfter` but never serviced once `app.stop_` ends the run loop, so that thread waits forever and `Py_FinalizeEx` hangs joining it. The restart path never finalizes (`os.execv`), which is why only plain close hangs.

## Goals / Non-Goals

**Goals:** Keep the native close callback short; deliver the existing warning after the callback yields; preserve normal and confirmed close paths and current recovery semantics; let the process actually exit after a confirmed close.

**Non-Goals:** Change provider request type, create an image task lookup API, resubmit unknown attempts, or alter persisted batch format.

## Decisions

### Defer JavaScript evaluation to a daemon worker

The active-attempt check and close cancellation remain in `on_window_closing`. The handler starts a short daemon worker to call `evaluate_js` and returns `False` immediately. PyWebView can then service the queued JavaScript evaluation on the Cocoa main thread. The worker captures the window and count at close time and handles evaluation errors without blocking native closure.

An alternative is a Cocoa-specific `callAfter`, but it would introduce a platform-specific dispatch path in application code. A daemon worker uses the existing cross-platform PyWebView API and avoids a new dependency.

### Keep exit confirmation and recovery unchanged

The existing `seedream_confirm_exit` bridge remains the only path to force closure while image attempts are active. Image recovery stays tied to whether the Ark response was persisted before exit; there is no safe way to infer an unsaved synchronous response or silently retry a paid request.

### Exit without interpreter finalization after cleanup

Once `webview.start()` returns, `run()` waits (bounded) for the closed-event cleanup signal, honors a pending in-place restart only after successful cleanup, flushes stdio, and ends the process without interpreter finalization. The closed-event handler attempts every shutdown step independently, records failures, and signals when those attempts finish. A completed cleanup exits with status 0; a failed or timed-out cleanup logs the reason, skips restart, and exits with status 1. The timeout remains an emergency escape from a cleanup hang and cannot guarantee that a still-running step has finished. Skipping finalization avoids joining a bridge thread blocked in a never-serviced `evaluate_js`.

An alternative is making pywebview's bridge threads daemon or adding a timeout to `evaluate_js`, but both require patching the dependency and the timeout would still leak a blocked thread per call. Hard exit after completed cleanup is deterministic and confined to our own entrypoint.

### Reuse the single-image retry API for batch recovery

The batch detail view derives eligible attempts from `download_failed` and `!url_expired`. When at least two are eligible, it replaces their individual buttons with one batch button. Its click handler retries the captured indices sequentially through the existing `seedream_retry_download` bridge, allowing later images to proceed if one fails, then reloads the local batch state. The view keeps the batch button visible and disabled while it runs; when only one eligible image remains, the existing individual button appears. This keeps the backend validation authoritative, avoids concurrent writes to one batch record, and does not add a paid endpoint or persistence format.

## Risks / Trade-offs

- A warning dispatch may race with a second close click or window destruction → The frontend dialog is already idempotent; evaluation errors are contained in the worker.
- The warning may not appear if the WebView is itself unavailable → The close attempt is cancelled, and a later close can retry delivery.
- A process crash before an image response is saved remains unrecoverable through this synchronous API → Keep the existing unknown status and explicit user choice to exit.
- Hard exit skips atexit handlers and finalizers → Each shutdown step is attempted before a successful exit. A failed or timed-out cleanup is reported as an abnormal exit; the timeout may still interrupt a step that has not finished.
- A batch can contain a mix of successful, failed, expired, and unknown attempts → Select only retryable failed downloads and preserve each attempt's own status and error.

## Migration Plan

No data migration is required. The change can be rolled back by restoring the previous handler, though that would restore the close deadlock.
