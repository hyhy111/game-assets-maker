# Proposal

## Why

When the desktop client exits during an Ark image request, a locally unknown result has no retained response or download URL. The current error logger is disabled by default and does not record the request lifecycle, so a user cannot distinguish a request that never started from one that started but lost its response; the same diagnostic gap exists for custom-key video calls.

## What Changes

- Add an always-on, bounded local audit log for Ark image and video API calls made with the user's custom key, including a durable pre-call event, response or failure event, elapsed time, and correlation to the local image attempt or video task.
- Record safe request and response metadata: model and non-sensitive options, HTTP status, provider request ID when available, image usage and URL presence, and video remote task ID and status. Record interruption and local persistence/download stages so a missing response can be interpreted accurately.
- Exclude API keys, authorization headers, prompts, reference-image bytes, raw response bodies, signed media URLs, and provider error messages from this log. Keep the log outside the replaceable app package and rotate it.
- Keep the logged-in account/credits generation path outside this feature. The audit log reports observed client and provider events, not a definitive billing verdict for a request whose response was lost.

## Capabilities

### New Capabilities

- `custom-key-generation-audit`: Persistent, privacy-bounded diagnostics for custom-key Ark image and video request lifecycles.

### Modified Capabilities

None.

## Impact

- Backend Ark image/video clients, batch/task managers, and their composition points; a dedicated local audit writer and focused tests.
- App data-path and log-retention behavior in development and installed modes. No provider API, account-generation contract, paid-request count, or user media format change.
