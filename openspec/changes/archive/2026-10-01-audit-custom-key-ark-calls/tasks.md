# Tasks

## 1. Durable audit writer

- [x] 1.1 Add a versioned, append-only custom-key Ark JSONL writer under the resolved application data root with thread serialization, restrictive permissions, rotation, and retention; verify the file remains readable across a simulated hard exit and respects `GAM_DATA_ROOT` and installed mode.
- [x] 1.2 Define an allowlisted event schema and safe field extractors for image/video requests, HTTP responses, and failures; verify sample records contain no sentinel API key, prompt text, image bytes, signed URL, or raw provider error message.
- [x] 1.3 Make a durable pre-POST intent write mandatory for paid submissions and surface a distinct local error if it fails; verify an unwritable audit location prevents the transport from being called.

## 2. Image generation lifecycle

- [x] 2.1 Correlate each Seedream attempt with its Ark HTTP call and record intent, response/failure, status, provider request ID when supplied, elapsed time, safe usage, and URL presence; verify one selected image produces one correlated POST timeline.
- [x] 2.2 Record response persistence, download start and outcome, and restart recovery without resubmitting unknown attempts; verify a response saved before download remains distinguishable from an interrupted call with no saved response.
- [x] 2.3 Document image audit field meanings and the log location next to the feature documentation; verify the documented example never treats missing response as confirmed billing.

## 3. Video generation lifecycle

- [x] 3.1 Correlate Seedance create POSTs, task GET polls, list connection checks, and DELETE cancellation calls with local and remote IDs, HTTP result, elapsed time, and safe remote status; verify a task timeline can be reconstructed across create and poll calls.
- [x] 3.2 Record task-ID persistence, successful media availability, download outcome, and `submission_unknown` startup recovery; verify a lost create response is distinguishable from a successful create followed by failed download.
- [x] 3.3 Document video call phases and the account/custom-key boundary; verify account-backed generation produces no custom-key audit record.

## 4. Integration review

- [x] 4.1 Inspect the focused diff for key/URL leakage, duplicate paid submissions, local data-root behavior, and compatibility with the existing mixed worktree; verify `git diff --check` and strict OpenSpec validation succeed.
- [x] 4.2 Exercise one interrupted-call and one completed-call trace using a local mock transport, then inspect their JSONL timelines and confirm no real paid endpoint was called during this verification.
