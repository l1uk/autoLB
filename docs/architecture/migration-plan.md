# Migration Plan

## 1. Strategy
- Use an incremental strangler migration.
- Preserve the legacy desktop application for ongoing operations while the new platform is introduced.
- Migrate in slices that deliver end-to-end business value.
- Extract reusable logic early and keep new code independent from Qt, ELOG, and local filesystem assumptions.

## 2. Migration Principles
- Preserve microscope-specific behavior before optimizing architecture details.
- Prefer coexistence over big-bang replacement.
- Replace path-derived implicit behavior with explicit contracts.
- Move state out of files and into durable backend persistence.
- Build compatibility tests around real legacy sample files.

## 3. Target Transition States

### State A: Legacy Only
- current Qt desktop app
- local watchdog ingestion
- ELOG-backed workflow

### State B: Shared Core + New Backend Foundation
- extracted domain package
- PostgreSQL, object storage, Redis, FastAPI, Celery in place
- no production user traffic yet

### State C: Hybrid Operation
- new backend and agent used for selected protocols
- legacy app remains available for fallback and comparison
- optional ELOG compatibility publishing

### State D: Web Primary
- web UI becomes the main operator interface
- legacy app retained only for edge workflows if still required

### State E: Legacy Retirement
- ELOG dependency removed or reduced to archival export only
- Qt desktop app no longer needed for normal operations

## 4. Migration Phases

### Phase 0: Foundations and Test Corpus
Goals:
- prepare migration safely
- reduce uncertainty around microscope-specific behavior

Deliverables:
- representative fixture set for FEI, VEGA TIFF, VEGA JPEG + sidecar, XL40 single-frame, XL40 multi-frame
- parity test matrix for:
  - subtype detection
  - metadata extraction
  - calibration
  - databar crop
  - derivative generation
- target data model draft
- API contract draft

Exit criteria:
- the team can validate legacy behavior without launching the Qt app

### Phase 1: Extract Shared Domain Core
Goals:
- isolate reusable logic from the legacy monolith

Scope:
- extract from legacy:
  - microscope detection
  - metadata extraction
  - calibration
  - databar crop
  - derivative generation helpers
  - selected rendering helpers
- remove Qt and ELOG dependencies from the extracted package

Deliverables:
- `core` Python package with unit tests
- adapter tests proving parity against legacy outputs

Exit criteria:
- backend workers can call the extracted logic without importing PyQt or ELOG modules

### Phase 2: Backend Platform Skeleton
Goals:
- establish persistent backend infrastructure

Scope:
- provision:
  - PostgreSQL
  - object storage
  - Redis
  - FastAPI
  - Celery
- implement:
  - health endpoints
  - auth skeleton
  - protocol repository layer
  - storage abstraction
  - task dispatch framework

Deliverables:
- deployable backend baseline
- initial schema migrations
- storage key conventions

Exit criteria:
- backend can create protocols and persist them

### Phase 3: First Vertical Slice
Goals:
- deliver the first production-relevant workflow

Scope:
- implement:
  - `FR-001` protocol creation and numbering
  - `FR-002` agent config download
  - `FR-003` ingestion endpoint
  - `FR-004` async processing orchestration
  - `FR-005` subtype detection
  - `FR-006` metadata extraction
  - `FR-007` thumbnail/full-size PNG generation
  - minimal read-only protocol workspace
- build a thin desktop agent for upload and file-stability checks

Deliverables:
- working protocol creation flow
- working agent upload flow
- read-only web workspace for ingested images

Exit criteria:
- a real microscope session can be ingested into the new system without the Qt app

### Phase 4: Workspace Editing and Session State
Goals:
- make the web application operational for daily review work

Scope:
- implement:
  - `FR-010` protocol retrieval/search
  - `FR-011` annotations
  - `FR-012` acquisition state management
  - `FR-016` real-time task and acquisition updates
- add protocol HTML rendering and export

Deliverables:
- operator-ready protocol dashboard and workspace
- live processing status updates

Exit criteria:
- users can review and annotate active sessions in the web UI

### Phase 5: Reassignment and Preservation of Customization
Goals:
- replace the most important protocol-editor correction workflows

Scope:
- implement:
  - `FR-013` reassignment, rename, subtree move, soft delete
- encode YAML-recycling semantics into backend reassignment services
- add audit logging for reassignment actions

Deliverables:
- web-based post-ingestion correction workflows
- annotation preservation during move/rename

Exit criteria:
- the most important protocol-editor correction workflows no longer require the desktop app

### Phase 6: Access Control and Restricted Content
Goals:
- close the biggest gap between legacy and target

Scope:
- implement:
  - `FR-014` access control and visibility
  - `FR-015` audit logging for restricted access
- add users, units, allowed-user grants, and sample-level restrictions

Deliverables:
- production authorization model
- restricted protocol and sample enforcement

Exit criteria:
- sensitive protocols are safely governed in the new platform

### Phase 7: Labtools and Compatibility Retirement
Goals:
- complete feature coverage and remove remaining legacy dependence

Scope:
- implement:
  - `FR-018` labtools endpoints and UI
- decide whether to:
  - retire ELOG completely
  - or keep one-way publishing/export only
- retire unused Qt workflows

Deliverables:
- full platform coverage
- legacy shutdown plan

Exit criteria:
- no normal production workflow depends on the Qt app

## 5. First Slice to Implement

### Scope
- Protocol creation with server-managed numbering
- Agent configuration download
- Desktop upload agent
- Ingestion endpoint
- Async file-processing pipeline
- Microscope subtype detection
- Metadata extraction
- Thumbnail and full-size PNG generation
- Read-only dashboard and protocol workspace

### Included Requirements
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007 partially
- FR-010 partially
- FR-012 partially
- FR-016 partially

### Why This Slice
- It hits the highest-risk architectural seam first.
- It preserves the core business value of automated acquisition documentation.
- It uses the strongest reusable legacy logic.
- It creates a measurable migration milestone with limited surface area.

## 6. Recommended Frontend Plan

### Initial Frontend
- React SPA with:
  - login
  - protocol list
  - protocol creation
  - read-only workspace

### Later Frontend Slices
- inline annotations
- status changes
- reassignment modals
- visibility management
- labtools pages

## 7. Recommended Backend Plan

### Initial Backend Modules
- `auth`
- `protocols`
- `ingestion`
- `media_processing`
- `rendering`
- `tasks`

### Later Backend Modules
- `reassignment`
- `visibility`
- `audit`
- `labtools`

## 8. Data Migration Approach

### Do Not Start With Full Historical Migration
- First prove live ingestion and new-session workflows.
- Historical import is lower risk once the target model stabilizes.

### Recommended Order
1. support new protocols created natively in the web system
2. validate live acquisitions end to end
3. import recent legacy protocols if needed
4. import older archival content only if there is business demand

### Historical Import Rules
- map ELOG attributes into canonical protocol fields
- map YAML customization into database-backed annotations
- map filesystem paths into stable storage keys and explicit sample paths
- preserve legacy protocol numbers

## 9. Authentication Rollout

### Phase-In
- start with OIDC user login for the web UI
- add protocol-scoped agent tokens for ingestion
- later enforce role and unit policies once the access-control model is ready

### Compatibility Note
- ELOG credentials must not remain part of the core application model
- if ELOG publishing is retained temporarily, isolate it in a compatibility adapter

## 10. Key Refactors to Avoid
- Do not port `autogui.py` behavior directly into the backend.
- Do not preserve filesystem paths as primary keys.
- Do not embed authorization rules inside UI code.
- Do not let Celery tasks own business rules that should live in services.
- Do not model the new system around ELOG concepts.

## 11. Risks to Watch During Execution
- hidden semantics in ELOG protocol numbering and status fields
- microscope-specific regressions in edge-case file formats
- annotation loss during rename/move if YAML recycling semantics are not preserved
- accidental reintroduction of path-coupled identity into the new schema
- overloading the first slice with access-control or historical-import complexity

## 12. Definition of Done for Web Primary Cutover
- new experiments are created only in the web app
- agent uploads go only to the backend
- operators review and annotate protocols only in the web app
- reassignment is supported in the web app
- visibility and audit requirements are enforced in the web app
- ELOG is either retired or reduced to non-authoritative export
