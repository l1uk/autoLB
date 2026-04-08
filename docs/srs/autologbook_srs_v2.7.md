**autologbook**

**Web Platform**

Software Requirements Specification & Architecture Document

**Version 2.7 --- Review-Amended**

2026-04-06

  --------------------- -------------------------------------------------
  **Property**          **Value**

  Status                Draft --- Review-Amended

  Source                autologbook v0.1.8 (reverse-engineered)

  Changes vs v2.6       Open-system architecture principles applied. (1)
                        data-service protocol decoupled from SEM domain:
                        file-notify returns opaque context_id; folder
                        naming is backend configuration (§8.2, RF-16).
                        (2) DataServiceTask payload generalised to
                        FILESYSTEM command object (§1.9, RF-18). (3)
                        RF-01 ingestion pipeline redesigned as
                        registerable handler chain (§2.1, §5.3). (4)
                        Access model generalised: Protocol.visibility
                        replaced by AccessPolicy entity with scope_type
                        OPEN/GROUP/EXPLICIT; UI labels and operator
                        experience unchanged (§1.3, §1.11, §3). (5)
                        Session token local validation made configurable
                        (§8.1). §7.1 updated.
  --------------------- -------------------------------------------------

**1. Domain Model --- Core Entities**

Core business entities derived from reverse-engineering autologbook
v0.1.8. Qt-specific references omitted. All entities are expressed as
data structures independent of any UI or transport layer.

v2.4 changes: DataServiceClient (§1.8), DataServiceTask (§1.9),
FileEvent (§1.10) added. idle_timeout_minutes, remote_storage_bucket and
mirroring_enabled removed from ExperimentConfiguration.
acquisition_status transitions are exclusively manual.

**1.1 MicroscopePicture**

The central domain object. Detection always runs server-side immediately
after file receipt.

  ----------------------- -----------------------------------------------
  **Field**               **Type / Description**

  id                      int --- DB sequence

  storage_key             string --- Object-storage path

  original_filename       string --- Filename as provided by the
                          data-service

  sample_path             string --- Relative path from protocol root,
                          e.g. SampleA/SubB

  picture_type            enum PictureType --- Detected server-side by
                          MicroscopePictureFactory

  params                  JSONB --- Dynamic metadata: magnification, HV,
                          WD, pixel size, etc.

  derivatives             List\[ImageDerivative\] --- Generated file
                          variants

  caption / description / string --- User-supplied annotation fields
  extra_info              

  has_metadata            bool --- False for VEGA JPEG before .hdr
                          sidecar arrives

  calibration_config      CalibrationConfig --- Per-image calibration
                          settings (§1.7)

  processing_status       enum --- PENDING / PROCESSING / DONE / ERROR

  created_at / updated_at datetime
  ----------------------- -----------------------------------------------

**ImageDerivative sub-entity**

  --------------------- -------------------------------------------------
  **Field**             **Type / Description**

  id                    UUID

  picture_id            int --- FK to MicroscopePicture

  derivative_type       enum --- THUMBNAIL / FULLSIZE_PNG / DZI / CROPPED
                        / FRAME_PNG

  storage_key           string --- Object-storage path

  url                   string --- Pre-signed URL (15-min TTL)

  frame_index           int / null --- Populated for FRAME_PNG (XL40
                        multiframe)

  created_at            datetime
  --------------------- -------------------------------------------------

**PictureType enum --- detection order is critical**

  ----------------------------------------------- ---------------- ------------------------------
  **Value**                                       **Instrument**   **Detection key**

  QUATTRO_MICROSCOPE_PICTURE                      FEI Quattro S    FEI tag 34680 (FEI_SFEG) +
                                                                   filename regex

  VERSA_MICROSCOPE_PICTURE                        FEI Versa 3D     FEI tag 34680 + filename regex

  FEI_MICROSCOPE_PICTURE                          Generic FEI      FEI tag 34680 or 34682, no
                                                                   filename match

  VEGA_MICROSCOPE_PICTURE                         TESCAN Vega TIFF Proprietary TIFF tag 50431

  VEGA_JPEG_MICROSCOPE_PICTURE                    TESCAN Vega JPEG JPEG + piexif MakerNote or
                                                                   .hdr sidecar

  XL40_MICROSCOPE_PICTURE                         Philips XL40     XMPMETA XML in TIFF IFD,
                                                                   single frame

  XL40_MULTIFRAME_MICROSCOPE_PICTURE              Philips XL40     XMPMETA + multi-page TIFF
                                                                   (SE + BSE)

  XL40_MULTIFRAME_WITH_STAGE_MICROSCOPE_PICTURE   Philips XL40     Multi-page + stage XMP

  XL40_WITH_STAGE_MICROSCOPE_PICTURE              Philips XL40     Single frame + stage XMP

  GENERIC_MICROSCOPE_PICTURE                      Unknown          Fallback --- always True,
                                                                   registered last
  ----------------------------------------------- ---------------- ------------------------------

**1.2 Sample**

Hierarchical container. Hierarchy is derived exclusively from the
sample_path field sent by the data-service. The server creates all
intermediate parent nodes automatically via check_and_add_parents().

  -------------------------- --------------------------------------------
  **Field**                  **Type / Description**

  id                         UUID

  protocol_id                UUID --- Parent protocol

  full_name                  string --- Hierarchical path, e.g.
                             SampleA/SubB/SubC

  last_name                  string --- Leaf node name only

  parent_id                  UUID / null --- null = top-level sample

  description                string --- User-supplied

  microscope_pictures /      Lists --- Recursive; access rules propagate
  videos / optical_images /  down
  attachments / subsamples   

  access_policy_id           UUID --- FK to AccessPolicy; inherits from
                             Protocol; overrideable at sample level
  -------------------------- --------------------------------------------

**1.3 Protocol**

Root document for a complete SEM analysis session. The Protocol IS the
logbook entry.

> **KEY CHANGE v2.3:** v2.7: Protocol.visibility (enum
> PUBLIC/UNIT/RESTRICTED) replaced by access_policy_id (FK to
> AccessPolicy). The operator-facing UI labels are unchanged --- Public,
> Unit, Restricted map to scope_type OPEN, GROUP, EXPLICIT respectively.
> allowed_users and the UNIT hardcoding are removed from the Protocol
> entity. See §1.12 for AccessPolicy.

  ----------------------- -----------------------------------------------
  **Field**               **Type / Description**

  id                      UUID

  protocol_number         int --- Unique numeric ID, application-managed
                          sequence

  project                 string

  responsible             string --- Operator name

  microscope_type         enum --- Quattro / Versa / Vega / XL40 / Multi

  introduction /          text --- Included in HTML export only if
  conclusion              non-empty

  samples                 List\[Sample\] --- Ordered, hierarchical

  optical_images /        Lists --- Protocol-level
  attachments /           
  navigation_images       

  status                  enum --- DRAFT / ACTIVE / LOCKED --- controls
                          edit authorisation

  acquisition_status      enum --- ONGOING / COMPLETED --- manual-only
                          transition

  access_policy_id        UUID --- FK to AccessPolicy; defines who can
                          see this protocol

  owner_id                UUID --- User who created the protocol

  unit_id                 UUID --- Organisational group; used to
                          pre-populate GROUP scope_type on creation; not
                          normative for access checks

  yaml_customization      JSONB --- Merged customization store

  html_export_cache       text --- Last generated HTML export (RF-08);
                          not used for UI rendering

  html_exported_at        datetime --- Timestamp of last export
                          generation

  created_at / updated_at datetime
  ----------------------- -----------------------------------------------

**1.4 Attachment**

  ----------------------- -----------------------------------------------
  **Field**               **Type / Description**

  id                      UUID

  protocol_id / sample_id UUID --- Owner (project-level or sample-level)

  storage_key /           Object-storage path, filename, bytes
  original_filename /     
  file_size               

  attachment_type         enum --- GENERIC / UPLOAD

  caption / description / string
  extra_info              
  ----------------------- -----------------------------------------------

**1.5 OpticalImage / NavigationImage / Video**

Lightweight entities sharing caption / description / extra_info with
MicroscopePicture. OpticalImageType: GENERIC / KEYENCE / DIGITAL_CAMERA
/ DIGITAL_CAMERA_WITH_GPS. NavigationImage is Quattro-only.

**1.6 ExperimentConfiguration**

Replaces the legacy .exp / .ini file. Persisted in the database,
downloadable as JSON for data-service configuration.

> **KEY CHANGE v2.3:** idle_timeout_minutes, remote_storage_bucket and
> mirroring_enabled removed in v2.4. The data-service sends files
> directly to the backend (RF-17, RF-18); the backend owns all object
> storage operations. remote_storage_bucket is server-side configuration
> only and is not included in the JSON config downloaded by the
> data-service. acquisition_status is manual-only (RF-19).

  ----------------------- -----------------------------------------------
  **Field**               **Type / Description**

  id                      UUID

  protocol_id             UUID --- FK to Protocol

  microscope_type         enum

  watch_folder            string --- Path on acquisition PC (data-service
                          only; not used server-side)

  thumbnail_max_width     int --- Default 400px

  operator                string
  ----------------------- -----------------------------------------------

> **NOTE:** The local watch_folder is stored for documentation only. The
> server never uses it. Sample hierarchy is derived entirely from the
> sample_path field the data-service sends per file.

**1.7 CalibrationConfig**

Per-image calibration settings, resolved by picture_type. Extracted from
ExperimentConfiguration to support Multi-microscope sessions where FEI
and XL40 files may arrive interleaved.

  ----------------------- -------------------------------------------------
  **Field**               **Type / Description**

  picture_type            enum PictureType --- Which instrument type this
                          config applies to

  auto_calibration        bool --- Run calibration task for this instrument
                          type

  databar_removal         bool --- FEI only --- run crop_databar task

  calibration_algorithm   enum --- FEI_TAG / VEGA_PIXEL_SIZE / XL40_XMP
  ----------------------- -------------------------------------------------

**1.8 DataServiceClient (new in v2.2)**

Represents a data-service daemon installed on an acquisition PC. The
name is deliberately generic to support future instrumentation beyond
electron microscopy.

  --------------------- -------------------------------------------------
  **Field**             **Type / Description**

  id                    UUID

  hostname              string --- Host name of the PC

  display_name          string --- Human-readable label, renameable by
                        admin

  ip_address            string --- IP at time of last registration/auth

  watch_folder          string --- Root folder being monitored

  api_key_hash          string --- bcrypt hash of the static API key;
                        never returned in plain text after registration

  session_token         string / null --- Short-lived JWT emitted after
                        successful authentication (8h TTL)

  session_expires_at    datetime / null --- Expiry of current session
                        token

  status                enum --- ONLINE / OFFLINE / NEVER_SEEN

  last_seen             datetime --- Timestamp of last heartbeat received

  registered_at         datetime

  is_revoked            bool --- If true, all new auth attempts are
                        rejected (403)

  os_info               string --- E.g. \'Windows 10 Pro 22H2\' --- sent
                        at registration

  agent_version         string --- Version of the data-service binary
                        installed
  --------------------- -------------------------------------------------

**1.10 DataServiceTask (new in v2.2, updated v2.7)**

A task queued by the backend for a specific client, retrieved at the
next heartbeat poll. In v2.7 the task is a generic command object ---
the data-service executes it without needing domain knowledge.

  --------------------- -------------------------------------------------
  **Field**             **Type / Description**

  id                    UUID

  client_id             UUID --- FK to DataServiceClient

  protocol_id           UUID / null --- FK to Protocol (informational;
                        not sent to the data-service)

  task_type             string --- Top-level command category. Current
                        value: FILESYSTEM. Extensible without schema
                        changes.

  operation             string --- Operation within the category. Current
                        values: CREATE_DIR.

  params                JSONB --- Operation parameters. For
                        FILESYSTEM/CREATE_DIR: { path: string } relative
                        to watch_folder.

  status                enum --- PENDING / DELIVERED / SUCCESS / ERROR

  created_at            datetime

  delivered_at          datetime / null --- When client retrieved the
                        task via heartbeat response

  completed_at          datetime / null

  error_message         string / null
  --------------------- -------------------------------------------------

**1.11 FileEvent (new in v2.2, updated v2.7)**

Persisted audit record of every filesystem notification received from a
data-service client. In v2.7 the context_id field replaces the raw
protocol_id/sample_path in the upload request --- the data-service uses
it as an opaque token.

  --------------------- -------------------------------------------------
  **Field**             **Type / Description**

  id                    UUID

  context_id            UUID --- opaque token returned to the
                        data-service in the ACCEPT response; encodes
                        protocol_id and sample_path server-side; never
                        exposed to the data-service in decoded form

  client_id             UUID --- FK to DataServiceClient

  protocol_id           UUID / null --- resolved by the backend from
                        relative_path; null if path does not match any
                        known protocol

  relative_path         string --- Path relative to watch_folder as sent
                        by the data-service

  filename              string

  file_size             int --- Bytes declared by client at notification
                        time

  decision              enum --- ACCEPT / IGNORE

  decision_reason       string / null --- E.g. \'path did not resolve\',
                        \'file type excluded\'

  notified_at           datetime

  uploaded_at           datetime / null --- Populated only if ACCEPT and
                        upload completed
  --------------------- -------------------------------------------------

**1.12 AccessPolicy (new in v2.7)**

Replaces Protocol.visibility enum, Protocol.allowed_users, and
Sample.sample_visibility/sample_allowed_users. Decouples access control
from any specific organisational structure. The operator-facing UI
presents the same three options as before --- Public, Unit, Restricted
map to scope_type OPEN, GROUP, EXPLICIT respectively.

> **KEY CHANGE v2.3:** v2.7: Protocol.visibility,
> Protocol.allowed_users, Sample.sample_visibility and
> Sample.sample_allowed_users are removed. Both Protocol and Sample now
> carry access_policy_id FK to this entity. unit_id on Protocol is
> retained only to pre-populate group_id on creation; it is no longer
> the normative source for access decisions. RLS policies read from
> AccessPolicy.scope_type and AccessPolicy.group_id / allowed_ids.

  --------------------- -------------------------------------------------
  **Field**             **Type / Description**

  id                    UUID

  scope_type            enum --- OPEN / GROUP / EXPLICIT. OPEN = all
                        authenticated users (maps to legacy PUBLIC).
                        GROUP = members of group_id (maps to legacy
                        UNIT). EXPLICIT = users in allowed_ids only (maps
                        to legacy RESTRICTED).

  group_id              UUID / null --- Populated when scope_type =
                        GROUP. In the default deployment this is the
                        unit_id of the protocol owner. Any grouping
                        entity can be substituted without schema changes.

  allowed_ids           List\[UUID\] --- Populated when scope_type =
                        EXPLICIT. Users who may access this resource in
                        addition to the owner.

  owner_id              UUID --- The user who created the resource;
                        always has access regardless of scope_type.

  created_at            datetime
  --------------------- -------------------------------------------------

> **NOTE:** The backend creates an AccessPolicy automatically when a
> protocol or sample is created, pre-populating scope_type and group_id
> from the creating user\'s context. The operator never interacts with
> AccessPolicy directly --- they use the Public / Unit / Restricted
> selector in the UI which maps transparently to scope_type values.

**2. Functional Requirements --- Backend & Business Logic**

All heavy processing runs asynchronously via Celery. HTTP endpoints
return immediately with a task_id. This chapter contains all functional
requirements RF-01 through RF-22. RF-09 has been removed (content fully
covered by RF-01, RF-16 and RF-17); requirements are renumbered from
RF-10 onward. The underlying data-service technical protocol is detailed
in §8.

**2.1 RF-01 --- Unified Server-Side Ingestion Pipeline**

> **ARCHITECTURE DECISION:** The data-service sends a file notification
> first. The backend responds ACCEPT or IGNORE. Only if ACCEPT does the
> data-service transmit the binary. The pipeline is implemented as a
> chain of registerable handlers --- each handler receives a
> PipelineContext, enriches it, and passes it forward. New instrument
> types are supported by registering a new handler; no changes to the
> pipeline coordinator are required.

Trigger: data-service POST to /api/v1/data-service/upload (after
receiving ACCEPT from /api/v1/data-service/file-notify). See RF-16 for
the two-step notify→upload protocol.

**Pipeline steps --- handler chain**

  ---------- -------------------- --------------------------------------------------
  **Step**   **Handler**          **Description**

  1          ReceiveHandler       Persist raw bytes to object storage under
                                  temporary key; initialise PipelineContext

  2          FileTypeHandler      Guess ElementType from filename regex via
                                  RegexpRepository; set context.element_type

  3          PictureTypeHandler   Open with Pillow; run registered \_am_i_right()
                                  chain; set context.picture_type. New instrument
                                  types registered here without touching other
                                  steps.

  4          MetadataHandler      RF-02 --- dispatch to per-type metadata extractor;
                                  populate context.params JSONB

  5          StorageHandler       Move object to final key:
                                  {protocol_id}/{sample_path}/{filename}

  6          DerivativeHandler    RF-03 --- generate THUMBNAIL, FULLSIZE_PNG, DZI,
                                  FRAME_PNG; create ImageDerivative records

  7          CalibrationHandler   RF-04 --- select CalibrationConfig by
                                  context.picture_type; run calibrate task if
                                  auto_calibration=True

  8          DatabarHandler       RF-05 --- run crop_databar if databar_removal=True
                                  in selected CalibrationConfig

  9          SampleTreeHandler    check_and_add_parents(): create missing Sample
                                  nodes from context.sample_path

  10         NotifyHandler        WebSocket push to connected clients: new image
                                  available, processing status update
  ---------- -------------------- --------------------------------------------------

> **NOTE:** Each handler is a standalone unit: it reads from
> PipelineContext, writes back to PipelineContext, and has no direct
> dependency on adjacent handlers. A failure in any handler marks the
> image as ERROR and halts the chain. The HTML export cache (RF-08) is
> NOT updated automatically --- generated on-demand only.

**2.2 RF-02 --- Metadata Extraction**

-   FEI: read proprietary tags; compute magnification = display_width /
    horizontal_field_of_view

-   VEGA TIFF: parse VegaMetadataParser from TIFF tag 50431 via regex
    MetadataDecoder chain

-   VEGA JPEG: parse piexif MakerNote; if .hdr absent, set
    has_metadata=False and schedule embed_vega_jpeg_metadata task when
    sidecar arrives

-   XL40: parse XMPMETA XML via XMPMixin.find_xmp_element(); handle
    multi-page TIFF frames

**2.3 RF-03 --- Thumbnail and Derivative Generation**

-   THUMBNAIL: PNG at max_width=400px (configurable per
    ExperimentConfiguration)

-   FULLSIZE_PNG: full-size PNG conversion; 16-bit TIFF applies numpy
    intensity normalisation

-   DZI: Deep Zoom Image tile set via libvips for images \>10 megapixels

-   FRAME_PNG: one ImageDerivative per frame for XL40 multiframe
    (frame_index set)

-   Idempotent: skip if derivative already exists in object storage
    (force_regen=False default)

**2.4 RF-04 --- Image Calibration**

Algorithm selected per image based on picture_type via CalibrationConfig
--- not from a global flag.

-   FEI (FEI_TAG): compare ResolutionSource.TIFF_TAG vs FEI_TAG; write
    corrected values if different; set
    params\[\'calibration_applied\'\]=True

-   VEGA (VEGA_PIXEL_SIZE): use pixel_size_x/y from tag 50431; write
    corrected resolution

-   XL40 (XL40_XMP): use resolution from XMP metadata; write corrected
    resolution

-   GENERIC: no calibration --- skip silently

**2.5 RF-05 --- FEI Databar Removal**

-   Detect databar height from image data

-   Save cropped version as CROPPED ImageDerivative; original is never
    overwritten

-   Controlled by databar_removal field in the QUATTRO/VERSA/FEI
    CalibrationConfig entry

**2.6 RF-06 --- Protocol CRUD**

  -------------------------------------- ------------ -------------------------------------
  **Endpoint**                           **Method**   **Description**

  /api/v1/protocols                      POST         Create protocol; assign
                                                      protocol_number from DB sequence; set
                                                      acquisition_status=ONGOING

  /api/v1/protocols/{id}                 GET          Retrieve with all nested data

  /api/v1/protocols/{id}                 PATCH        Update intro, conclusion, status,
                                                      visibility, acquisition_status
                                                      (manual only --- RF-20)

  /api/v1/protocols/{id}/samples         POST         Add a sample (server creates parent
                                                      chain from path)

  /api/v1/protocols/{id}/samples/{sid}   DELETE       Remove sample; cascade-remove empty
                                                      parents

  /api/v1/protocols/{id}/export          GET          Generate and return HTML export ---
                                                      see RF-08

  /api/v1/protocols                      GET          Search/list with SQL-level visibility
                                                      filter
  -------------------------------------- ------------ -------------------------------------

**2.7 RF-07 --- Protocol Customization**

caption, description, extra_info fields live directly on each entity
record. PATCH on any element updates the field and triggers a WebSocket
push to update the React UI immediately. YAMLRecycler logic preserves
custom fields on item move/rename (RF-14).

**2.8 RF-08 --- Protocol HTML Export**

> **KEY CHANGE v2.3:** RF-08 is redefined in v2.3. The React SPA is the
> primary and only UI for viewing protocol data. RF-08 covers only the
> generation of a standalone HTML file for archival, printing, or
> sharing outside the system. The html_export_cache field on Protocol
> stores the last generated export; it is NOT used for rendering the UI
> and is NOT invalidated on protocol mutations.

The HTML export renders a complete, self-contained snapshot of the
protocol at the time of request, using Jinja2 templates. It is generated
on-demand only.

  ------------------ ----------------------------------------------------
  **Aspect**         **Specification**

  Trigger            User clicks \'Export HTML\' in the Protocol
                     Workspace top bar → GET
                     /api/v1/protocols/{id}/export

  Generation         Backend renders Jinja2 template with all protocol
                     data; returns as application/octet-stream download

  Caching            html_export_cache stores last generated output; used
                     only to serve repeated download requests quickly,
                     not for UI display

  Cache validity     Invalidated only when user explicitly requests a new
                     export; NOT invalidated on protocol mutations

  Format             Single self-contained .html file with inline CSS;
                     all images embedded as base64 data URIs or linked
                     via pre-signed URLs (15-min TTL)

  Access             Any user with read access to the protocol may
                     download the export
  ------------------ ----------------------------------------------------

> **NOTE:** Jinja2 is now a dependency of the export service only, not
> of the core application stack. The React SPA fetches protocol data
> directly from REST API endpoints and renders it natively. There is no
> server-side rendering of the primary UI.

**2.9 RF-09 --- Integrated Logbook**

  -------------------------- --------------------------------------------
  **Legacy ELOG feature**    **Web platform equivalent**

  ELOG entry per protocol    Protocol record; viewed natively in React
                             SPA

  ELOG attributes (Operator, Protocol entity fields with search/filter
  Protocol ID)               

  ELOG Edit Lock             Protocol.status = LOCKED / ACTIVE

  Analysis Status (On going  Protocol.acquisition_status = ONGOING /
  / Completed)               COMPLETED (manual-only)

  ELOG page size limit (240  Not applicable --- React SPA fetches
  KB)                        paginated API data

  ELOG search                PostgreSQL full-text search on Protocol
                             fields

  Write URL file             Each protocol has a permanent shareable URL

  HTML export for archival   RF-08 --- on-demand HTML export with
                             embedded images
  -------------------------- --------------------------------------------

**2.10 RF-10 --- File Ingestion Transport**

> **KEY CHANGE v2.3:** v2.4: the data-service sends files exclusively to
> the backend via the two-step notify→upload protocol (RF-16, RF-17).
> The data-service has no knowledge of object storage, bucket names or
> storage keys. All persistence to object storage is performed by the
> backend after receiving the binary. The fields remote_storage_bucket
> and mirroring_enabled have been removed from ExperimentConfiguration.

  ------------------ ----------------------------------------------------
  **Aspect**         **Specification**

  Transport          data-service → backend only (HTTPS POST to
                     /api/v1/data-service/upload)

  Storage            Backend persists to object storage after receiving
                     binary; data-service is not involved

  Retry              data-service retries failed uploads with exponential
                     backoff (default: max_attempts=5, wait 0.5--30s)

  Offline buffer     Uploads queued in local SQLite if backend
                     unreachable; replayed FIFO on reconnection

  Status check       GET /api/v1/protocols/{id}/storage-status ---
                     returns which files are present in object storage vs
                     expected from the protocol tree
  ------------------ ----------------------------------------------------

**2.11 RF-11 --- New Experiment Wizard (API Flow)**

-   Step 1: GET /api/v1/protocols/next-number --- next available
    protocol_number from DB sequence

-   Step 2: POST /api/v1/protocols --- create Protocol; set
    acquisition_status=ONGOING

-   Step 3: GET /api/v1/protocols/{id}/agent-config --- download JSON
    config for the data-service (watch_folder, protocol_id, auth
    endpoint, heartbeat interval)

-   Step 4: Queue CREATE_FOLDER tasks for selected clients via RF-21
    (optional)

-   Step 5: Data-service starts, reads config, begins monitoring local
    folder

**2.12 RF-12 --- Labtools Endpoints**

-   POST /api/v1/tools/metadata --- dump all TIFF/EXIF/XMP metadata as
    JSON

-   POST /api/v1/tools/fei/calibrate --- standalone FEI calibration on
    an uploaded file

-   POST /api/v1/tools/fei/crop-databar --- standalone databar removal

-   POST /api/v1/tools/convert --- convert TIFF to PNG/JPEG with
    optional resize

-   POST /api/v1/tools/fei/check --- detect FEI subtype (FEI_SFEG vs
    FEI_HELIOS)

**2.13 RF-13 --- Post-Ingestion Element Reassignment**

> **ARCHITECTURE DECISION:** Implements the equivalent of the legacy
> FileSystemCommander (gui.py). Reassignment is logical (DB + object
> storage key update), not a filesystem operation on the acquisition PC.

  -------------------- ------------------------------ -----------------------------
  **Operation**        **Endpoint**                   **Description**

  Move image to        PATCH                          Update sample_id and
  different sample     /api/v1/images/{id}/sample     storage_key; create parent
                                                      samples if needed; preserve
                                                      custom fields (YAMLRecycler)

  Move image to        PATCH                          OPERATOR if destination
  different protocol   /api/v1/images/{id}/protocol   protocol is own; UNIT_MANAGER
                                                      (own unit) or SYSTEM_ADMIN
                                                      for any

  Rename image         PATCH                          Updates original_filename;
                       /api/v1/images/{id}/filename   storage_key suffix unchanged

  Remove image         DELETE /api/v1/images/{id}     Soft-delete: REMOVED status;
                                                      retained in object storage 30
                                                      days before purge

  Move sample subtree  PATCH                          Reassign sample and all
                       /api/v1/samples/{id}/parent    contents to new parent;
                                                      update full_name of all
                                                      descendants
  -------------------- ------------------------------ -----------------------------

**2.14 RF-14 --- Data-Service Registration & Session Authentication**

Machine-to-machine authentication pattern: one-time API key
registration; per-connection session token. Full implementation details
in §8.1.

  ------------------------------- ------------ -------------------------------------
  **Endpoint**                    **Method**   **Description**

  /api/v1/data-service/register   POST         One-time registration: body {
                                               hostname, watch_folder, os_info,
                                               agent_version }; response {
                                               client_id, api_key } --- api_key
                                               returned in plain text exactly once

  /api/v1/data-service/auth       POST         Per-connection auth: body {
                                               client_id, api_key }; response {
                                               session_token, expires_at };
                                               session_token is JWT RS256 with 8h
                                               TTL
  ------------------------------- ------------ -------------------------------------

> **NOTE:** TLS mandatory on all data-service endpoints. api_key stored
> server-side as bcrypt hash only. session_token used as Bearer token on
> all subsequent requests.

**TLS specification**

All communication between the data-service and backend is encrypted via
TLS. The following constraints apply:

  --------------------- -------------------------------------------------
  **Parameter**         **Requirement**

  Minimum version       TLS 1.2 --- required for Windows 7 compatibility
                        (Go crypto/tls supports TLS 1.2 on Windows 7 via
                        syscall)

  Recommended version   TLS 1.3 --- used automatically by Go\'s
                        crypto/tls when both sides support it

  Certificate           Server certificate must be verified by the client
  verification          --- InsecureSkipVerify must never be set to true
                        in production

  CA bundle (public CA) Go\'s crypto/tls uses the OS trust store by
                        default --- no configuration needed for publicly
                        signed certificates

  CA bundle (internal   Custom CA certificate configurable in the
  CA)                   data-service config file: ca_cert_path points to
                        a PEM file loaded into x509.CertPool and injected
                        into tls.Config.RootCAs

  Cipher suites         Go\'s crypto/tls default cipher suite selection
                        is used --- no manual override needed; Go
                        automatically prefers ECDHE and AES-GCM

  Certificate on server Nginx handles TLS termination; the FastAPI
                        backend sees plain HTTP on the loopback interface
  --------------------- -------------------------------------------------

> **SECURITY:** For on-premise deployments with a self-signed
> certificate or an internal CA (common in laboratory environments), the
> operator must distribute the CA certificate to each acquisition PC and
> set ca_cert_path in the data-service config. The data-service will
> refuse to connect if certificate verification fails --- this is
> intentional and must not be bypassed.

**2.15 RF-15 --- Heartbeat & Task Delivery**

The data-service sends periodic keepalive messages. The backend responds
with any pending tasks for that client.

  -------------------------------- ------------ -----------------------------------
  **Endpoint**                     **Method**   **Description**

  /api/v1/data-service/heartbeat   POST         Body: { client_id, agent_version,
                                                status_info }; response: { tasks:
                                                \[{id, task_type, payload}\] };
                                                backend updates last_seen and
                                                status=ONLINE; client marked
                                                OFFLINE if no heartbeat for 3×
                                                configured interval
  -------------------------------- ------------ -----------------------------------

**2.16 RF-16 --- File Event Notification (Notify → ACCEPT/IGNORE)**

The data-service notifies the backend of a detected filesystem event
before transmitting the binary. The backend decides ACCEPT or IGNORE.
Only if ACCEPT does the data-service proceed to RF-17.

> **KEY CHANGE v2.3:** v2.7: the file-notify request no longer carries
> protocol-domain semantics. The data-service sends a path and filename
> --- it does not know what a \'protocol\' is. The backend interprets
> the path according to its own configuration (e.g. extracting a
> protocol number via regex) and responds with an opaque context_id. The
> data-service includes context_id in the subsequent upload without
> needing to understand its meaning. This decouples the data-service
> from the SEM domain entirely.

  ---------------------------------- ------------ -----------------------------------
  **Endpoint**                       **Method**   **Description**

  /api/v1/data-service/file-notify   POST         Body: { client_id, relative_path,
                                                  filename, file_size }; response: {
                                                  decision: ACCEPT\|IGNORE, reason?,
                                                  context_id? } --- context_id is an
                                                  opaque token the data-service must
                                                  include in the upload; it encodes
                                                  backend routing information (e.g.
                                                  protocol_id, sample_path) without
                                                  exposing domain logic to the client
  ---------------------------------- ------------ -----------------------------------

**ACCEPT/IGNORE decision rules**

-   ACCEPT if: the backend\'s path interpretation logic (configured
    regex or routing rules) resolves the relative_path to a known,
    active resource with acquisition_status=ONGOING

-   IGNORE if: path does not resolve to any known resource

-   IGNORE if: resolved resource has status=LOCKED

-   IGNORE if: file extension is in the configured exclusion list (e.g.
    .tmp, .part)

-   All decisions are persisted as FileEvent records regardless of
    outcome

-   The path interpretation logic (e.g. \'extract protocol number from
    folder name matching regex\') is server-side configuration, not part
    of the data-service protocol

**2.17 RF-17 --- File Upload (post-ACCEPT)**

Executed by the data-service only after receiving ACCEPT from RF-16.
Triggers the RF-01 ingestion pipeline. The data-service does not need to
know the protocol_id or sample_path --- it passes the opaque context_id
received from RF-16 and the backend resolves routing internally.

  ----------------------------- ------------ -----------------------------------
  **Endpoint**                  **Method**   **Description**

  /api/v1/data-service/upload   POST         multipart/form-data: { context_id,
                                             filename, file (binary) }; backend
                                             decodes context_id to resolve
                                             protocol_id, sample_path, and other
                                             routing; triggers RF-01 Celery
                                             chain; updates
                                             FileEvent.uploaded_at on completion
  ----------------------------- ------------ -----------------------------------

**2.18 RF-18 --- Task Execution & Acknowledgement**

The data-service executes tasks delivered in the heartbeat response
(RF-15) and reports results.

> **KEY CHANGE v2.3:** v2.7: task_type is no longer a closed enum. Tasks
> are now command objects with a category and operation. The
> data-service is a generic command executor --- it does not need domain
> knowledge to execute a task. New task types can be added server-side
> without updating the data-service binary, as long as they use existing
> categories.

  ------------ ------------------ ----------------------------------------
  **Field**    **Example value**  **Description**

  task_type    FILESYSTEM         Top-level category. Current supported
                                  value: FILESYSTEM. Extensible to
                                  NETWORK, CONFIG, PROCESS without
                                  data-service code changes.

  operation    CREATE_DIR         Operation within the category. Current
                                  FILESYSTEM operations: CREATE_DIR,
                                  DELETE_DIR (future), RENAME_DIR
                                  (future).

  params       {\"path\":         Operation parameters. For CREATE_DIR:
               \"2024-0042\"}     path relative to watch_folder. The
                                  data-service does not interpret the path
                                  semantics.
  ------------ ------------------ ----------------------------------------

  ------------------------------- ------------ -----------------------------------
  **Endpoint**                    **Method**   **Description**

  /api/v1/data-service/task-ack   POST         Body: { task_id, status:
                                               SUCCESS\|ERROR, error_message? };
                                               backend updates
                                               DataServiceTask.status,
                                               completed_at, error_message
  ------------------------------- ------------ -----------------------------------

> **NOTE:** FILESYSTEM / CREATE_DIR is idempotent: if the directory
> already exists the task reports SUCCESS. Tasks remain PENDING until
> ACKed --- a client restart before ACKing causes re-delivery at the
> next heartbeat.

**2.19 RF-19 --- Acquisition Status --- Manual Transition Only**

> **KEY CHANGE v2.3:** acquisition_status has no automatic transitions.
> idle_timeout_minutes has been removed from ExperimentConfiguration.
> acquisition_status=COMPLETED is set exclusively by an authenticated
> user via PATCH /api/v1/protocols/{id} or the \'Mark acquisition
> complete\' button in the Protocol Workspace. The data-service going
> offline does not change acquisition_status.

Rationale: automatic timeout transitions caused false COMPLETED states
for overnight or multi-day sessions. Operators are responsible for
explicitly closing a session.

**2.20 RF-20 --- Data-Service Admin Panel**

Backend endpoints for SYSTEM_ADMIN management of all DataServiceClient
records.

  ------------------------------------------------ ------------ --------------------------------
  **Endpoint**                                     **Method**   **Description**

  /api/v1/admin/data-service-clients               GET          List all clients (any status),
                                                                paginated; includes is_revoked,
                                                                last_seen, agent_version,
                                                                os_info

  /api/v1/admin/data-service-clients/{id}          PATCH        Update display_name

  /api/v1/admin/data-service-clients/{id}/revoke   PATCH        Set is_revoked=True; invalidate
                                                                active session_token via Redis
                                                                JWT blacklist

  /api/v1/admin/data-service-clients/{id}          DELETE       Remove client record; only
                                                                allowed if status=OFFLINE or
                                                                NEVER_SEEN

  /api/v1/admin/data-service-clients/{id}/tasks    GET          List all DataServiceTask records
                                                                for this client, paginated
  ------------------------------------------------ ------------ --------------------------------

**2.21 RF-21 --- Experiment Wizard --- Folder Deployment**

> **ARCHITECTURE DECISION:** During protocol creation, the operator may
> select data-service clients on which to create the protocol folder.
> Only ONLINE and OFFLINE clients are selectable. NEVER_SEEN clients are
> excluded --- they have never connected and their watch_folder
> configuration is unverified. ONLINE clients execute at the next
> heartbeat; OFFLINE clients execute when they next connect.

  ------------------------------------- ------------ -----------------------------------
  **Endpoint**                          **Method**   **Description**

  /api/v1/data-service-clients          GET          List all non-revoked, non-deleted
                                                     clients with current status;
                                                     NEVER_SEEN clients included in list
                                                     but flagged as non-selectable for
                                                     folder deployment

  /api/v1/protocols/{id}/folder-tasks   POST         Body: { client_ids: \[UUID\] };
                                                     only ONLINE or OFFLINE client_ids
                                                     accepted; returns 400 if a
                                                     NEVER_SEEN client_id is included;
                                                     returns { tasks: \[{client_id,
                                                     task_id, status}\] }

  /api/v1/protocols/{id}/folder-tasks   GET          List all CREATE_FOLDER tasks for
                                                     this protocol with current status
  ------------------------------------- ------------ -----------------------------------

**2.22 RF-22 --- Post-Creation Folder Deployment**

From the Protocol Workspace, an operator can add the protocol folder to
any ONLINE or OFFLINE data-service client at any time after protocol
creation, as long as protocol.status != LOCKED. Uses the same POST
/api/v1/protocols/{id}/folder-tasks endpoint as RF-21. NEVER_SEEN
clients are excluded. Clients with an existing SUCCESS CREATE_FOLDER
task for this protocol are excluded.

**3. Access Control Model**

Access control operates at two levels: group (unit/department) and
individual user. In v2.7 the visibility enum has been replaced by the
AccessScope value object (§1.3), which makes the model extensible
without code changes. The three UI-facing presets (PUBLIC, Unit only,
Restricted) behave identically to the previous PUBLIC/UNIT/RESTRICTED
enum from the user\'s perspective.

**3.1 Principals**

  ------------------ ----------------------------------------------------
  **Principal**      **Description**

  User               Individual authenticated account; has a primary
                     unit_id; optionally belongs to additional units

  Unit               Organisational group (e.g. a laboratory department);
                     has one or more Unit Managers

  Role               System-wide: SYSTEM_ADMIN / UNIT_MANAGER / OPERATOR
                     / READER
  ------------------ ----------------------------------------------------

**3.2 AccessScope --- Protocol and Sample Visibility**

Every Protocol and Sample carries an AccessScope value object. The
backend evaluates access by inspecting the type field and matching it
against the requesting user\'s identity and group memberships.

  ----------- ------------------------------------------- ---------------
  **type**    **Access rule**                             **UI preset
                                                          label**

  ALL         Any authenticated user in the system can    PUBLIC
              see this resource                           

  GROUP       Only members of the group identified by     Unit only
              group_id (primary or guest) can see this    (default)
              resource                                    

  EXPLICIT    Only the resource owner and users listed in Restricted
              allowed_ids can see this resource.          
              Invisible to everyone else including group  
              members.                                    
  ----------- ------------------------------------------- ---------------

> **SECURITY:** The EXPLICIT type is the strongest form of access
> restriction. The resource is completely invisible in search results,
> lists, and any API response to users not in allowed_ids --- including
> members of the owner\'s unit. No title, metadata, or thumbnail leaks.

**3.3 Extensibility**

New access types can be introduced by adding a new type value and
corresponding evaluation logic in the AuthorizationService. No schema
migration is required --- AccessScope is stored as JSONB. Example future
extension:

  --------------- -------------------------------------------------------
  **Future type** **Intended semantics**

  DEPARTMENT      Visible to all members of a parent department (group
                  hierarchy not yet implemented --- see §7.1)

  CONSORTIUM      Visible to members of a defined inter-unit consortium
                  --- useful for multi-lab collaborative projects

  TIMED           Visible to all after a specified embargo_until date
                  (useful for pre-publication data)
  --------------- -------------------------------------------------------

**3.4 Permission Matrix**

  -------------------------- ------------------ ---------------- ---------------
  **Action**                 **SYSTEM_ADMIN**   **UNIT_MANAGER   **OPERATOR (own
                                                (own unit)**     protocol)**

  List ALL-scope protocols   Y                  Y                Y

  List GROUP-scope protocols Y                  Y (own unit)     Y (own unit)

  List EXPLICIT-scope        Y                  N                Y (own)
  protocols                                                      

  View EXPLICIT-scope        Y                  N                Y (own or in
  protocol                                                       allowed_ids)

  Create protocol            Y                  Y                Y

  Edit protocol metadata     Y                  Y (own unit)     Y (own)

  Change protocol            Y                  Y (own unit)     Y (own)
  access_scope                                                   

  Add user to allowed_ids    Y                  Y (own unit)     Y (own)

  Reassign image to          Y                  Y (own unit)     Y (own)
  different sample                                               

  Reassign image to          Y                  Y (own unit)     Y (if
  different protocol                                             destination is
                                                                 own)

  Lock / Unlock protocol     Y                  Y (own unit)     Y (own)

  Mark acquisition complete  Y                  Y (own unit)     Y (own)
  (RF-19)                                                        

  Delete protocol            Y                  Y (own unit)     Y (own)

  Download HTML export       Y                  Y (own unit)     Y (own or in
  (RF-08)                                                        allowed_ids)

  Manage DataServiceClient   Y                  N                N
  (RF-20)                                                        
  -------------------------- ------------------ ---------------- ---------------

**3.5 Unit Membership Model**

-   A User has one primary unit_id; can be added as guest to other units
    by a UNIT_MANAGER

-   GROUP-scope protocols are visible to all members (primary or guest)
    of the group identified by group_id

-   EXPLICIT-scope protocols are NOT visible to group members unless
    explicitly listed in allowed_ids

-   Membership changes propagate immediately --- queries are DB-backed,
    no cache to invalidate

**3.6 Sample-Level Access Override**

> **NOTE:** A sample\'s access_scope can be set independently of the
> parent protocol\'s access_scope. If a protocol is GROUP-scope but
> contains a sensitive sample, that sample can be set to EXPLICIT-scope.
> The protocol remains visible to group members; the restricted sample
> appears as \'\[Confidential sample\]\' with no content or count
> visible to unauthorised users.

**3.7 API Enforcement**

-   All API endpoints check permissions via dependency-injected
    AuthorizationService

-   Protocol and sample list queries apply access_scope filters at SQL
    level via Row-Level Security (RLS) --- never post-filtered in
    application code

-   RLS policies evaluate the AccessScope JSONB field directly: type=ALL
    passes all users; type=GROUP checks unit membership; type=EXPLICIT
    checks allowed_ids array

-   Object storage URLs are pre-signed with 15-minute TTL

-   Audit log: all access to EXPLICIT-scope resources logged (user,
    timestamp, endpoint, IP)

-   Data-service session tokens scoped only to /api/v1/data-service/\*
    endpoints

**3.8 Authentication (Human Users)**

-   JWT Bearer tokens (15 min) + refresh tokens (7 days)

-   Integration with institutional LDAP/Active Directory via
    oauth2-proxy or python-ldap

-   Fallback: local accounts for external collaborators

-   MFA optional --- enforced by SYSTEM_ADMIN per user or per unit

**4. User Flows --- Web UI**

The React SPA is the primary interface for all protocol viewing and
annotation. File content enters the system exclusively via the
data-service. This chapter covers all user flows, including those
introduced in v2.2 for data-service management and folder deployment.

**4.1 Flow 1 --- New Experiment**

**Step 1 --- Parameters**

-   Microscope type (Quattro / Versa / Vega / XL40 / Multi)

-   Operator (pre-filled from authenticated user, editable)

-   Project name, Customer

-   Visibility (PUBLIC / UNIT / RESTRICTED) --- default UNIT

-   If RESTRICTED: user search to pre-populate allowed_users

-   Protocol number: read-only, assigned by server on creation

**Step 2 --- Confirm & Download Data-Service Config**

-   \'Create experiment\' → server creates Protocol
    (acquisition_status=ONGOING)

-   Download JSON config file for the data-service

**Step 3 --- Folder Deployment (optional, new in v2.2)**

-   See Flow 8 --- operator selects acquisition PCs; CREATE_FOLDER tasks
    queued

**Step 4 --- Workspace opens**

-   Protocol Workspace opens empty, waiting for first file from
    data-service

-   Acquisition status banner: \'Acquisition in progress\'

**4.2 Flow 2 --- Protocol Dashboard**

-   Search bar: full-text search across project, responsible,
    protocol_number, customer

-   Filter chips: microscope type, unit, date range, status,
    acquisition_status, visibility

-   Results grid: card per protocol (thumbnail, number, project, date,
    status chips)

-   UNIT and RESTRICTED protocols of other units absent from results

-   Click card → Protocol Workspace

**4.3 Flow 3 --- Protocol Workspace**

Three-column layout --- all data fetched via REST API and rendered by
the React SPA.

**Left panel --- Sample Tree**

-   Collapsible tree; populated exclusively from API data as the
    data-service pushes files

-   Status badges: image count, processing state (PENDING / DONE /
    ERROR)

-   RESTRICTED samples shown as \'\[Confidential\]\' for unauthorised
    users

-   Context menu (authorised users): Move to sample, Rename, Remove,
    Restrict, Lock, View audit log

**Centre panel --- Content Area**

-   Deep-zoom image viewer (OpenSeadragon) using DZI tiles via API for
    images \>10 MP

-   Frame selector for XL40 multiframe: switch between FRAME_PNG
    derivatives (SE/BSE)

-   Processing status: live updates via WebSocket push
    (\'Calibrating\...\', \'Thumbnail ready\', \'Cropped version
    available\')

-   Acquisition status bar: \'Acquisition in progress\' / \'Acquisition
    completed\'

-   Metadata accordion: human-readable params fetched from API

-   FEI Cropped/Original toggle: switch between original TIFF and
    CROPPED ImageDerivative

**Right panel --- Edit Panel**

-   caption, description, extra_info --- auto-save with debounce via
    PATCH API calls

-   Protocol-level introduction and conclusion: inline text areas at
    top/bottom of protocol view

**Top bar**

-   Protocol status chip (DRAFT / ACTIVE / LOCKED) + acquisition_status
    chip (ONGOING / COMPLETED)

-   Visibility chip --- click to change if authorised

-   \'Export HTML\' → triggers RF-08 export download (not used for UI
    rendering)

-   \'Lock protocol\' → sets status=LOCKED; disables all edits and
    reassignment

-   \'Mark acquisition complete\' → sets acquisition_status=COMPLETED
    (manual only --- RF-19)

-   \'Create folder on machine\...\' → opens Flow 9 modal

-   Data-service connection status badge with last-seen timestamp

-   Real-time task progress bar (WebSocket-driven)

**4.4 Flow 4 --- Post-Ingestion Correction (RF-14)**

-   Operator right-clicks misplaced image in Sample Tree → \'Move to
    sample\...\'

-   Modal shows full sample tree with picker; operator selects correct
    target → \'Move\'

-   Server: copies object to new key, updates DB, preserves custom
    fields, deletes old key, triggers WebSocket push

-   Audit log entry written with old and new sample path

> **CONSTRAINT:** Reassignment is blocked if protocol.status=LOCKED.
> Operator must unlock first, correct, then re-lock.

**4.5 Flow 5 --- Sensitivity Management**

-   Protocol owner or UNIT_MANAGER can change visibility while status !=
    LOCKED

-   Changing to RESTRICTED: modal prompts to add allowed_users

-   Changing from RESTRICTED: modal warns images will become visible to
    unit

-   Sample-level: right-click sample → \'Restrict this sample\' →
    allowed_users modal

**4.6 Flow 6 --- Labtools Standalone Page**

-   Metadata Viewer: upload TIFF/JPEG → display full metadata tree as
    JSON (stateless)

-   FEI Tools: calibrate / crop-databar on individual files without
    creating a protocol

-   Image Converter: upload TIFF → configure output format/size →
    download

-   All labtools operations are stateless --- files are not persisted
    server-side

**4.7 Flow 7 --- Admin Panel: Data-Service Client Management (RF-20)**

Accessible only to SYSTEM_ADMIN via Settings \> Data Services.

-   Table columns: display_name, hostname, IP, watch_folder, status
    badge, last_seen, agent_version, os_info

-   Status badge auto-refreshes via WebSocket on status change

-   Row actions: Rename (inline edit); Revoke API key (confirmation
    modal → is_revoked=True; active session invalidated); Remove (only
    if OFFLINE or NEVER_SEEN)

-   ONLINE clients cannot be deleted; Revoke must be performed first

-   Expand row → Task History: paginated DataServiceTask records with
    status, payload, timestamps, error_message

-   \'Register new client\' button → displays registration CLI command
    for operator to run on target PC

**4.8 Flow 8 --- Experiment Wizard: Folder Deployment Step (RF-21)**

Optional step in the New Experiment Wizard (Flow 1), immediately after
protocol creation.

**Client list**

-   Shows all non-revoked, non-deleted DataServiceClient records
    (ONLINE + OFFLINE + NEVER_SEEN)

-   ONLINE and OFFLINE clients are selectable (checkbox enabled)

-   NEVER_SEEN clients are shown but not selectable --- greyed out with
    tooltip: \'Client has never connected --- folder deployment not
    available until first connection\'

-   Status badge per row: 🟢 ONLINE \'Folder created at next heartbeat
    (\~30s)\' / ⚫ OFFLINE \'Task queued --- executes on reconnect\'

-   If no ONLINE or OFFLINE clients are registered: informational
    banner + link to Admin Panel (Flow 7)

**After confirming selection**

-   Backend queues CREATE_FOLDER tasks; frontend polls GET
    /api/v1/protocols/{id}/folder-tasks every 5s (or receives WebSocket
    push)

-   ONLINE clients: spinner (PENDING/DELIVERED) → ✓ SUCCESS / ✗ ERROR
    with error_message

-   OFFLINE/NEVER_SEEN clients: \'Task queued --- execution deferred\'
    badge immediately; no spinner

-   \'Finish\' button always enabled --- step result does not block
    wizard completion

-   \'Skip\' → no tasks queued; folders can be created later from
    Protocol Workspace (Flow 9)

**4.9 Flow 9 --- Post-Creation Folder Deployment (Protocol Workspace)
(RF-22)**

Accessible from the Protocol Workspace top bar at any time while
protocol.status != LOCKED.

-   \'Create folder on machine\...\' button --- disabled if
    status=LOCKED (tooltip: \'Unlock protocol first\')

-   Modal lists all non-revoked, non-deleted ONLINE and OFFLINE clients
    that do NOT already have a SUCCESS CREATE_FOLDER task for this
    protocol; NEVER_SEEN clients are excluded

-   Status badges: 🟢 ONLINE \'Folder will be created at next
    heartbeat\' / ⚫ OFFLINE \'Task queued --- executes on reconnect\'

-   Operator selects one or more clients → \'Queue folder creation\'

-   Real-time status for ONLINE clients (spinner → SUCCESS/ERROR);
    deferred badge for OFFLINE

-   If all eligible clients already have SUCCESS tasks (or no eligible
    clients exist): button disabled with tooltip \'Folder already
    deployed to all available PCs\'

**5. Architectural Proposal --- Stack & System Design**

**5.1 High-Level Architecture**

Browser SPA (React 18 + TypeScript) communicates via HTTPS REST +
WebSocket with a FastAPI backend behind Nginx TLS termination. Celery
workers handle all async image processing. PostgreSQL stores all domain
entities; Redis serves as Celery broker, cache and WebSocket pub/sub.
Object storage (MinIO / S3-compatible) holds all binary files. The
data-service daemon runs on acquisition PCs and communicates exclusively
with the FastAPI backend using the two-step notify→upload protocol
(RF-17, RF-18).

**5.2 Backend --- FastAPI**

FastAPI allows direct reuse of existing Python domain code. The ASGI
runtime provides non-blocking I/O for concurrent file processing.

  ----------------------- -----------------------------------------------
  **Package**             **Role**

  fastapi + uvicorn       ASGI server and HTTP framework

  sqlalchemy (async) +    ORM with async drivers + migrations
  alembic                 

  pydantic v2             Entity schemas and settings management

  celery + redis          Task queue, broker and result backend

  Pillow, numpy, piexif,  Image processing --- reused from legacy
  defusedxml              

  libvips / pyvips        Deep Zoom Image tile generation for large TIFFs

  Jinja2                  Protocol HTML export only (RF-08) --- not used
                          for primary UI rendering

  boto3 / minio-py        Object storage client

  python-jose             JWT token creation and validation (human users
                          and data-service session tokens)

  python-ldap / ldap3     Institutional directory integration

  bcrypt                  API key hashing for DataServiceClient
  ----------------------- -----------------------------------------------

**5.3 Task Queue --- Celery**

The ingestion pipeline runs as a Celery task chain. Each step is a
handler that reads from and writes to a shared PipelineContext. Handlers
are registered independently --- adding support for a new instrument
type requires only a new handler registration, not changes to the
coordinator.

  -------------------------- -------------------------------- --------------
  **Handler / Task**         **Trigger**                      **Priority**

  ReceiveHandler             Data-service POST to /upload     HIGH
                             (after ACCEPT)                   

  FileTypeHandler            After ReceiveHandler             HIGH

  PictureTypeHandler         After FileTypeHandler            HIGH

  MetadataHandler            After PictureTypeHandler;        HIGH
                             dispatches to per-type extractor 

  StorageHandler             After MetadataHandler; moves to  HIGH
                             final object key                 

  DerivativeHandler          After StorageHandler; creates    HIGH
                             ImageDerivative records          

  generate_dzi_tiles         After DerivativeHandler (images  MEDIUM
                             \>10 MP only)                    

  CalibrationHandler         After DerivativeHandler;         MEDIUM
                             resolves CalibrationConfig       

  DatabarHandler             After CalibrationHandler (if     MEDIUM
                             databar_removal=True)            

  SampleTreeHandler          After CalibrationHandler;        MEDIUM
                             creates missing Sample nodes     

  NotifyHandler              After SampleTreeHandler;         MEDIUM
                             WebSocket push                   

  embed_vega_jpeg_metadata   On .hdr sidecar arrival (VEGA    HIGH
                             JPEG only)                       

  reassign_element           User RF-13 action via UI         HIGH

  generate_html_export       User requests RF-08 export ---   LOW
                             on-demand only                   

  process_task_ack           Data-service ACK received via    MEDIUM
                             /task-ack (RF-18)                
  -------------------------- -------------------------------- --------------

**5.4 Frontend --- React SPA**

The React SPA is the primary and only UI. All protocol data is fetched
via REST API and rendered client-side. There is no server-side rendering
of the primary UI.

  ----------------------- -----------------------------------------------
  **Library**             **Role**

  React 18 + TypeScript   Core SPA framework

  TanStack Query          Server state management and cache invalidation

  Zustand                 Local UI state (selected item, panel sizes,
                          etc.)

  React Router v6         Client-side routing

  Tailwind CSS +          Component library
  shadcn/ui               

  OpenSeadragon           Deep-zoom TIFF viewer using DZI tiles

  native WebSocket API    Real-time task progress and status updates
  ----------------------- -----------------------------------------------

**5.5 Data Storage**

> **ARCHITECTURE DECISION:** Object storage (MinIO / S3-compatible) is
> used for all binary assets. This is the correct choice for this
> workload: SEM TIFF files are large (50 MB--2 GB), immutable after
> ingestion, and accessed by key --- the exact profile object storage is
> designed for. Pre-signed URLs allow the browser to download files
> directly without proxying through the backend. Horizontal scalability
> and 11-nine durability come without custom RAID or backup logic. The
> target deployment is MinIO on-premise, not S3 remote --- latency
> assumptions in the ingestion pipeline are based on local network
> access (\<5ms round-trip). If a remote S3 endpoint is used, async
> Celery tasks absorb the added latency without user impact, but
> pre-signed URL generation adds \~50--200ms per request.
>
> **OPERATIONAL NOTE:** DZI tile sets generate hundreds to thousands of
> small objects per image in object storage. A MinIO lifecycle policy
> should be configured to purge orphaned tile sets (e.g. after
> soft-delete expiry at 30 days). For a local MinIO deployment with a
> modest number of protocols (\<10,000), the overhead per object is
> negligible. At very high scale, a dedicated tile CDN may be
> preferable.

**PostgreSQL**

-   All domain entities including DataServiceClient, DataServiceTask,
    FileEvent

-   JSONB for params (MicroscopePicture) and payload (DataServiceTask)

-   Row-Level Security (RLS) policies enforce visibility at the database
    layer

-   Full-text search on project, responsible, description (tsvector
    index)

**Object Storage (MinIO / S3-compatible)**

-   Original TIFF and JPEG uploads; all ImageDerivative files
    (THUMBNAIL, FULLSIZE_PNG, DZI tiles, CROPPED, FRAME_PNG); HTML
    export files; attachments

-   Pre-signed URLs with 15-minute TTL --- browser downloads directly
    from storage, no backend proxy

-   Soft-deleted images retained 30 days before purge (RF-13 remove
    operation)

-   Target deployment: MinIO on-premise on same local network as backend

**Redis**

-   Celery broker and result backend; HTTP session and JWT blacklist
    cache

-   WebSocket pub/sub for real-time events; protocol-level write lock

-   JWT blacklist for revoked data-service session tokens (RF-14, RF-20)

**5.6 API Design Conventions**

-   Base path: /api/v1/

-   Human auth: JWT Bearer (15 min) + refresh tokens (7 days)

-   Data-service auth: API key → session JWT (8h) per RF-15; see §8.1
    for full protocol

-   Async responses: 202 Accepted + { task_id, status_url } for all
    pipeline operations

-   WebSocket: WS /api/v1/ws/protocols/{id} --- real-time events

-   Pagination: cursor-based for all list endpoints

-   Error format: RFC 7807 Problem Details

-   Visibility filtering: SQL RLS --- never post-filtered in application
    code

**6. Non-Functional Requirements**

  --------- --------------- ----------------------------------------------
  **ID**    **Category**    **Requirement**

  NFR-01    Performance     Thumbnail generation for a 50 MB TIFF must
                            complete within 30 seconds

  NFR-02    Performance     API response time for protocol list \< 200ms
                            at p95

  NFR-03    Performance     DZI tile set generation for a 500 MB TIFF must
                            complete within 5 minutes

  NFR-04    Scalability     Celery worker pool scales horizontally;
                            minimum 4 workers for image processing

  NFR-05    File size       Must handle TIFF files up to 2 GB (XL40
                            multiframe)

  NFR-06    Availability    Server unavailability must not prevent
                            data-service from queueing uploads locally
                            (SQLite buffer)

  NFR-07    Data integrity  Calibration must never overwrite original file
                            without explicit CalibrationConfig flag

  NFR-08    Data integrity  Reassignment (RF-14) must be atomic: DB update
                            and object storage move succeed together or
                            both roll back

  NFR-09    Security        RESTRICTED protocol thumbnails must never
                            appear in API responses for unauthorised users

  NFR-10    Security        Object storage URLs must be pre-signed with
                            15-min TTL --- no public permanent URLs

  NFR-11    Security        All access to RESTRICTED resources must be
                            written to the audit log

  NFR-12    Security        Data-service session tokens scoped only to
                            /api/v1/data-service/\* endpoints

  NFR-13    Backwards       .exp config files from legacy expwizard
            compat          importable via POST
                            /api/v1/protocols/import-config

  NFR-14    Browser support Chrome 110+, Firefox 110+, Safari 16+

  NFR-15    Accessibility   WCAG 2.1 AA for all primary user flows

  NFR-16    DS reliability  Crash recovery and automatic reconnect with
                            exponential backoff (no manual intervention
                            required)

  NFR-17    DS OS           Must run on Windows 7+ and Linux with kernel
            compatibility   3.x+

  NFR-18    DS daemon       Installable as Windows Service and Linux
                            systemd unit; launchd on macOS

  NFR-19    DS performance  Filesystem monitoring must not be the
                            bottleneck; heartbeat and file notification
                            latency \< 1 second

  NFR-20    DS distribution Distributed as a single self-contained binary
                            or installer with no external runtime
                            dependencies
  --------- --------------- ----------------------------------------------

**7. Open Questions & Migration Notes**

**7.1 Critical design decisions to resolve**

-   Protocol number sequence: import existing ELOG protocol numbers at
    migration time; start DB sequence above the highest existing value.

-   XL40 stability window: default 5-second stability_window in the
    data-service may be insufficient for very large multiframe TIFFs.
    Confirm maximum expected write duration with operators.

-   Multi-user concurrent annotation: optimistic locking via updated_at
    ETag. Confirm if real-time collaborative editing (two users in same
    protocol simultaneously) is a requirement.

-   VEGA JPEG sidecar timing: confirm maximum expected delay between
    JPEG creation and .hdr sidecar arrival. Determines the data-service
    pairing timeout.

-   AccessPolicy --- group hierarchy: the current model supports a flat
    group (scope_type=GROUP, group_id points to a single unit). A
    hierarchical group tree (department \> section \> lab) would require
    changes to the AuthorizationService and RLS policies but not to the
    AccessPolicy schema --- group_id can point to any entity. Confirm if
    hierarchy is needed before the first production deployment.

-   AccessPolicy --- future scope types: TIMED (embargo_until date),
    CONSORTIUM (inter-unit groups), and DEPARTMENT (parent-group
    traversal) are anticipated future extensions. No schema changes
    required --- new scope_type values can be added and handled in the
    AuthorizationService. Confirm priority and timeline.

-   CalibrationConfig defaults for Multi protocols: confirm whether a
    Multi protocol should inherit calibration settings from a primary
    microscope or require explicit entries for every instrument type.

-   Session token TTL: 8 hours proposed for data-service session tokens.
    Confirm suitability for overnight acquisition sessions.

-   DataServiceTask --- additional operation types:
    FILESYSTEM/CREATE_DIR is the only operation currently defined.
    FILESYSTEM/DELETE_DIR, FILESYSTEM/RENAME_DIR, and a CONFIG category
    for pushing configuration updates are anticipated. New operations
    require no schema changes --- add task_type/operation values and a
    handler in the data-service.

-   HTML export image embedding: confirm whether the standalone .html
    export should embed images as base64 (larger file, fully
    self-contained) or use pre-signed URLs (smaller file, 15-min
    expiry).

**7.2 Modules reusable as-is (strip Qt imports only)**

-   microscope_picture.py --- MicroscopePicture, FEIPicture,
    VegaPicture, XL40Picture, MicroscopePictureFactory

-   autotools.py --- PictureType, FEITagCodes, VegaMetadataParser, all
    formatters

-   file_type_guesser.py --- ElementTypeGuesser, RegexpRepository (zero
    Qt deps)

-   attachment.py --- Attachment, AttachmentFactory, AttachmentType

-   Jinja2 templates (.yammy files) --- repurposed for RF-08 HTML export
    only

**7.3 Modules to rewrite**

-   autowatchdog.py → data-service daemon (Go --- see §8.3 for library
    selection and implementation patterns)

-   autoprotocol.py → strip Qt signals, replace filesystem paths with
    storage keys, remove all ELOG calls

-   sample.py → strip Qt signals, map to SQLAlchemy async model

-   elog_interface.py → deleted entirely; no equivalent

-   autoconfig.py → Pydantic BaseSettings + .env file; QSettings removed

-   expwizard/ → replaced by web wizard flow (RF-12 + RF-22)

-   autogui.py, autologbook_app.py → replaced by React SPA

-   file_system_command.py (FileSystemCommander) → replaced by RF-14
    server-side reassignment service

**8. Data-Service --- Technical Protocol**

This chapter defines the technical implementation of the data-service
daemon, written in Go (see §8.3 for the language decision rationale). It
covers the authentication mechanism, wire protocol, offline behaviour,
and operational requirements. Functional requirements RF-14 through
RF-22 are specified in §2. UI flows (Flow 7, 8, 9) are in §4.

**8.1 Authentication Implementation --- Session Token Pattern**

> **ARCHITECTURE DECISION:** The data-service is a machine client, not a
> human user. Authentication occurs once per connection/reconnect, not
> per message. The pattern follows OAuth2 Client Credentials semantics
> implemented directly in FastAPI --- no external Authorization Server
> required. If an AS is integrated in a future release, the client wire
> protocol (Bearer token) does not change.

**Registration (one-time, admin-initiated)**

  ------------------------------- ----------------------------------------------
  **Step**                        **Detail**

  POST                            Body: { hostname, watch_folder, os_info,
  /api/v1/data-service/register   agent_version }

  Response (one-time)             { client_id, api_key } --- api_key shown in
                                  plain text exactly once; never retrievable
                                  again

  Client storage                  api_key persisted in local config file (OS
                                  keystore on Windows; 0600-permission file on
                                  Linux)

  Server storage                  api_key_hash (bcrypt, cost factor 12); plain
                                  text discarded immediately
  ------------------------------- ----------------------------------------------

**Per-connection authentication flow**

  --------------------------- ----------------------------------------------
  **Step**                    **Detail**

  POST                        Body: { client_id, api_key }
  /api/v1/data-service/auth   

  Backend                     Verifies api_key against api_key_hash; checks
                              is_revoked; emits session_token (JWT RS256, 8h
                              TTL)

  Response                    { session_token, expires_at }

  Subsequent requests         All heartbeats, file-notify, upload, task-ack
                              use: Authorization: Bearer {session_token}

  Token refresh               When session_token expires, client
                              re-authenticates via /auth. No separate
                              refresh endpoint --- the API key is the
                              long-lived credential.

  Revocation                  Admin sets is_revoked=True (RF-21);
                              session_token added to Redis JWT blacklist;
                              client cannot re-authenticate.
  --------------------------- ----------------------------------------------

> **SECURITY:** TLS mandatory on all data-service endpoints. Client must
> verify server certificate. For environments with an internal CA, the
> bundle CA path is configurable in the local config file.

**Session token --- local validation (configurable)**

The session_token is a JWT RS256 --- the data-service can validate it
locally by checking the exp claim, avoiding a server round-trip on every
request. This is an optimisation, not a protocol requirement.

  --------------------------- -------------------------------------------
  **Config flag**             **Behaviour**

  local_token_validation:     data-service verifies exp claim locally;
  true (default)              re-authenticates proactively 5 minutes
                              before expiry; no server round-trip per
                              request

  local_token_validation:     data-service uses the token as an opaque
  false                       string; the server returns 401 on expiry;
                              client re-authenticates on 401. Useful if
                              token format changes in a future release
                              without updating the client.
  --------------------------- -------------------------------------------

All messages after authentication use JSON over HTTPS with
Authorization: Bearer {session_token}. There is no persistent TCP
connection or custom binary protocol.

  ---------------- --------------- ---------------------------------- ----------------
  **Flow**         **Direction**   **Endpoint**                       **Frequency**

  Authentication   Client → Server POST /api/v1/data-service/auth     On connect /
                                                                      reconnect

  Heartbeat        Client → Server POST                               Every 30s
                                   /api/v1/data-service/heartbeat     (configurable)

  Task delivery    Server → Client In heartbeat response body         Piggybacks on
                                                                      heartbeat

  Task ACK         Client → Server POST /api/v1/data-service/task-ack After each task
                                                                      executed

  File notify      Client → Server POST                               On filesystem
                                   /api/v1/data-service/file-notify   event

  File upload      Client → Server POST /api/v1/data-service/upload   Only if ACCEPT
                                                                      received
  ---------------- --------------- ---------------------------------- ----------------

**8.3 Language --- Go (Confirmed)**

**Requirements driving the decision (NFR-16 to NFR-20)**

  ---------- --------------------------------------------- ---------------
  **NFR**    **Requirement**                               **Weight**

  NFR-16     Crash recovery and automatic reconnect (no    HIGH
             manual intervention)                          

  NFR-17     Windows 7+ and Linux kernel 3.x+              HIGH
             compatibility                                 

  NFR-18     Windows Service / systemd / launchd daemon    HIGH

  NFR-19     Filesystem monitoring not the bottleneck;     MEDIUM
             latency \< 1s                                 

  NFR-20     Single self-contained binary; no external     MEDIUM
             runtime dependencies                          
  ---------- --------------------------------------------- ---------------

**Comparison matrix**

  --------------------- ------------- ---------------------------- -----------------------
  **Criterion**         **Python**    **Go**                       **Rust / C++**

  Windows 7+            ✓ Python 3.8  ✓ static binary, no runtime  ✓ / complex toolchain
  compatibility         (EOL but                                   
                        functional)                                

  Linux legacy kernel   ✓             ✓ (kernel 2.6.23+)           ⚠ MUSL recommended / ✓

  Windows Service       ⚠ via pywin32 ✓ native                     ⚠ crates available / ✓
                        (fragile)     (golang.org/x/sys/windows)   native

  Linux systemd daemon  ✓ via unit    ✓                            ✓
                        file                                       

  Crash recovery /      ⚠ requires    ✓ goroutine + context cancel ✓ / ✓
  reconnect             explicit      idiom                        
                        design                                     

  Filesystem monitoring ⚠ watchdog    ✓                            ✓
                        lib;                                       
                        sufficient                                 
                        for SEM                                    

  Memory footprint      ✗ 60--150 MB  ✓ 10--20 MB                  ✓ \<10 MB
                        with                                       
                        interpreter                                

  Distribution          ⚠ PyInstaller ✓ single binary \<15 MB      ✓ \<10 MB / ✗ MSVC deps
                        \>50 MB; AV                                
                        false pos.                                 

  Maintainability       ✓ team knows  ✓ simple syntax              ⚠ steep curve / ✗
                        Python                                     complex

  Legacy code reuse     ✓ watchdog,   ✗ full rewrite               ✗ full rewrite
                        tenacity,                                  
                        requests                                   

  Time to market        ✓ immediate   ✓ 2--3 week rewrite          ✗ months
  --------------------- ------------- ---------------------------- -----------------------

**Decision**

> **CONFIRMED:** The data-service is implemented in Go. Go satisfies all
> NFR-16 through NFR-20: static binary with no runtime dependencies,
> native Windows Service and systemd support, goroutines for crash
> recovery and automatic reconnect, 10--20 MB footprint, compilation
> targeting Windows 7+ and Linux legacy kernels. The comparison table
> above documents the rationale. Python and Rust/C++ were evaluated and
> rejected.

**Go library selection**

  ---------------- ------------------------------------- ----------------------------------
  **Concern**      **Library**                           **Notes**

  Filesystem       github.com/fsnotify/fsnotify          Cross-platform wrapper over
  monitoring                                             inotify (Linux),
                                                         ReadDirectoryChangesW (Windows),
                                                         kqueue (macOS). Emits
                                                         Create/Write/Remove/Rename/Chmod
                                                         events. Used to detect new files
                                                         in watch_folder.

  HTTP client      net/http (stdlib)                     Standard library client with
                                                         configurable timeout and TLS. No
                                                         external dependency needed for
                                                         basic HTTP/HTTPS.

  Retry with       github.com/avast/retry-go             Exponential backoff with jitter
  backoff                                                for upload retries and reconnect
                                                         loops. Replaces legacy tenacity
                                                         usage.

  Windows Service  golang.org/x/sys/windows/svc          Native Windows Service lifecycle
                                                         (Start, Stop, Pause). Allows
                                                         data-service to run as a proper
                                                         Windows Service without pywin32.

  Linux systemd    github.com/coreos/go-systemd/daemon   Sends sd_notify READY=1 and
  notify                                                 WATCHDOG=1 signals to systemd.
                                                         Enables Type=notify in the unit
                                                         file for clean startup detection.

  SQLite offline   zombiezen.com/go/sqlite               Pure Go SQLite driver (no CGO).
  buffer                                                 Preferred over go-sqlite3
                                                         (requires CGO) to preserve single
                                                         static binary compilation. Stores
                                                         pending file events and upload
                                                         queue.

  TLS / CA config  crypto/tls + crypto/x509 (stdlib)     x509.CertPool loads custom CA PEM
                                                         from ca_cert_path config field.
                                                         Injected into tls.Config.RootCAs
                                                         for the HTTP client.
                                                         InsecureSkipVerify always false.

  JWT verification github.com/golang-jwt/jwt/v5          Parses and verifies the
                                                         session_token received from /auth.
                                                         Client validates expiry (exp
                                                         claim) locally before each request
                                                         to trigger proactive
                                                         re-authentication.

  Configuration    github.com/spf13/viper                Reads config from JSON or TOML
                                                         file (client_id, api_key,
                                                         watch_folder, server_url,
                                                         ca_cert_path, heartbeat_interval,
                                                         stability_window, buffer_path,
                                                         buffer_max_gb). Supports env var
                                                         overrides.
  ---------------- ------------------------------------- ----------------------------------

**Key implementation patterns**

**Authentication and session management**

On startup the data-service reads client_id and api_key from the config
file, calls POST /auth, and stores the session_token in memory. A
background goroutine monitors token expiry (exp claim minus a 5-minute
safety margin) and proactively re-authenticates before expiry. If /auth
fails (network error or 403 revoked), the goroutine retries with
exponential backoff and logs a warning. All other goroutines block on a
sync.RWMutex until a valid token is available.

**Filesystem monitoring and XL40 stability debounce**

fsnotify emits a Create event when a new file appears. For TIFF files
(and all files by default) a stability check is applied before upload: a
timer is started with the configured stability_window (default 5s). On
any subsequent Write event for the same path the timer is reset. When
the timer fires without interruption, the file size is compared to the
size recorded at timer start --- if equal the file is considered stable
and the notify→upload flow is triggered. This correctly handles XL40
multiframe TIFFs where the BSE frame is appended seconds after the SE
frame, firing a Write event that would otherwise cause a partial upload.

  ----------------------- -----------------------------------------------
  **Event**               **Action**

  fsnotify.Create on      Start stability timer (stability_window);
  .tif/.tiff              record file size

  fsnotify.Write before   Reset timer; record new file size
  timer fires             

  Timer fires, size       Proceed: POST /file-notify → if ACCEPT → POST
  stable                  /upload

  fsnotify.Create on .jpg Wait for paired .hdr sidecar (same stem); start
  (VEGA JPEG)             pairing timeout (configurable, default 30s);
                          upload both as multipart if sidecar arrives;
                          upload JPEG alone if timeout expires

  fsnotify.Create on .tmp Ignore (extension exclusion list)
  / .part                 
  ----------------------- -----------------------------------------------

**Reconnect and crash recovery**

The main event loop runs in a goroutine managed by a supervisor
goroutine. If the event loop goroutine panics or returns an error, the
supervisor logs the event and restarts it after a backoff delay
(retry-go with exponential backoff, max 30s). The heartbeat goroutine,
upload worker goroutine, and task executor goroutine are each supervised
independently --- a failure in one does not crash the others. On
reconnection, the SQLite buffer is replayed in FIFO order before new
events are processed.

-   If the server is unreachable, the data-service buffers pending
    uploads to a local SQLite queue

-   On reconnection, queued uploads are replayed in FIFO order

-   Retry uses exponential backoff (default: max_attempts=5, wait
    0.5--30s)

-   Buffer size limit configurable (default 10 GB); operator warned if
    buffer approaches limit

-   The SQLite queue also buffers file-notify events received while
    offline; replayed as notify+upload pairs on reconnection

**8.5 Folder Naming Convention & Protocol Number Extraction**

The relative_path sent by the data-service contains the protocol folder
as its first component. The folder name must include the protocol number
in a format parseable by the backend regex (e.g.
\'2024-0042-project-alpha\' --- backend extracts \'0042\'). The folder
is created by the data-service on receipt of a CREATE_FOLDER task
(RF-19). The local folder structure is otherwise unconstrained --- the
legacy NNN-project-resp naming convention is no longer enforced.

**9. Legacy Migration Reference**

This chapter provides a consolidated reference mapping legacy desktop
application components and ELOG features to their web platform
equivalents. It supplements §7.2 and §7.3.

**9.1 ELOG Feature Mapping**

  ------------------------- ------------------------------- -------------
  **Legacy ELOG feature**   **Web platform equivalent**     **RF**

  ELOG entry per protocol   Protocol record; viewed in      RF-06, RF-10
                            React SPA Protocol Workspace    

  ELOG HTML rendering       RF-08 on-demand HTML export     RF-08
                            only; React SPA is primary UI   

  ELOG Edit Lock            Protocol.status = LOCKED /      RF-06
                            ACTIVE                          

  Analysis Status (On       Protocol.acquisition_status =   RF-20
  going/Done)               ONGOING / COMPLETED (manual)    

  ELOG search               PostgreSQL full-text search on  RF-06
                            Protocol fields                 

  Write URL file            Each protocol has a permanent   RF-06
                            shareable URL                   

  elog_post_splitter        Not needed --- React SPA        ---
                            paginates natively              

  ListLogbook               Protocol Dashboard with filters RF-06
                            (Flow 2)                        

  AnalysisLogbook per       Protocol filtered by            RF-06
  microscope                microscope_type                 
  ------------------------- ------------------------------- -------------

**9.2 Desktop Component Mapping**

  ------------------------ ----------------- -----------------------------------
  **Legacy module**        **Disposition**   **Web equivalent**

  microscope_picture.py    Reuse --- strip   Server-side domain entity + Celery
                           Qt imports        tasks

  autotools.py             Reuse --- strip   Utility library for metadata
                           Qt imports        parsing

  file_type_guesser.py     Reuse --- zero Qt RF-01 Step 2
                           deps              

  attachment.py            Reuse --- strip   Attachment entity
                           Qt imports        

  Jinja2 templates         Reuse --- scope   RF-08 HTML export
  (.yammy)                 to export only    

  autowatchdog.py          Rewrite           data-service daemon (Go or Python)

  autoprotocol.py          Rewrite           Protocol entity + Celery tasks

  sample.py                Rewrite           SQLAlchemy async Sample model

  elog_interface.py        Delete            No equivalent --- ELOG replaced
                                             entirely

  autoconfig.py            Rewrite           Pydantic BaseSettings + .env

  expwizard/               Replace           New Experiment Wizard (Flow 1,
                                             RF-12, RF-22)

  autogui.py /             Replace           React SPA
  autologbook_app.py                         

  protocol_editor.py       Replace           Protocol Workspace Edit Panel (Flow
                                             3)

  file_system_command.py   Replace           RF-14 server-side reassignment
                                             service
  ------------------------ ----------------- -----------------------------------

**10. Security & Compliance**

This chapter defines the security requirements, controls and operational
procedures applicable to the autologbook platform. The deployment
context is a university research laboratory: acquisition PCs are
standalone, not managed by central IT, and often run legacy operating
systems. There are no formal certification requirements (ISO 27001,
IT-Grundschutz audit) and no mandatory data retention periods. The
controls defined here are proportionate to the actual risk profile of
this environment.

**10.1 Threat Model**

A realistic threat model for this deployment focuses on insider risk and
opportunistic access, not sophisticated external attackers. The system
is not internet-facing by default --- it runs on an institutional
intranet.

  ------------------ ---------------- ------------------- --------------------------------
  **Threat**         **Likelihood**   **Impact**          **Primary control**

  Operator reads     MEDIUM --- PCs   HIGH --- attacker   API key stored in OS keystore
  another            are physically   can impersonate the (§10.2); revocation procedure
  operator\'s API    shared in open   PC and inject files (§10.2)
  key from           labs             into any ONGOING    
  acquisition PC                      protocol            
  filesystem                                              

  PC lost, stolen or LOW--MEDIUM ---  HIGH --- same as    OS keystore encryption (§10.2);
  decommissioned     lab hardware is  above               immediate revocation on incident
  with API key on    occasionally                         (§10.2)
  disk               misplaced or                         
                     repurposed                           

  Operator accesses  LOW --- requires HIGH ---            RLS at DB layer (§3.6); audit
  a RESTRICTED       exploiting an    confidential        log (§10.3)
  protocol they are  application bug  research data       
  not authorised for or DB access     exposed             

  Unauthorised       LOW --- requires MEDIUM --- tampered Append-only audit table; no
  modification of    SYSTEM_ADMIN     logs reduce         DELETE/UPDATE permission for any
  audit logs         compromise or    incident response   app role (§10.3)
                     direct DB access capability          

  Data loss due to   LOW --- hardware VERY HIGH --- SEM   Daily backup with 30-day
  server failure     failure is       data is             retention (§10.4)
  (PostgreSQL or     infrequent but   non-reproducible;   
  MinIO)             non-zero         sample may be       
                                      destroyed           
                                      post-acquisition    

  Malicious or       LOW --- requires MEDIUM --- file     File type validation in pipeline
  corrupted file     valid session    enters ingestion    (RF-01 step 2--3); defusedxml
  injected via       token            pipeline;           for XML parsing
  data-service                        Pillow/defusedxml   
                                      parse it            

  Outdated           LOW--MEDIUM ---  MEDIUM --- depends  Version reporting at heartbeat;
  data-service       Windows 7 PCs    on vulnerability    admin alert on outdated agents
  binary with known  rarely updated   class               (§10.5)
  vulnerability                                           
  ------------------ ---------------- ------------------- --------------------------------

> **SCOPE:** This threat model explicitly excludes: nation-state
> attackers, ransomware targeting the server infrastructure, and
> supply-chain attacks on Go dependencies. These threats exist but are
> out of scope for a laboratory-scale deployment without dedicated
> security operations.

**10.2 Credential & Secret Management**

**API key storage on acquisition PCs --- mandatory requirements**

The API key is the long-lived credential that authenticates a
data-service instance to the backend. Its compromise allows an attacker
to impersonate the PC indefinitely until the key is revoked. Storage in
a plaintext file is explicitly prohibited.

  -------------- ----------------------- -------------------------------------
  **Platform**   **Required storage      **Implementation in Go**
                 mechanism**             

  Windows 7+     Windows Credential      github.com/danieljoos/wincred ---
                 Manager                 CredWrite / CredRead API; key stored
                 (DPAPI-encrypted, user  under target name
                 or system scope)        \'autologbook-data-service\'

  Linux          Secret Service API      github.com/zalando/go-keyring ---
                 (libsecret) or, if      falls back to file-based storage with
                 unavailable, file with  explicit chmod; service user must not
                 0600 permissions owned  be root
                 by the service user in  
                 /etc/autologbook/       

  macOS          macOS Keychain via      github.com/zalando/go-keyring ---
                 Security framework      native Keychain integration
  -------------- ----------------------- -------------------------------------

> **CRITICAL:** Storing the API key in a plaintext config file (e.g.
> config.json, .env) is prohibited in production deployments. The
> data-service installer must write the API key directly to the OS
> keystore at registration time and delete any intermediate plaintext
> copy. The only moment the key exists in plaintext is in the HTTP
> response body of POST /register --- which is encrypted in transit by
> TLS.

**Memory hygiene**

-   After POST /auth succeeds, the API key is no longer needed in memory
    --- it must be zeroed (Go: use a \[\]byte and call
    runtime.MemclrNoHeapPointers or simply overwrite with zeros before
    GC)

-   Only the session_token is retained in memory for subsequent requests

-   The session_token must never be written to any log file or persisted
    to disk

-   On process exit (Windows Service stop / systemd stop), the
    session_token is discarded --- no persistence needed since
    re-authentication on startup is fast (\<1s on local network)

**Revocation procedure**

If a PC is lost, stolen, decommissioned, or an operator suspects key
compromise, the following procedure must be executed immediately:

  ---------- ------------------------------ ------------------------------------
  **Step**   **Action**                     **Where**

  1          Navigate to Settings \> Data   Web UI --- Flow 7
             Services in the admin panel    

  2          Locate the client by hostname  Admin Panel table
             or display_name                

  3          Click \'Revoke API key\' →     Admin Panel --- RF-20
             confirm modal                  

  4          Backend sets is_revoked=True   Automatic --- RF-20
             and invalidates active         
             session_token via Redis        
             blacklist                      

  5          Verify client status changes   Admin Panel status badge
             to OFFLINE within one          
             heartbeat interval             

  6          If PC is recovered: run        CLI on acquisition PC
             data-service re-registration   
             to obtain a new API key        

  7          If PC is not recovered: remove Admin Panel --- Delete action
             the client record from the     
             admin panel after revocation   
  ---------- ------------------------------ ------------------------------------

**Backend secret management**

-   JWT signing key (RS256 private key): generated at deployment, stored
    as an environment variable or mounted secret --- never committed to
    version control

-   Database credentials: stored in environment variables, injected via
    .env file (excluded from git) or a secrets manager (Vault, Docker
    secrets)

-   MinIO credentials: same pattern as DB credentials

-   bcrypt cost factor for API key hashing: 12 (default) --- reviewed if
    hardware changes significantly

**10.3 Audit Logging**

**Events logged**

  ---------------- ------------------------ ------------------------------
  **Event          **Specific events        **Fields recorded**
  category**       logged**                 

  Authentication   Successful login (human  timestamp, user_id or
                   users); failed login     client_id, ip_address,
                   attempts; data-service   outcome, failure_reason
                   /auth success and        
                   failure; API key         
                   revocation               

  RESTRICTED       Any GET/LIST on a        timestamp, user_id,
  access           RESTRICTED protocol or   protocol_id, endpoint,
                   sample by any user       ip_address

  Protocol         status changes           timestamp, user_id,
  mutations        (LOCKED/UNLOCKED);       protocol_id, old_value,
                   acquisition_status       new_value
                   changes; visibility      
                   changes                  

  Reassignment     Image or sample          timestamp, user_id,
  (RF-13)          move/rename/delete;      element_id, old_path,
                   protocol delete          new_path, operation

  Admin actions    DataServiceClient        timestamp, admin_id,
                   revoke, delete, rename;  target_id, action
                   user role changes        

  Data-service     File ACCEPT/IGNORE       timestamp, client_id,
  events           decisions; CREATE_FOLDER file_event_id or task_id,
                   task SUCCESS/ERROR       decision, reason
  ---------------- ------------------------ ------------------------------

**Retention and access**

  --------------------- -------------------------------------------------
  **Parameter**         **Specification**

  Retention period      12 months --- sufficient for security incident
                        investigation without accumulating unnecessary
                        personal data

  Storage               Dedicated audit_log table in PostgreSQL ---
                        separate from application tables

  Write access          INSERT only --- granted to the application
                        service account via a dedicated DB role

  Read access           SYSTEM_ADMIN only via GET /api/v1/admin/audit-log
                        (paginated, filterable by date, user, event type)

  Modification /        No DELETE or UPDATE permission granted to any
  deletion              application role --- not even SYSTEM_ADMIN via
                        the application. Direct DB admin access required
                        for purge after retention expiry.

  Purge                 Automated job purges records older than 12
                        months; runs nightly; logs own execution to a
                        separate admin log

  Export                SYSTEM_ADMIN can export audit log as CSV for a
                        given date range via the admin panel
  --------------------- -------------------------------------------------

> **GDPR:** Audit log records contain user_id and ip_address ---
> personal data under GDPR. The 12-month retention is justified as
> legitimate interest for IT security purposes. See §10.6 for GDPR
> details.

**10.4 Backup & Recovery**

SEM image data is non-reproducible: the physical sample may be
destroyed, modified or consumed during or after acquisition. A single
day\'s acquisition session can represent weeks of preparation. The
backup strategy must reflect this.

  --------------------------- -------------------------------------------
  **Parameter**               **Target**

  RPO (Recovery Point         24 hours --- maximum acceptable data loss
  Objective)                  is one day\'s acquisitions

  RTO (Recovery Time          4 hours --- maximum acceptable downtime for
  Objective)                  manual restoration from backup
  --------------------------- -------------------------------------------

**PostgreSQL backup**

  ------------------ ----------------------------------------------------
  **Aspect**         **Specification**

  Method             pg_dump (logical backup) or pg_basebackup (physical)
                     --- both acceptable for this scale

  Frequency          Daily --- scheduled nightly (e.g. 02:00 local time)

  Retention          30 days of daily backups

  Storage            Backup files written to a separate volume or NAS ---
                     not the same disk as the database

  Verification       Weekly automated restore test to a temporary
                     instance; alert on failure

  Encryption         Backup files encrypted at rest (AES-256) if stored
                     on shared infrastructure
  ------------------ ----------------------------------------------------

**MinIO backup**

  ------------------ ----------------------------------------------------
  **Aspect**         **Specification**

  Method             mc mirror (MinIO client) to a secondary bucket or
                     NAS path; alternatively MinIO server-side
                     replication if two MinIO instances are available

  Frequency          Daily incremental mirror --- only changed/new
                     objects are transferred

  Retention          Mirror retains objects for 30 days after deletion
                     from primary (lifecycle rule on mirror target)

  Storage            Mirror target on separate physical storage from
                     primary MinIO

  Verification       Weekly: sample 5 random objects from primary; verify
                     checksum matches mirror copy
  ------------------ ----------------------------------------------------

**Recovery procedure (outline)**

-   PostgreSQL: restore latest pg_dump to a fresh PostgreSQL instance;
    update connection strings in FastAPI .env; restart backend

-   MinIO: if primary volume is lost, promote mirror to primary (update
    MINIO_VOLUMES in config); pre-signed URLs in DB will be stale --- a
    migration task regenerates them on first access

-   Full disaster recovery (both DB and storage lost): restore DB from
    backup, then re-sync storage from mirror; estimated time within RTO
    of 4h for a typical deployment

> **NOTE:** If only the server is lost but storage volumes survive (e.g.
> hardware failure with intact disks), recovery time is significantly
> shorter --- typically under 1 hour to bring up a new server instance
> connected to existing volumes.

**10.5 Patch & Update Management**

**Server-side components**

-   FastAPI backend, PostgreSQL, Redis, MinIO: managed via standard OS
    package manager or Docker image updates; follow upstream security
    advisories

-   Python dependencies: pip-audit run monthly in CI; critical
    vulnerabilities patched within 7 days

-   Go backend libraries (if any): govulncheck run monthly; critical
    vulnerabilities patched within 7 days

**Data-service binary on acquisition PCs**

Acquisition PCs (Windows 7, potentially air-gapped or unmanaged) cannot
rely on automated update mechanisms. The following manual update
procedure applies:

  -------------- ---------------------------------------------------------
  **Step**       **Action**

  Detection      SYSTEM_ADMIN monitors agent_version column in the Admin
                 Panel (Flow 7). A version banner alerts when any client
                 is running a version older than the current release by
                 more than one minor version.

  Distribution   New binary is published as a single .exe (Windows) or
                 binary (Linux) on an internal file share or the lab\'s
                 intranet. No installer required --- the binary is
                 self-contained.

  Update         Operator on the acquisition PC: stop the Windows Service
                 (sc stop autologbook-agent), replace the binary, start
                 the service (sc start autologbook-agent). Estimated time:
                 2 minutes.

  Verification   Admin panel shows updated agent_version at next heartbeat
                 (\~30s). No reconfiguration or re-registration needed ---
                 config file and OS keystore credentials are unchanged.

  Legacy OS      Windows 7 receives no OS security updates. The Go binary
                 statically links all dependencies and does not rely on
                 OS-level TLS libraries (uses Go\'s crypto/tls). Risk from
                 OS-level vulnerabilities is acknowledged and accepted for
                 this deployment context.
  -------------- ---------------------------------------------------------

**Go dependency vulnerability management**

-   govulncheck is run against the data-service module on every release
    build

-   Critical CVEs in direct dependencies trigger an out-of-band patch
    release

-   The static binary eliminates runtime dependency on OS libraries ---
    the attack surface is limited to the Go standard library and
    declared module dependencies

**10.6 GDPR --- Minimal Compliance**

The platform processes a limited set of personal data. There are no
special category data (no health data, no biometric data). The
deployment is on-premise within the EU. No data is transferred to third
countries.

  ------------------ ------------------------------ ---------------- -----------------------
  **Data category**  **Where stored**               **Legal basis**  **Retention**

  User accounts      PostgreSQL users table         Legitimate       Duration of
  (name, email,                                     interest ---     employment + 6 months
  institutional ID)                                 necessary to     
                                                    operate access   
                                                    control          

  Operator name on   PostgreSQL protocols table     Legitimate       Duration of data
  protocols                                         interest ---     retention policy
  (responsible                                      scientific       (institution-defined;
  field)                                            record-keeping   no mandatory period
                                                                     applies here ---
                                                                     recommended minimum 5
                                                                     years for research
                                                                     data)

  Audit log          PostgreSQL audit_log table     Legitimate       12 months (§10.3)
  (user_id,                                         interest --- IT  
  ip_address,                                       security         
  timestamps)                                                        

  Data-service       PostgreSQL                     Legitimate       Duration of client
  client IP address  DataServiceClient.ip_address   interest --- IT  registration; deleted
                                                    security         on client removal
  ------------------ ------------------------------ ---------------- -----------------------

**Data subject rights**

-   Right of access: SYSTEM_ADMIN can export all personal data
    associated with a user account on request

-   Right to erasure: user accounts can be deleted; operator names on
    protocols are replaced with \'\[Deleted User\]\' to preserve
    scientific record integrity; audit log entries are retained for the
    full 12-month period even after account deletion (legitimate
    interest override)

-   Right to rectification: username and email editable by SYSTEM_ADMIN

**No data transfers outside EU**

-   MinIO runs on-premise --- no data leaves the institution

-   No third-party analytics, telemetry or cloud services are used by
    the platform

-   If a cloud MinIO / S3 endpoint is configured in future, a GDPR
    transfer impact assessment is required before activation
