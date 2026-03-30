# Target Architecture

## 1. Architecture Goals
- Preserve business-critical microscope ingestion, metadata extraction, calibration, databar crop, rendering, and post-ingestion correction behavior.
- Remove direct coupling between UI, filesystem watching, ELOG, and domain logic.
- Support incremental migration with both legacy and new paths operating in parallel where needed.
- Establish maintainable service boundaries with explicit APIs, durable persistence, and testable domain services.

## 2. Recommended Architecture Style
- Use a modular web platform with a thin desktop agent and a service-oriented backend.
- Apply a strangler migration pattern:
  - extract reusable domain logic first
  - build the new backend around that logic
  - replace legacy desktop workflows one slice at a time
  - retire ELOG and direct filesystem dependence last

## 3. Recommended Stack

### Frontend
- React 18 + TypeScript
- React Router
- TanStack Query
- Zustand for local UI state only
- OpenSeadragon for deep zoom image viewing
- Tailwind CSS with a controlled design system

### Backend
- FastAPI on Python 3.12
- SQLAlchemy 2.x + Alembic
- Pydantic v2
- Celery for async processing
- Redis for Celery broker, task results, and pub/sub events

### Data and Storage
- PostgreSQL as the system of record
- S3-compatible object storage for originals, derivatives, exports, and attachments
- Redis for background processing coordination and real-time event fanout

### Authentication
- OIDC/OAuth2-based authentication
- Identity provider integrated with LDAP/Active Directory
- JWT access tokens plus refresh tokens
- Separate scoped protocol agent tokens for ingestion and close-session only

## 4. High-Level System Design

### Core Components
- `Web SPA`
  - protocol dashboard
  - protocol workspace
  - visibility and access management
  - labtools pages
- `API Backend`
  - protocol CRUD
  - search and filtering
  - metadata and annotation updates
  - reassignment operations
  - rendering/export endpoints
  - authz enforcement
- `Ingestion API`
  - receives uploads from the desktop agent
  - validates protocol-scoped agent tokens
  - persists ingestion jobs and initial file records
- `Processing Workers`
  - classify file type
  - detect microscope subtype
  - extract metadata
  - generate derivatives
  - calibrate
  - crop databar
  - render protocol HTML
- `Desktop Agent`
  - watches acquisition folders
  - computes `sample_path`
  - waits for file stability
  - pairs VEGA JPEG with sidecar metadata
  - uploads files to the backend
  - buffers uploads locally during outages
- `Compatibility Bridge`
  - optional transition component that can continue publishing selected data to ELOG until the organization stops depending on it

## 5. Logical Layers

### Presentation Layer
- React SPA
- no microscope-specific parsing logic in the browser

### Application Layer
- FastAPI routers
- use-case services
- authorization policies
- task orchestration

### Domain Layer
- protocol, sample, media, derivative, configuration, and access-control models
- microscope parsing and calibration services
- reassignment and rendering rules
- no Qt, ELOG, filesystem watcher, or HTTP framework dependencies

### Infrastructure Layer
- PostgreSQL repositories
- object storage adapters
- Celery tasks
- event publishing
- auth provider integration
- optional ELOG compatibility publisher

## 6. API Boundaries

### Public User API
- `/api/v1/auth/*`
- `/api/v1/protocols/*`
- `/api/v1/samples/*`
- `/api/v1/images/*`
- `/api/v1/tasks/*`
- `/api/v1/tools/*`
- `/api/v1/ws/protocols/{id}`

### Agent API
- `/api/v1/ingest`
- `/api/v1/protocols/{id}/close-session`
- optional `/api/v1/protocols/{id}/agent-config`

### Internal Boundaries
- `ProtocolService`
  - protocol creation
  - numbering
  - visibility and state changes
- `IngestionService`
  - request validation
  - file registration
  - task dispatch
- `ImageProcessingService`
  - subtype detection
  - metadata extraction
  - derivative generation
  - calibration
  - databar removal
- `ReassignmentService`
  - logical move, rename, remove, subtree changes
  - atomic DB + storage changes
- `RenderingService`
  - HTML generation
  - export artifacts
- `AuthorizationService`
  - role and visibility checks
  - sample override enforcement
- `AuditService`
  - restricted-access and reassignment logs

## 7. Data Persistence Approach

### PostgreSQL
- system of record for:
  - protocols
  - samples
  - microscope pictures
  - image derivatives
  - attachments
  - optical images
  - videos
  - navigation images
  - calibration configuration
  - experiment configuration
  - users
  - units
  - audit logs
- use UUID primary keys for domain entities
- keep `protocol_number` as a separate unique business identifier
- store dynamic microscope metadata in JSONB
- enforce visibility filtering as close to the database as practical

### Object Storage
- store:
  - original uploaded files
  - thumbnails
  - full-size PNG
  - DZI tile sets
  - cropped derivatives
  - XL40 frame derivatives
  - rendered HTML exports
  - attachments
- use stable storage keys independent of local workstation paths
- issue signed URLs with short TTLs

### Redis
- Celery broker and result backend
- real-time event fanout
- distributed locking for reassignment and render debounce

## 8. Authentication and Authorization Approach

### User Authentication
- Use OIDC with the organization’s identity provider.
- Back the identity provider with LDAP/AD where required.
- Use refreshable user sessions for the SPA.

### Agent Authentication
- Issue protocol-scoped agent tokens during experiment setup.
- Limit agent tokens to:
  - file ingestion
  - session close
- Do not allow agent tokens to call user workflows such as reassignment or visibility management.

### Authorization
- Implement explicit role checks for `SYSTEM_ADMIN`, `UNIT_MANAGER`, `OPERATOR`, and `READER`.
- Implement protocol visibility levels:
  - `PUBLIC`
  - `UNIT`
  - `RESTRICTED`
- Implement sample-level restricted overrides as first-class records, not UI-only masking.
- Log access to restricted resources.

## 9. Incremental Migration Design

### Principle
- Migrate behavior by capability slice, not by rewriting the entire legacy app at once.

### Shared Core Extraction
- First extract reusable logic from legacy into a new Python package with no Qt or ELOG dependency:
  - microscope picture subtype detection
  - metadata extraction
  - calibration
  - databar removal
  - derivative generation helpers
  - rendering helpers where still valuable
- This shared core should be callable from:
  - the new backend worker
  - transitional validation tools
  - possibly parts of the legacy desktop app during migration

### Legacy Coexistence
- Keep the legacy desktop app operational during early phases.
- Introduce the new web system beside it.
- Allow selective dual-running for validation on a limited set of protocols.
- If needed, keep ELOG publishing as a compatibility adapter rather than as a core domain dependency.

## 10. Recommended Bounded Contexts

### Experiment Setup
- protocol creation
- numbering
- agent configuration generation

### Acquisition and Ingestion
- file receipt
- sample-path interpretation
- acquisition session state

### Media Processing
- microscope subtype detection
- metadata extraction
- derivatives
- calibration
- cropping

### Protocol Workspace
- browsing
- annotations
- reassignment
- rendering/export

### Access Control
- users
- units
- visibility
- audit

### Labtools
- metadata dump
- FEI tools
- conversion

## 11. Handling Legacy-Specific Concerns

### ELOG
- Treat ELOG as an external legacy integration, not a core data store.
- During transition, optionally publish protocol summaries or rendered exports to ELOG from a dedicated adapter.
- Do not allow ELOG data structures to shape the new domain model.

### Filesystem-Derived Sample Hierarchy
- The new agent must convert local folder structure into explicit `sample_path`.
- The backend must treat `sample_path` as the contract.
- The backend must not rely on legacy folder naming conventions.

### YAML Customization
- Migrate editable custom fields into database-backed columns.
- Preserve the semantic behavior of YAML key recycling in the new reassignment service so that annotations survive move and rename operations.

## 12. First Slice to Implement

### Recommended First Slice
- Implement the minimum vertical slice for:
  - protocol creation
  - agent config download
  - agent upload of microscope images
  - server-side subtype detection
  - metadata extraction
  - thumbnail/full-size PNG generation
  - protocol workspace read-only view

### Why This Slice First
- It preserves the most business-critical automation from the legacy app.
- It validates the biggest architectural change early: moving from local watcher behavior to explicit agent-to-server ingestion.
- It exercises the highest-value reusable domain logic.
- It creates a usable path without waiting for full access-control or reassignment parity.

### Explicitly Deferred from Slice 1
- sample-level restricted overrides
- cross-protocol reassignment
- full audit reporting UI
- HTML export parity with every legacy template nuance
- full labtools migration

## 13. Maintainability Rules
- Keep all microscope-specific logic in backend domain modules, not in API routers or UI code.
- Keep object storage access behind adapters.
- Keep authorization checks centralized in one service layer.
- Keep Celery tasks thin; orchestration belongs in services.
- Do not allow frontend components to depend on backend implementation details beyond typed API contracts.
- Maintain a compatibility test suite using a representative set of legacy microscope files.

## 14. Recommended Deliverables Before Full Buildout
- shared core extraction plan
- canonical target data model
- API contract draft
- representative microscope fixture set
- parity test matrix for FEI, VEGA, and XL40
- ELOG retirement or compatibility decision document
