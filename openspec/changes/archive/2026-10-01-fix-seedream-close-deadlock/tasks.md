# Tasks

## 1. Native close handling

- [x] 1.1 Move Seedream warning delivery out of the native closing callback while preserving its `False` return and active-count payload; verify the callback contains no synchronous `evaluate_js` call.
- [x] 1.2 Review the idle and confirmed-exit paths against the existing bridge and UI event contract; verify neither path schedules an unnecessary warning or changes the exit decision.

## 2. Integration review

- [x] 2.1 Validate the OpenSpec change, inspect the focused diff, and run static syntax/style checks on touched code; record that live macOS close and interrupted-download recovery remain for the user's later manual test.

## 3. Batch download recovery

- [x] 3.1 Add one batch-level retry control for two or more unexpired failed downloads in the Seedream detail view, reusing the existing single-image API sequentially; verify eligible selection, busy state, and continued attempts after a failure by inspecting the interaction path.
- [x] 3.2 Add Chinese and English copy for the batch retry action and retain the single-image button when only one attempt is eligible; verify both locale keys and conditional rendering.
- [x] 3.3 Validate the updated OpenSpec artifacts, inspect the focused diff, and run frontend static checks; leave live recovery verification to the user's follow-up test.

Validation note: OpenSpec strict validation, focused ESLint (zero errors), and `git diff --check` passed. Whole-frontend typecheck is blocked by two `SeedanceSettings.vue:710` errors in an unrelated pre-existing worktree edit. The batch retry UI has not been exercised in a live app session.

## 4. Process exit after confirmed close

- [x] 4.1 Diagnose the remaining post-close hang: sample the hung process, identify the non-daemon JS-bridge thread blocked in `evaluate_js` during interpreter finalization, and reproduce it in a minimal pywebview app with frontend polling traffic.
- [x] 4.2 Add a shutdown epilogue to `MainApp.run()` that waits (bounded) for the closed-event cleanup signal, honors a pending in-place restart, and hard-exits via `os._exit(0)`; signal cleanup completion from `on_window_closed` in a `finally` block.
- [x] 4.3 Add focused shutdown tests (cleanup signal on failure, hard exit without restart, restart before exit, bounded wait) and stub `os._exit` in the existing restart harness; verify the full backend suite and ruff pass.
- [x] 4.4 Verify live on macOS: red-button close is cancelled by the warning, then confirmed exit terminates the process cleanly within seconds instead of hanging at `threading._shutdown`.

Validation note (section 4): full backend suite 647 passed / 2 skipped; ruff check and format clean on touched files; live close-then-confirm-exit verified in the dev app. Visual confirmation of the warning dialog via `screencapture` was blocked by screen-recording permission; close cancellation was proven by the process staying alive.

## 5. Shutdown failure follow-up

- [x] 5.1 Attempt all shutdown steps even if one fails, and record the failure before signaling that cleanup attempts have finished.
- [x] 5.2 Skip in-place restart and exit with a failure status when cleanup fails or exceeds the bounded wait; retain successful close and restart behavior.
- [x] 5.3 Review the focused diff, run static checks, and validate the updated OpenSpec change.

Validation note (section 5): frontend typecheck, focused ESLint, Ruff check/format, OpenSpec strict validation, and `git diff --check` passed. Whole-frontend lint still reports one unrelated reserved-name error in `frontend/src/select-repro.ts`. Backend tests and live close were not run in this follow-up.
