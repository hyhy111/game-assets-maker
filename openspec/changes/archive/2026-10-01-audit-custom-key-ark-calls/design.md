# Design

## Context

See [proposal.md](proposal.md). Seedream creates one synchronous Ark POST per image attempt, stores the returned JSON in `batch.json`, then downloads its URL. An interrupted attempt without that stored JSON becomes `unknown`. Seedance creates a remote task with one POST, persists the task ID, then polls with GET; it also uses list for a key check and DELETE for cancellation. Both use local Python Ark clients. The current `SafeLogger` is disabled by default, writes only ERROR-level records, and does not capture HTTP lifecycles. The development-only frontend request panel is unrelated to durable production diagnostics. Confirmed window close can end with `os._exit`, so ordinary buffered logger shutdown is insufficient.

## Goals / Non-Goals

**Goals:** Make each custom-key Ark call reconstructable from safe, durable, timestamped events; correlate those events with local image attempts and video tasks; retain enough HTTP and provider metadata to compare with Ark usage records; preserve update-safe storage and avoid leaking credentials or media.

**Non-Goals:** Infer billing from a missing response, recover an image whose synchronous response was never received, record full prompts or signed URLs in the audit file, change the account-backed generation transport, or change the number of paid calls.

## Decisions

### Dedicated append-only JSONL audit

Write versioned JSON Lines in `data_root()/logs/ark-custom-key.jsonl`, independent of `logger_enabled`. Each event has UTC wall-clock time, monotonic elapsed time where meaningful, a per-call UUID, operation (`image.create`, `video.create`, `video.get`, `video.list`, `video.delete`), local batch/attempt or task ID, phase, and an allowlisted metadata object. A process-local lock serializes concurrent image threads and the video worker. Rotate by file size with a bounded number of archives and an age limit; use a restrictive file mode where supported. Do not reuse `SafeLogger`: it can be disabled and currently formats exception strings and tracebacks that may contain sensitive request data.

Before each paid POST, append `intent` and call `fsync` before entering the transport. If the write fails, return a distinct local audit-storage error and do not send the POST. This makes the absence of any pre-call record meaningful for calls made after the feature is enabled. For non-paid GET/list/DELETE, a logging failure is surfaced diagnostically but does not prevent recovery polling or cancellation. Subsequent events are appended promptly; a response event is written as soon as the HTTP response body has been read, before parsing and before manager-level persistence. `os._exit` requires writes to be complete before the event is considered recorded.

Alternative: use the existing error logger or one summary at task completion. Both miss requests interrupted before completion; the error logger is optional and may serialize unsafe exception text.

### Separate HTTP evidence from local state transitions

Instrument the two Ark clients at the HTTP boundary to emit `intent`, `http_response`, `parsed_response`, and `failure` events with sanitized fields. The clients can observe method, operation, status, duration, safe provider request ID headers/body fields, parse failures, and error codes. Add correlation context from the image/video managers so client events point to the existing local IDs. The managers emit `response_persisted`, `download_started`, `download_succeeded` or `download_failed`, plus video task persistence and recovery events. A startup reconciliation pass records `interrupted_unresolved` for unmatched paid intents and links to the existing recovered `unknown`/`submission_unknown` states; it never makes an Ark request or treats an intent as proof of receipt.

The event vocabulary must preserve distinctions: `intent` proves only that the client was about to attempt transport; `http_response` proves bytes came back; `parsed_response` proves a usable provider payload; `response_persisted` proves the existing task/batch record has the recovery data. A timeout or process exit between events remains an unresolved remote outcome. Provider-side billing can be established only from provider usage/billing data.

Alternative: log only manager method entry/exit. It cannot record HTTP status or a response that arrived just before local persistence failed.

### Strict allowlists instead of generic redaction

Request metadata includes model ID, resolution/ratio/duration, input-image count, prompt length and SHA-256 digest, and flags such as watermark; it never includes prompt text, local image paths, data URLs, or request JSON. Image response metadata includes `created`, `usage.generated_images`, token counts, data item count, URL-present flags, and provider request ID if present. Video response metadata includes remote task ID, status, safe timestamps, and output-URL-present flags. Errors include HTTP status, allowlisted provider error code or exception class/errno; do not log raw message strings. Extract request IDs only from known header/body fields, never dump all headers. Audit tests inspect log bytes with sentinel keys, prompts, data URLs, and signed URLs.

Existing `batch.json` and video task records retain their current full response/recovery behavior; the audit log carries metadata and correlation, not a second copy of an expiring URL. The custom-key path is selected at the local Ark client composition boundary. The account/credits HTTP stack remains untouched.

Alternative: serialize full request/response and scrub later. A missed nested field or provider-added field could expose a key, private prompt, image data, or signed URL.

## Risks / Trade-offs

- A durable write adds small latency to paid POSTs → fsync only the pre-POST intent and keep each event compact; measure under focused validation.
- A full or unwritable log directory blocks new paid submissions → report an explicit local error before network transport so a paid call is never silently unaudited; existing video polling and cancellation remain available.
- The process can die between observing a provider response and appending its event → the audit narrows but cannot eliminate this tiny uncertainty; never label unmatched intents as billed.
- Frequent video polls can grow the file → bounded rotation and retention, with every call still represented.
- Provider IDs and usage fields may be absent or change → optional fields remain absent; do not substitute guesses or raw bodies.
- A SHA-256 prompt digest can support correlation but also facilitate guessing short prompts → the digest is kept only in local restricted files and can be omitted if that privacy trade-off is unacceptable; no prompt text is logged.

## Migration Plan

No existing batch or video task data is rewritten. New calls use the audit after the update; old unknown results remain untraceable from this new log. On rollback, audit files can remain in user data without affecting existing generation and can be removed separately by the user. Document the file location and the fact that the audit is not a billing ledger.
