# Legacy to Requirements Mapping

## Scope
- Source code analyzed from [`/home/luc/Documents/migration-workspace/autologbook`](/home/luc/Documents/migration-workspace/autologbook).
- Requirements source: [`/home/luc/Documents/migration-workspace/docs/spec/normalized-requirements.md`](/home/luc/Documents/migration-workspace/docs/spec/normalized-requirements.md).
- Mapping status values used here:
  - `Supported`: clear legacy implementation exists
  - `Partial`: related behavior exists but differs materially from the target requirement
  - `Not Found`: no clear legacy implementation found
  - `Unclear`: evidence is insufficient

## Architecture Fit Summary
- The legacy system is not a direct implementation of the target web architecture.
- It is closer to a desktop automation tool that watches folders, maintains local protocol state, and posts rendered output to ELOG.
- Some domain logic is reusable, but many requirements in the target specification assume server-side APIs, persistent application data, role-based visibility, and object storage abstractions that do not exist in the legacy codebase.

## Functional Requirement Mapping

| ID | Requirement | Legacy Status | Evidence and Notes |
| --- | --- | --- | --- |
| FR-001 | Protocol Creation and Numbering | Partial | The wizard creates new experiments and derives the next protocol number from the ELOG protocol-list workflow, not from an internal application sequence. See `expwizard/wizard_commit_new_experiment_page.py`. |
| FR-002 | Agent Configuration Download | Partial | The wizard generates an `.exp` configuration file for the desktop app, but there is no protocol-scoped upload agent configuration in the target API sense. |
| FR-003 | Agent-Only File Ingestion | Not Found | Legacy ingestion is local filesystem monitoring via `watchdog`, not API-based upload. There is no server endpoint or scoped ingestion token model. |
| FR-004 | Unified Asynchronous Processing Pipeline | Partial | There is an automated local processing pipeline triggered by filesystem events in `autowatchdog.py`, but it is not server-side and does not expose async task APIs. |
| FR-005 | Microscope Image Type Detection | Supported | Picture subtype handling and factory-based detection exist in `microscope_picture.py`. |
| FR-006 | Metadata Extraction | Supported | FEI, VEGA, VEGA JPEG, and XL40 metadata parsing are present in `microscope_picture.py` and related helpers. |
| FR-007 | Derivative Generation | Partial | Thumbnail and PNG generation exist. DZI tiling and a separate derivative entity model were not found. XL40 multi-frame handling exists, but not as a normalized derivative table. |
| FR-008 | Per-Image Calibration | Partial | Calibration exists for FEI, VEGA, and XL40, but legacy configuration appears to be microscope/global rather than per-image configuration objects resolved by detected type. |
| FR-009 | FEI Databar Removal | Supported | FEI databar crop logic exists and preserves the original by writing cropped output separately. |
| FR-010 | Protocol Retrieval, Search, and Rendering | Partial | Protocol rendering exists through Jinja and ELOG posting. Search exists in the wizard against ELOG. There is no web protocol API or server-side cache model matching the target architecture. |
| FR-011 | Protocol and Item Annotation | Supported | Caption, description, and extra information editing are implemented through the protocol editor and persisted in YAML customization. |
| FR-012 | Acquisition State Management | Partial | Legacy uses ELOG attributes such as `Analysis status` and `Edit Lock`, but the target split between `status` and `acquisition_status` is not present as first-class application state. |
| FR-013 | Post-Ingestion Reassignment | Partial | Rename, move, remove, and restore flows exist in the protocol editor, but they operate on local filesystem paths, not on server-managed logical reassignment with storage-key updates and soft-delete semantics. |
| FR-014 | Access Control and Visibility Enforcement | Not Found | No equivalent application-level role, unit, restricted visibility, or SQL/RLS-backed enforcement model was found. |
| FR-015 | Audit Logging | Not Found | General application logging exists, but no clear audit log model for restricted-resource access or reassignment history was found. |
| FR-016 | Real-Time Workspace Updates | Partial | The desktop UI receives updates via local Qt signals from worker threads. No WebSocket or browser real-time update mechanism exists. |
| FR-017 | Agent File Stability and Offline Buffering | Partial | Filesystem event handling and some retry/stability behavior exist, including VEGA JPEG sidecar logic. No offline upload queue exists because there is no server upload model. |
| FR-018 | Standalone Lab Tools | Supported | `labtools` includes metadata dumping, FEI manipulation, image conversion, event logging, and mirroring utilities. |

## Workflow Mapping

| Workflow | Legacy Status | Notes |
| --- | --- | --- |
| WF-001 Create New Experiment | Partial | Supported through `expwizard`, but built around ELOG posting and `.exp` file generation rather than protocol creation in an application backend. |
| WF-002 Agent-Driven File Ingestion | Partial | Closest legacy equivalent is watchdog-driven local ingestion from a folder, not an agent POST to a server. |
| WF-003 Review Protocol Content | Supported | The main app and protocol editor support browsing protocol trees, previews, and metadata. |
| WF-004 Update Protocol and Item Annotations | Supported | Implemented through YAML-backed customization in the protocol editor. |
| WF-005 Correct Sample Assignment After Ingestion | Partial | Implemented as local file move/rename/remove plus YAML key recycling, not server-side logical reassignment. |
| WF-006 Manage Visibility and Sensitive Content | Not Found | No comparable role/visibility model was identified. |
| WF-007 Complete Acquisition Session | Partial | Legacy updates ELOG analysis status and uses watchdog start/stop behavior, but not the target API and timeout-based acquisition state model. |
| WF-008 Use Standalone Lab Tools | Supported | Present through `labtools`. |

## Gaps: Requirements Present in Spec but Not Found in Legacy
- FR-003: no API-based ingestion endpoint and no agent token scope model
- FR-010: no web protocol retrieval API, no cursor-paginated list API
- FR-012: no clear independent `status` plus `acquisition_status` domain model
- FR-014: no unit/user visibility model matching the target spec
- FR-015: no clear audit log subsystem
- FR-016: no WebSocket-driven browser updates
- large parts of the target non-functional architecture:
  - no database-backed persistence
  - no object storage abstraction
  - no server-side task queue
  - no authentication and authorization service

## Legacy Functionality Not Clearly Represented in the Spec
- direct ELOG posting and editing
- microscopy protocol-list management through ELOG messages
- `.exp` experiment file generation, comparison, and attachment upload
- hard dependency on local/mirrored folder structures
- network-share mirroring as a core workflow
- recycle-bin restore flow in the protocol editor
- experiment recovery by searching ELOG and reconciling local vs remote `.exp` files
- Windows-specific external tool launching

## Candidate Reuse by Requirement Area

### Strong Reuse Candidates
- FR-005, FR-006, FR-008, FR-009:
  - microscope subtype detection
  - metadata parsing
  - calibration logic
  - databar crop logic
- FR-007:
  - thumbnail and PNG generation logic
- FR-011:
  - customization concepts and YAML recycling behavior can inform migration
- FR-018:
  - some labtools algorithms can likely be repurposed as service endpoints

### Reuse With Heavy Refactoring
- FR-001, FR-004, FR-010, FR-013:
  - protocol management and editor behavior are coupled to ELOG, Qt, and filesystem paths
- FR-012:
  - status concepts exist, but in a different shape

### Likely New Implementation Needed
- FR-003
- FR-014
- FR-015
- FR-016
- most of the target access control, persistence, and API surfaces

## Requirement-Level Notes

### FR-001 and FR-002
- Legacy behavior is wizard-centric.
- New experiment creation immediately creates folders and an `.exp` file.
- The target system instead expects backend-owned protocol creation and agent config download.

### FR-003 and FR-004
- Legacy ingestion is tied to a local watcher and direct file access.
- This is the biggest architectural mismatch.

### FR-010 and FR-011
- Rendering and annotation exist, but the storage model is split across local YAML and remote ELOG.
- This suggests conceptual reuse, not structural reuse.

### FR-013
- Legacy rename/move/remove flows are important because they preserve custom metadata through YAML key recycling.
- That behavior should be preserved in migration, but the implementation model must change completely.

## Confidence Notes
- Confidence is high for the absence of a database-backed authorization model.
- Confidence is high for the presence of microscope parsing and local ingestion logic.
- Confidence is medium for some edge-case editor and restore flows because the relevant modules are large and were inspected selectively.
