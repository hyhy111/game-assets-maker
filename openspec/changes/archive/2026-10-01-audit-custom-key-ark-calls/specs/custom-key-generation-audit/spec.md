# Spec Delta

## Purpose

Provides durable, privacy-bounded evidence of custom-key Ark image and video API calls so users can investigate interrupted generations and distinguish observed responses from unresolved remote outcomes.

## ADDED Requirements

### Requirement: Custom-key Ark calls have correlated lifecycle records
The application SHALL maintain a local audit record for each custom-key Ark image generation call and video create, query, list, and delete call. Each call SHALL have one correlation ID and events for intent before transport, receipt or failure, and the resulting local handling stage when applicable. An image call SHALL identify its local batch and attempt; a video call SHALL identify its local task when one exists.

#### Scenario: Image generation completes and downloads
- **WHEN** a custom-key image generation call returns a usable response and the image downloads
- **THEN** the audit record identifies the image attempt and contains the call start time, response time, elapsed time, response status, provider request ID when supplied, image usage, URL presence, and local save/download outcome

#### Scenario: Video task is created and polled
- **WHEN** a custom-key video create call returns a remote task ID and later query calls update the task
- **THEN** the audit events correlate those calls with the local and remote task IDs and record each call's elapsed time and observed remote status

#### Scenario: Connection check or cancellation call
- **WHEN** the client calls the custom-key Ark list or delete endpoint
- **THEN** the call's method, endpoint kind, timing, HTTP result or failure, and available correlation IDs are recorded

### Requirement: Audit records survive interruption without overstating remote outcome
Before a paid custom-key generation POST starts, the application SHALL durably record its intent. It SHALL distinguish transport failure, HTTP error, malformed response, parsed success, persistence success, and download outcome. On startup it SHALL identify calls with no observed terminal event as interrupted or unresolved without asserting that Ark accepted or billed them.

#### Scenario: Client exits while image POST is pending
- **WHEN** a paid image call has a durable intent event but no recorded response after the client exits
- **THEN** the audit trail retains the attempted call and marks its outcome unresolved after restart, without inventing an image URL or billing result

#### Scenario: Response received before download fails
- **WHEN** a provider response is observed but local media download fails
- **THEN** the audit trail distinguishes the successful generation response from the failed download and indicates whether the response was persisted for recovery

#### Scenario: Audit storage fails before paid submission
- **WHEN** the durable intent event cannot be written before a paid image or video POST
- **THEN** the application does not send that paid POST and reports a local logging error to the caller

### Requirement: Audit data is bounded and excludes secrets and media
Audit records SHALL contain only allowlisted diagnostic fields and SHALL exclude API keys, authorization headers, raw prompts, reference or frame bytes, raw provider response bodies, signed media URLs, and raw provider error messages. Audit files SHALL reside in update-safe application data storage, honor configured data-root overrides, and have bounded size and retention independent of the optional error logger.

#### Scenario: Request contains a prompt or image input
- **WHEN** a custom-key generation request contains text or encoded image data
- **THEN** the log records permitted metadata such as model, dimensions/options, prompt length or digest, and input count without recording the text or bytes

#### Scenario: Provider returns a media URL or error
- **WHEN** Ark returns a signed media URL or an error response
- **THEN** the log records URL presence and safe status/error codes without writing the URL, response body, or unfiltered error message

#### Scenario: Installed application is updated
- **WHEN** the app package is replaced or the configured data root is used
- **THEN** existing audit files remain under the writable application data location rather than the package or repository source tree

### Requirement: Account-based generation is separate
The custom-key audit SHALL be attached only to the local Ark client path that uses the user's custom key. It SHALL NOT log or change the logged-in account/credits generation path.

#### Scenario: Logged-in account generation
- **WHEN** generation uses the account-backed service rather than a custom Ark key
- **THEN** no custom-key Ark audit event is created for that request
