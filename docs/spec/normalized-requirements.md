# Product Requirements

## 1. Overview
- The system is a web-based microscopy logbook and acquisition management platform.
- It stores SEM protocols, samples, images, videos, optical images, navigation images, and attachments.
- It receives acquisition files from a desktop agent, processes them on the server, and presents them in a structured protocol workspace.
- It replaces the legacy external logbook workflow with a native application that supports search, annotation, access control, rendering, and auditability.
- Its purpose is to centralize experiment records, automate ingestion and image processing, and let authorized users review and correct protocol content after acquisition.

## 2. Users
- `SYSTEM_ADMIN`: manages system-wide access, can view and administer all protocols, and can override normal visibility restrictions.
- `UNIT_MANAGER`: manages protocols and access within their unit, including restricted sharing and cross-protocol reassignment inside authorized scope.
- `OPERATOR`: creates and edits protocols they own, reviews incoming acquisition content, and performs allowed post-ingestion corrections.
- `READER`: can view protocols they are authorized to access but cannot create, edit, or reassign content.
- `Agent`: authenticated machine client that uploads files and closes acquisition sessions for one protocol only.

## 3. Core Workflows

### WF-001: Create New Experiment
Description:
Create a new protocol and prepare the agent configuration for acquisition.
Steps:
1. An authorized user requests the next protocol number.
2. The user creates a protocol with microscope type, project information, operator, and visibility settings.
3. If visibility is restricted, the user provides the allowed user list.
4. The system creates the protocol with acquisition status set to ongoing.
5. The user downloads the agent configuration for the acquisition workstation.
Expected outcome:
The protocol exists, has a unique protocol number, is ready to receive files, and the agent can start uploading content.

### WF-002: Agent-Driven File Ingestion
Description:
Ingest a file sent by the acquisition agent and process it through the server pipeline.
Steps:
1. The agent uploads a file with protocol identifier, sample path, filename, and file content.
2. The server stores the raw file and classifies the element type.
3. For microscope images, the server detects the microscope picture type and extracts metadata.
4. The server moves the file to its final storage location and generates derivatives.
5. The server applies calibration and databar removal when configured for that image type.
6. The server creates missing sample nodes from the provided sample path.
7. The system refreshes protocol content and notifies connected clients.
Expected outcome:
The uploaded file is stored, linked to the correct protocol and sample hierarchy, processed asynchronously, and visible in the workspace when permitted.

### WF-003: Review Protocol Content
Description:
Browse protocol structure, inspect processed content, and read metadata.
Steps:
1. A user opens the protocol dashboard and selects a visible protocol.
2. The workspace loads the protocol tree, content area, and edit panel.
3. The user selects an item from the protocol or sample tree.
4. The system displays the correct viewer or preview for the selected item.
5. The system shows processing state, acquisition state, and metadata when available.
Expected outcome:
The user can inspect protocol content without uploading files manually or leaving the application.

### WF-004: Update Protocol and Item Annotations
Description:
Edit descriptive fields on a protocol or its elements.
Steps:
1. An authorized user edits introduction, conclusion, caption, description, or extra information.
2. The system saves the change.
3. The system invalidates the rendered HTML cache for the affected protocol.
4. The system re-renders protocol HTML according to debounce rules.
Expected outcome:
Updated annotations persist and appear in subsequent protocol views and rendered exports.

### WF-005: Correct Sample Assignment After Ingestion
Description:
Move an already ingested item or sample subtree to the correct location without re-uploading the file.
Steps:
1. An authorized user selects a reassignment action in the workspace.
2. The user chooses the target sample or protocol, or submits a rename or removal action.
3. The server validates permissions and protocol edit state.
4. The server updates storage references and database records atomically.
5. The system preserves existing custom fields and records the action in the audit log.
Expected outcome:
The selected content appears in its corrected logical location and the system retains traceability of the change.

### WF-006: Manage Visibility and Sensitive Content
Description:
Control who can view a protocol or a sample subtree.
Steps:
1. An authorized user changes protocol visibility or applies sample-level restriction.
2. If restricted access is selected, the user specifies explicit allowed users.
3. The system updates visibility rules and applies them to API responses.
4. Unauthorized users no longer see restricted content in listings, details, or thumbnails.
Expected outcome:
Access to protocol and sample content follows unit membership and explicit sharing rules without metadata leakage.

### WF-007: Complete Acquisition Session
Description:
Mark acquisition as finished either explicitly or automatically.
Steps:
1. The agent sends a session close request, or the system detects prolonged inactivity.
2. The system updates the protocol acquisition status.
3. Connected clients receive the updated acquisition state.
Expected outcome:
The protocol reflects whether acquisition is still active independently of edit lock status.

### WF-008: Use Standalone Lab Tools
Description:
Run utility operations on individual files outside a protocol.
Steps:
1. An authenticated user uploads a file to a lab tool endpoint.
2. The system performs the requested metadata, calibration, crop, or conversion operation.
3. The system returns the result without creating protocol records.
Expected outcome:
Users can inspect or transform files on demand without persisting them in the main logbook.

---

## 4. Functional Requirements

### FR-001: Protocol Creation and Numbering
Description:
The system shall create a protocol record with an application-managed unique protocol number.
User story:
As an operator, I want the system to create a new protocol with a reserved number so that I can start an experiment without conflicting identifiers.
Acceptance criteria:
- The system provides the next available protocol number before protocol creation.
- Creating a protocol stores microscope type, owner, unit, visibility, and core metadata.
- A created protocol starts with acquisition status set to `ONGOING`.
- Only authorized roles can create a protocol.

### FR-002: Agent Configuration Download
Description:
The system shall provide a protocol-specific agent configuration after protocol creation.
User story:
As an operator, I want to download agent settings for a protocol so that the acquisition workstation can upload files to the correct destination.
Acceptance criteria:
- The system returns a protocol-specific configuration document for the agent.
- The configuration includes the protocol context required for uploads.
- The agent configuration is retrievable only by authorized users.

### FR-003: Agent-Only File Ingestion
Description:
The system shall accept acquisition files only through the agent ingestion API.
User story:
As a product owner, I want all ingestion to follow one server-controlled pipeline so that file handling is consistent and auditable.
Acceptance criteria:
- The ingestion endpoint requires protocol identifier, sample path, filename, and file content.
- The ingestion endpoint rejects requests that do not include `sample_path`.
- Browser users cannot upload protocol files through a manual file upload workflow.
- Ingestion requests from agent tokens are accepted only for the protocol bound to the token.

### FR-004: Unified Asynchronous Processing Pipeline
Description:
The system shall process ingested files through one asynchronous pipeline that classifies, extracts, stores, and renders content.
User story:
As an operator, I want uploaded files to be processed automatically so that I do not need to trigger separate back-office actions.
Acceptance criteria:
- The ingestion API returns immediately with asynchronous task tracking information.
- The pipeline determines the element type before protocol-specific processing.
- For microscope images, image type detection runs server-side without a separate client request.
- The pipeline creates missing sample parents from the provided sample path.
- The pipeline triggers protocol HTML re-rendering according to debounce rules.

### FR-005: Microscope Image Type Detection
Description:
The system shall detect microscope image subtype on the server using a fixed evaluation order.
User story:
As a system maintainer, I want deterministic image classification so that downstream metadata extraction and calibration use the correct logic.
Acceptance criteria:
- The server evaluates picture type detectors in a defined priority order.
- The generic detector is used only when no more specific detector matches.
- The detected picture type is stored with the microscope picture record.
- No client-provided picture type overrides server detection.

### FR-006: Metadata Extraction
Description:
The system shall extract and persist instrument metadata for supported microscope image types.
User story:
As a reader, I want image metadata stored with each image so that I can review acquisition parameters later.
Acceptance criteria:
- The system stores extracted microscope metadata in the image parameter set.
- FEI images include computed magnification based on extracted values.
- VEGA JPEG images without required sidecar metadata are marked as missing metadata.
- VEGA JPEG images can be reprocessed when the sidecar metadata becomes available.
- XL40 multi-frame metadata includes frame count when applicable.

### FR-007: Derivative Generation
Description:
The system shall generate and persist image derivatives as typed records.
User story:
As a reader, I want viewable derivatives so that I can inspect large microscope images efficiently.
Acceptance criteria:
- The system creates a thumbnail derivative for supported microscope images.
- The system creates a full-size PNG derivative for supported microscope images.
- The system creates DZI derivatives for images above the configured size threshold.
- XL40 multi-frame images create one frame derivative per frame with a frame index.
- Derivative generation is idempotent when regeneration is not forced.

### FR-008: Per-Image Calibration
Description:
The system shall apply calibration per image based on the detected picture type and matching calibration configuration.
User story:
As an operator, I want calibration to match the actual image source so that mixed-instrument sessions are processed correctly.
Acceptance criteria:
- The system resolves calibration settings using the detected picture type of each image.
- Calibration can be enabled for one image type and skipped for another within the same protocol.
- Supported calibration algorithms write corrected resolution data when needed.
- Generic images skip calibration without failing the ingestion pipeline.
- The system records when calibration has been applied or confirmed as already correct.

### FR-009: FEI Databar Removal
Description:
The system shall create cropped derivatives for supported FEI-family images when databar removal is enabled.
User story:
As a reader, I want a cropped viewing option so that I can review FEI images without the databar overlay.
Acceptance criteria:
- Databar removal runs only when enabled in the applicable calibration configuration.
- The system stores the cropped output as a separate derivative.
- The original uploaded file remains unchanged.
- The workspace can expose both original and cropped versions when both exist.

### FR-010: Protocol Retrieval, Search, and Rendering
Description:
The system shall support protocol retrieval, list search, and HTML rendering.
User story:
As a user, I want to search and open protocols quickly so that I can find and review past experiments.
Acceptance criteria:
- The system provides a protocol detail response with nested protocol data.
- The system provides a paginated protocol list with search and filter support.
- Search covers the fields defined for protocol lookup in the source specification.
- The system stores rendered protocol HTML and reuses cached output when still valid.
- Any protocol mutation invalidates the HTML cache.

### FR-011: Protocol and Item Annotation
Description:
The system shall allow authorized users to update editable descriptive fields on protocols and content items.
User story:
As an operator, I want to annotate protocol content so that the record is understandable to later reviewers.
Acceptance criteria:
- Authorized users can update protocol introduction and conclusion.
- Authorized users can update caption, description, and extra information on supported items.
- Saving annotation changes updates persistent data.
- Annotation changes invalidate the protocol HTML cache.

### FR-012: Acquisition State Management
Description:
The system shall track acquisition progress independently from protocol edit lock state.
User story:
As an operator, I want the system to distinguish active acquisition from edit permissions so that session state stays accurate.
Acceptance criteria:
- Protocol edit status and acquisition status are stored as separate fields.
- The agent can mark a session complete through a dedicated endpoint.
- The system can mark acquisition complete after a configured idle timeout.
- A locked protocol may still remain in ongoing acquisition state until completion conditions are met.

### FR-013: Post-Ingestion Reassignment
Description:
The system shall support logical reassignment, rename, soft deletion, and subtree moves for already ingested content.
User story:
As an operator, I want to correct organizational mistakes after ingestion so that the protocol structure matches the real experiment.
Acceptance criteria:
- Authorized users can move an image to another sample.
- Authorized users with elevated permission can move an image to another protocol.
- Authorized users can rename an image without requiring a new upload.
- Removing an image performs a soft delete with retention before purge.
- Moving a sample subtree updates descendant paths.
- Reassignment preserves caption, description, and extra information.
- Reassignment updates database state and storage state atomically.
- Reassignment is blocked when the protocol is locked.

### FR-014: Access Control and Visibility Enforcement
Description:
The system shall enforce role-based and visibility-based access to protocols and samples.
User story:
As a unit manager, I want protocol visibility enforced at query time so that unauthorized users cannot infer sensitive content.
Acceptance criteria:
- Protocol visibility supports `PUBLIC`, `UNIT`, and `RESTRICTED`.
- Restricted protocols are absent from search results for unauthorized users.
- Unauthorized users cannot access restricted protocol details, thumbnails, or metadata through any API.
- Sample-level restriction hides the sample content from unauthorized viewers while keeping the protocol visible when allowed.
- Agent tokens cannot call user reassignment operations.

### FR-015: Audit Logging
Description:
The system shall record security-sensitive access and reassignment events.
User story:
As an administrator, I want audit records for restricted access and content moves so that I can investigate who accessed or changed sensitive data.
Acceptance criteria:
- Access to restricted resources is written to the audit log.
- Reassignment events record previous and new logical locations.
- Audit entries include the acting user and request context needed for traceability.

### FR-016: Real-Time Workspace Updates
Description:
The system shall notify connected clients about ingestion and processing progress.
User story:
As a reader, I want the workspace to update as files are processed so that I can monitor acquisition without refreshing manually.
Acceptance criteria:
- The system publishes protocol-level real-time events for new content and status changes.
- Clients receive processing progress updates for asynchronous tasks.
- Clients receive acquisition status changes when sessions close or time out.

### FR-017: Agent File Stability and Offline Buffering
Description:
The agent shall wait for file stability before upload and queue uploads locally when the server is unavailable.
User story:
As an operator, I want the agent to avoid partial uploads and survive temporary outages so that acquisition data is not lost.
Acceptance criteria:
- The agent delays upload until file size remains unchanged for the configured stability window.
- The stability check applies to TIFF uploads.
- VEGA JPEG uploads wait for the matching sidecar metadata file before submission.
- If the server is unavailable, the agent stores pending uploads in a local queue.
- Buffered uploads are replayed in order after connectivity returns.

### FR-018: Standalone Lab Tools
Description:
The system shall expose authenticated utility endpoints for metadata inspection and file transformation outside protocol workflows.
User story:
As a user, I want to run one-off metadata and conversion tools so that I can inspect or transform files without creating a protocol.
Acceptance criteria:
- The system provides a metadata extraction tool endpoint.
- The system provides standalone FEI calibration and databar crop endpoints.
- The system provides a file conversion endpoint with format or resize options.
- Lab tool operations do not create protocol records or persist uploaded files as protocol content.

---

## 5. Business Rules

BR-001: The application is the system of record for protocol logbook entries and does not depend on an external logbook service.
BR-002: File ingestion is agent-driven only. Manual browser upload of protocol content is not included.
BR-003: `sample_path` is mandatory for every ingestion request and is the source of truth for sample hierarchy creation.
BR-004: The server creates missing parent samples automatically from the submitted sample path.
BR-005: Protocol edit status and acquisition status are independent states.
BR-006: A locked protocol cannot be edited or used for reassignment operations.
BR-007: Image type detection is performed on the server and cannot be bypassed by the client.
BR-008: Calibration settings are resolved per image using detected picture type, not by a single global session flag.
BR-009: FEI databar removal creates a new derivative and must not overwrite the original file.
BR-010: Reassignment must preserve user-entered custom fields.
BR-011: Reassignment must update storage and database state atomically.
BR-012: Restricted protocols must be fully invisible to unauthorized users, including list entries, thumbnails, and metadata.
BR-013: Sample-level restriction hides the sample subtree content from unauthorized users while leaving the parent protocol visible when otherwise permitted.
BR-014: Agent tokens are limited to ingestion and session close operations for one protocol.
BR-015: Object access is provided through time-limited signed URLs.
BR-016: Soft-deleted images remain recoverable until the retention period expires.
BR-017: HTML rendering is cached and invalidated by protocol mutations.
BR-018: During active ingestion, protocol HTML rendering is debounced and must not run more frequently than the configured interval.

## 6. Data Model (Conceptual)

Entity: Protocol
Fields:
- id
- protocol_number
- project
- responsible
- microscope_type
- introduction
- conclusion
- status
- acquisition_status
- visibility
- owner_id
- unit_id
- allowed_users
- yaml_customization
- html_cache
- html_rendered_at
- created_at
- updated_at

Entity: Sample
Fields:
- id
- protocol_id
- full_name
- last_name
- parent_id
- description
- sample_visibility
- sample_allowed_users

Entity: MicroscopePicture
Fields:
- id
- storage_key
- original_filename
- sample_path
- picture_type
- params
- caption
- description
- extra_info
- has_metadata
- calibration_config
- processing_status
- created_at
- updated_at

Entity: ImageDerivative
Fields:
- id
- picture_id
- derivative_type
- storage_key
- url
- frame_index
- created_at

Entity: Attachment
Fields:
- id
- protocol_id
- sample_id
- storage_key
- original_filename
- file_size
- attachment_type
- caption
- description
- extra_info

Entity: OpticalImage
Fields:
- id
- protocol_id
- sample_id
- storage_key
- original_filename
- optical_image_type
- caption
- description
- extra_info

Entity: NavigationImage
Fields:
- id
- protocol_id
- storage_key
- original_filename
- caption
- description
- extra_info

Entity: Video
Fields:
- id
- protocol_id
- sample_id
- storage_key
- original_filename
- caption
- description
- extra_info

Entity: ExperimentConfiguration
Fields:
- id
- protocol_id
- microscope_type
- watch_folder
- remote_storage_bucket
- mirroring_enabled
- thumbnail_max_width
- operator
- idle_timeout_minutes

Entity: CalibrationConfig
Fields:
- picture_type
- auto_calibration
- databar_removal
- calibration_algorithm

Entity: User
Fields:
- id
- primary_unit_id
- role
- allowed_units
- authentication_source

Entity: Unit
Fields:
- id
- name
- manager_ids

Entity: AuditLog
Fields:
- id
- user_id
- protocol_id
- sample_id
- action
- endpoint
- ip_address
- old_value
- new_value
- created_at

## 7. Non-Functional Requirements

- Performance: The system must generate a thumbnail for a 50 MB TIFF within 30 seconds.
- Performance: The protocol list API must respond within 200 ms at p95.
- Performance: The system must generate DZI tiles for a 500 MB TIFF within 5 minutes.
- Security: Restricted protocol thumbnails, metadata, and list entries must never be exposed to unauthorized users.
- Security: Object URLs must be signed and expire after 15 minutes.
- Security: All access to restricted resources must be audit logged.
- Security: Agent tokens must be scoped per protocol and limited to ingestion and session close endpoints.
- Usability: Primary user flows must meet WCAG 2.1 AA accessibility requirements.
- Usability: The system must support Chrome 110+, Firefox 110+, and Safari 16+.
- Scalability: Image processing workers must scale horizontally and support at least a four-worker baseline.
- Scalability: The system must support TIFF files up to 2 GB, including multi-frame XL40 files.
- Scalability: Server downtime must not block acquisition because the agent must queue uploads locally and replay them later.
- Reliability: Calibration must not overwrite the original file unless an explicit future rule permits it.
- Reliability: Reassignment must succeed as one atomic operation across database and object storage, or roll back completely.

## 8. Out of Scope

- Manual browser upload of protocol files.
- Direct filesystem operations on the acquisition workstation during reassignment.
- Dependence on an external ELOG service.
- Physical renaming or reorganization of files on the acquisition PC after ingestion.
- Persistent storage of standalone lab tool uploads as protocol content.
- UI-specific layout implementation details beyond the behaviors explicitly stated in the source specification.

## 9. Open Questions

- The source flows reference a `customer` field in creation and search, but the domain model section does not define it. Should `customer` be part of the protocol entity?
- The default idle timeout is documented as 120 minutes. Should this value be configurable per protocol, per microscope type, or globally only?
- The required stability window for large XL40 multi-frame TIFF files is not confirmed. What maximum write duration should the agent support before upload?
- The maximum acceptable delay between a VEGA JPEG file and its `.hdr` sidecar is not defined. What pairing timeout should the agent use?
- The specification mentions multi-user editing concerns but does not confirm whether real-time concurrent annotation is required. Is optimistic locking sufficient?
- The unit model is described as flat. Is hierarchical unit inheritance required for permissions?
- Multi protocols allow mixed image sources. Must calibration settings be explicitly defined for every expected instrument type, or can defaults be inherited?
- The protocol patch endpoint includes acquisition status updates. Which roles are allowed to set acquisition complete manually, and can they reopen a completed session?
- Sample tree context actions mention sample locking and audit log viewing, but the data model and rules do not define sample lock behavior. Is sample-level locking required?
- The delete operation is described as a soft delete with 30-day retention. Is restoration within that retention window required as a user-facing feature?
