# seedream-window-close Specification

## Purpose

Defines safe desktop window closing while Seedream image attempts are active, so users can choose whether to wait or exit without freezing the application or silently resubmitting paid requests.

## Requirements

### Requirement: Active image generation does not freeze window closing
When a user requests window closure while Seedream attempts are active, the application SHALL cancel that close attempt and present the existing close warning without blocking the native window event loop.

#### Scenario: Close during active generation
- **WHEN** a user clicks the window close control while one or more image attempts are active
- **THEN** the window remains responsive and a warning displays the active attempt count

#### Scenario: User continues generation
- **WHEN** the user chooses to continue generation from the warning
- **THEN** the warning closes, the application stays open, and active attempts continue

#### Scenario: User confirms exit
- **WHEN** the user chooses to exit from the warning
- **THEN** the application closes without requiring another close attempt

#### Scenario: Process terminates after close
- **WHEN** the window has been destroyed and closed-event cleanup has completed, whether or not bridge calls were in flight during the close
- **THEN** the process terminates instead of hanging in interpreter finalization, and a pending in-place restart still runs before termination

#### Scenario: A cleanup step fails
- **WHEN** one shutdown step raises an exception after the window closes
- **THEN** the application attempts the remaining shutdown steps, records a failed shutdown, and does not restart in place

#### Scenario: Cleanup exceeds the exit deadline
- **WHEN** closed-event cleanup has not finished within the bounded wait
- **THEN** the application reports a failed shutdown and terminates without restarting in place

#### Scenario: No active image attempts
- **WHEN** the user closes the window while no image attempts are active
- **THEN** the application follows its normal close path without showing the Seedream warning

### Requirement: Interrupted image attempts retain their recovery state
The application SHALL preserve any image response saved before exit for download retry after restart, and SHALL represent attempts without a saved response as unknown without automatically resubmitting a paid generation request.

#### Scenario: Response saved before exit
- **WHEN** the application restarts after an image response was saved but its download did not finish
- **THEN** the attempt remains eligible for download retry from the saved response

#### Scenario: Response not saved before exit
- **WHEN** the application restarts after an image attempt was interrupted before its response was saved
- **THEN** the attempt is marked unknown and no paid generation is automatically submitted

### Requirement: Recover multiple downloaded images with one action
When a batch contains multiple image attempts with saved responses and unexpired download links, the application SHALL offer one action to retry all eligible failed downloads without submitting a new image generation request. The action SHALL exclude expired links and attempts whose responses were not saved, and SHALL leave each attempt's result visible independently.

#### Scenario: Multiple recoverable download failures
- **WHEN** a batch has two or more failed downloads with unexpired saved links
- **THEN** one batch-level retry action is available and individual retry buttons for those attempts are replaced

#### Scenario: Partial recovery
- **WHEN** one image download fails during a batch retry while another succeeds
- **THEN** the other eligible downloads are still attempted and each image keeps its own success or failure state

#### Scenario: Only one recoverable download failure
- **WHEN** a batch has only one failed download with an unexpired saved link
- **THEN** the existing single-image retry action remains available

#### Scenario: Expired and unknown attempts
- **WHEN** a batch contains expired download links or attempts without saved responses
- **THEN** those attempts are not submitted by the batch retry action
