**autologbook**

**Web Platform**

Software Requirements Specification & Architecture Document

**Version 2.9 --- Draft**

2026-04-15

  --------------------- -------------------------------------------------
  **Property**          **Value**

  Status                Draft

  Source                autologbook v0.1.8 (reverse-engineered)

  Changes vs v2.8       SEC-1: registration_secret added to POST
                        /register payload (RF-14, §8.1) --- prevents
                        unauthorised client registration. SEC-2:
                        REGISTRATION_SECRET env var documented in §10.2
                        backend secret management. DM-1: §1.14
                        ProjectContact --- documented informative vs
                        access-granting modalities; user_id=null contacts
                        are display-only, non-null confers RESPONSIBLE
                        access; "Invite to system" UI flow added. AC-1:
                        §3.5 --- clarified that RESPONSIBLE access
                        propagation requires user_id non-null;
                        informative contacts (user_id=null) confer no
                        access. SEC-3: STRIDE per-component analysis
                        applied --- resolved ambiguities in context_id
                        (HMAC-SHA256, §2.16), FileEvent.sha256 field
                        added (§1.11), Redis requirepass + network
                        isolation mandated (§5.5), MinIO network
                        isolation mandated (§5.5), PostgreSQL connection
                        isolation specified (NFR-24), backup encryption
                        made unconditional (§11.4), JWT signing key
                        rotation and emergency procedure documented
                        (§11.2), refresh tokens server-side with
                        immediate revocation on user disable (§5.6), JWT
                        stored in httpOnly cookie (§5.6), auto-update
                        signature algorithm specified as Ed25519 (RF-24),
                        Celery task hard timeout added (NFR-21), rate
                        limiting specified (NFR-22), CSP and output
                        sanitisation requirements added (NFR-23), threat
                        model expanded with three new high-impact threats
                        (§11.1). SEC-4 (v2.10): §11.1 updated with DFD
                        references and attack-vector specificity; §11.2
                        Ed25519 signing key custody (HSM/vault, CI/CD
                        isolation, rotation, logging) documented; §11.3
                        HMAC log chaining and Verification Package for
                        external chain-of-custody added; RFC 3161 TSA
                        optional integration added to §11.3 and
                        FileEvent; NFR-23 expanded with concrete CSP
                        header policy, extra_info plain-text enforcement,
                        and additional security response headers; §11.5
                        Windows 7 Minimum Viable Hardening checklist
                        added (services to disable, DPAPI user-scope
                        keystore, firewall egress rules, user account
                        restrictions, residual risk acknowledgement);
                        §11.7 Security Design Rationale (new section):
                        four Level-1 DFDs, threat-to-control mapping
                        table with literature references, four design
                        decisions with explicit tradeoffs documented.
  --------------------- -------------------------------------------------

########## 1. Domain Model --- Core Entities

Core business entities derived from reverse-engineering autologbook
v0.1.8. Qt-specific references omitted. All entities are expressed as
data structures independent of any UI or transport layer.

v2.8 changes: Operator entity added (§1.13); ProjectContact entity added
(§1.14); ProtocolItem mixin introduced --- all annotatable entities
inherit caption, description, extra_info (JSONB) from it;
yaml_customization removed from Protocol; NavigationImage Quattro-only
constraint removed; AccessPolicy introduced (v2.7, §1.12).

#################### 1.0 ProtocolItem (mixin, new in v2.8)

A shared annotation mixin inherited by all entities that carry
user-supplied descriptions. Eliminates the previous duplication of
caption/description/extra_info across MicroscopePicture, Attachment,
OpticalImage, Video and NavigationImage. extra_info is now JSONB (was
string) to support structured key-value annotations.

  ------------------ ----------------------------------------------------
  **Field**          **Type / Description**

  caption            string --- Short user-supplied label

  description        string --- Free-text description

  extra_info         JSONB --- Structured key-value pairs for arbitrary
                     annotations, e.g. {\"sample_preparation\":
                     \"sputtering 5nm Au\"}. Replaces the legacy string
                     extra_info field.
  ------------------ ----------------------------------------------------

> **NOTE:** All entities listed as inheriting ProtocolItem carry these
> three fields directly on their DB record. There is no separate
> annotation table. A PATCH on any of these fields updates the record
> and invalidates the html_export_cache on the parent Protocol. PATCH on
> caption and description is permitted for: the protocol owner, users
> with role OPERATOR or MANAGER, and CUSTOMER contacts whose linked
> account has edit access. READER and RESPONSIBLE roles cannot PATCH
> these fields.

#################### 1.1 MicroscopePicture

The central domain object. Detection always runs server-side immediately
after file receipt. Inherits ProtocolItem (§1.0).

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

  embedding               List\[float\] / null --- Vector embedding for
                          similarity search; populated by
                          EmbeddingHandler (§2.1 level 4); null until
                          computed

  has_metadata            bool --- False for VEGA JPEG before .hdr
                          sidecar arrives

  calibration_config      CalibrationConfig --- Per-image calibration
                          settings (§1.7)

  processing_status       enum --- PENDING / PROCESSING / DONE / ERROR

  created_at / updated_at datetime

  --- ProtocolItem fields caption, description, extra_info (JSONB) ---
  ---                     inherited
  ----------------------- -----------------------------------------------

############################## ImageDerivative sub-entity

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

############################## PictureType enum --- detection order is critical

  ----------------------------------------------- ---------------- --------------
  **Value**                                       **Instrument**   **Detection
                                                                   key**

  QUATTRO_MICROSCOPE_PICTURE                      FEI Quattro S    FEI tag 34680
                                                                   (FEI_SFEG) +
                                                                   filename regex

  VERSA_MICROSCOPE_PICTURE                        FEI Versa 3D     FEI tag
                                                                   34680 +
                                                                   filename regex

  FEI_MICROSCOPE_PICTURE                          Generic FEI      FEI tag 34680
                                                                   or 34682, no
                                                                   filename match

  VEGA_MICROSCOPE_PICTURE                         TESCAN Vega TIFF Proprietary
                                                                   TIFF tag 50431

  VEGA_JPEG_MICROSCOPE_PICTURE                    TESCAN Vega JPEG JPEG + piexif
                                                                   MakerNote or
                                                                   .hdr sidecar

  XL40_MICROSCOPE_PICTURE                         Philips XL40     XMPMETA XML in
                                                                   TIFF IFD,
                                                                   single frame

  XL40_MULTIFRAME_MICROSCOPE_PICTURE              Philips XL40     XMPMETA +
                                                                   multi-page
                                                                   TIFF (SE +
                                                                   BSE)

  XL40_MULTIFRAME_WITH_STAGE_MICROSCOPE_PICTURE   Philips XL40     Multi-page +
                                                                   stage XMP

  XL40_WITH_STAGE_MICROSCOPE_PICTURE              Philips XL40     Single frame +
                                                                   stage XMP

  GENERIC_MICROSCOPE_PICTURE                      Unknown          Fallback ---
                                                                   always True,
                                                                   registered
                                                                   last
  ----------------------------------------------- ---------------- --------------

#################### 1.2 Sample

Hierarchical container. Hierarchy is derived exclusively from the
sample_path field sent by the data-service.

  -------------------------- --------------------------------------------
  **Field**                  **Type / Description**

  id                         UUID

  protocol_id                UUID --- Parent protocol

  full_name                  string --- Hierarchical path, e.g.
                             SampleA/SubB/SubC

  last_name                  string --- Leaf node name only

  parent_id                  UUID / null --- null = top-level sample

  microscope_pictures /      Lists --- Recursive; access rules propagate
  videos / optical_images /  down
  attachments / subsamples   

  access_policy_id           UUID --- FK to AccessPolicy; inherits from
                             Protocol; overrideable at sample level
  -------------------------- --------------------------------------------

#################### 1.3 Protocol

Root document for a complete SEM analysis session. The Protocol IS the
logbook entry.

> **KEY CHANGE v2.3:** v2.8: responsible (string) replaced by
> operator_id (FK → Operator, §1.13). project/customer strings replaced
> by contacts: List\[ProjectContact\] (§1.14). yaml_customization
> removed --- annotations now live on ProtocolItem fields. v2.7:
> visibility replaced by access_policy_id (§1.12).

  ----------------------- -----------------------------------------------
  **Field**               **Type / Description**

  id                      UUID

  protocol_number         int --- Unique numeric ID, application-managed
                          sequence

  project                 string --- Project name (short label; detailed
                          contacts in contacts list)

  operator_id             UUID --- FK to Operator (§1.13); pre-populated
                          from authenticated user on creation

  contacts                List\[ProjectContact\] --- Project-level
                          contacts: responsible, customer, other roles
                          (§1.14)

  microscope_type         enum --- Quattro / Versa / Vega / XL40 / Multi

  introduction /          text --- Included in PDF/HTML export only if
  conclusion              non-empty

  samples                 List\[Sample\] --- Ordered, hierarchical

  optical_images /        Lists --- Protocol-level
  attachments /           
  navigation_images       

  status                  enum --- DRAFT / ACTIVE / LOCKED --- controls
                          edit authorisation

  acquisition_status      enum --- ONGOING / COMPLETED --- manual-only
                          transition

  access_policy_id        UUID --- FK to AccessPolicy (§1.12)

  owner_id                UUID --- User who created the protocol

  unit_id                 UUID --- Pre-populates group_id in AccessPolicy
                          on creation; not normative for access checks

  html_export_cache       text --- Last generated PDF/HTML export blob;
                          not used for UI rendering

  html_exported_at        datetime

  created_at / updated_at datetime
  ----------------------- -----------------------------------------------

#################### 1.4 Attachment

Inherits ProtocolItem (§1.0).

  ----------------------- -----------------------------------------------
  **Field**               **Type / Description**

  id                      UUID

  protocol_id / sample_id UUID --- Owner (project-level or sample-level)

  storage_key /           Object-storage path, filename, bytes
  original_filename /     
  file_size               

  attachment_type         enum --- GENERIC / UPLOAD

  --- ProtocolItem fields caption, description, extra_info (JSONB) ---
  ---                     inherited
  ----------------------- -----------------------------------------------

#################### 1.5 OpticalImage / NavigationImage / Video

Lightweight entities, all inheriting ProtocolItem (§1.0).
OpticalImageType: GENERIC / KEYENCE / DIGITAL_CAMERA /
DIGITAL_CAMERA_WITH_GPS.

> **v2.8 CHANGE:** NavigationImage was Quattro-only in autologbook v1
> for legacy reasons. In v2.8 this constraint is removed ---
> NavigationImage is available for all microscope types.

#################### 1.6 ExperimentConfiguration

Replaces the legacy .exp / .ini file. Persisted in the database,
downloadable as JSON for data-service configuration.

> **KEY CHANGE v2.3:** v2.8: operator (string) replaced by operator_id
> (FK → Operator, §1.13). v2.4: idle_timeout_minutes,
> remote_storage_bucket and mirroring_enabled removed.

  ----------------------- -----------------------------------------------
  **Field**               **Type / Description**

  id                      UUID

  protocol_id             UUID --- FK to Protocol

  microscope_type         enum

  watch_folder            string --- Path on acquisition PC (data-service
                          only; not used server-side)

  thumbnail_max_width     int --- Default 400px

  operator_id             UUID --- FK to Operator (§1.13)
  ----------------------- -----------------------------------------------

> **NOTE:** The local watch_folder is stored for documentation only. The
> server never uses it. Sample hierarchy is derived entirely from the
> sample_path field the data-service sends per file.

#################### 1.7 CalibrationConfig

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

#################### 1.8 DataServiceClient (new in v2.2)

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

#################### 1.10 DataServiceTask (new in v2.2, updated v2.7)

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

#################### 1.11 FileEvent (new in v2.2, updated v2.7)

Persisted audit record of every filesystem notification received from a
data-service client. In v2.7 the context_id field replaces the raw
protocol_id/sample_path in the upload request --- the data-service uses
it as an opaque token.

  --------------------- -------------------------------------------------
  **Field**             **Type / Description**

  id                    UUID

  context_id            string --- HMAC-SHA256-protected opaque token
                        returned to the data-service in the ACCEPT
                        response; encodes protocol_id and sample_path
                        server-side; never exposed to the data-service in
                        decoded form; rejected by the backend if MAC
                        verification fails

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

  sha256                string / null --- Hex-encoded SHA-256 of the
                        received file bytes, computed server-side by
                        ReceiveHandler before writing to object storage;
                        null until upload completes. Used to detect
                        post-ingestion tampering of files in object
                        storage.
  --------------------- -------------------------------------------------

#################### 1.12 AccessPolicy (new in v2.7)

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

#################### 1.13 Operator (new in v2.8)

Represents the person who physically performed the acquisition. Distinct
from the User entity (which handles authentication). An Operator may or
may not have a system account --- this supports visiting researchers,
external collaborators, and technicians who do not have login
credentials.

  --------------------- -------------------------------------------------
  **Field**             **Type / Description**

  id                    UUID

  display_name          string --- Full name as shown in protocol headers
                        and exports

  affiliation           string / null --- Institution or department

  email                 string / null --- Contact email (not used for
                        authentication)

  user_id               UUID / null --- FK to User; null if the operator
                        has no system account. When set, the operator
                        record is auto-created on first login and
                        display_name is pre-populated from the user\'s
                        directory entry.

  is_active             bool --- Inactive operators are hidden from
                        creation dropdowns but retained on historical
                        protocols

  created_at            datetime
  --------------------- -------------------------------------------------

> **NOTE:** When an authenticated user creates a protocol, operator_id
> is pre-populated by looking up the Operator record linked to their
> user_id. If no linked Operator exists, one is created automatically.
> The operator can be changed manually before locking the protocol.

#################### 1.14 ProjectContact (new in v2.8)

A global registry of people who appear on protocols in roles other than
operator --- typically the responsible scientist and the customer or
sponsor. Reusable across protocols; a recurring customer is entered once
and selected from a dropdown. An Operator and a ProjectContact can refer
to the same physical person but are separate records with different
roles.

  --------------------- -------------------------------------------------
  **Field**             **Type / Description**

  id                    UUID

  display_name          string --- Full name

  affiliation           string / null --- Institution, company, or
                        department

  email                 string / null

  role                  enum --- RESPONSIBLE / CUSTOMER / OTHER

  notes                 string / null --- Free text (e.g. project
                        reference, PO number)

  user_id               UUID / null --- FK to User; if set, grants access
                        to protocols where this contact appears as
                        RESPONSIBLE (see §3.5)

  is_active             bool --- Inactive contacts hidden from dropdowns
                        but retained on historical protocols

  created_at            datetime
  --------------------- -------------------------------------------------

> **NOTE:** Protocol.contacts is a many-to-many join between Protocol
> and ProjectContact. A protocol can have multiple contacts of different
> roles. The same ProjectContact can appear on many protocols. A
> protocol typically has one RESPONSIBLE contact (internal) and one
> CUSTOMER contact, but this is not enforced. CRUD for ProjectContact is
> managed from a dedicated settings page. A ProjectContact operates in
> one of two modes: (1) Informative --- user_id is null; the contact's
> name appears in the protocol header and PDF/HTML export but confers no
> system access; this is the default for external contacts who do not
> need to interact with the platform. (2) With access --- user_id is
> non-null (linked to a local or LDAP account); grants the contact read
> access and comment rights on all protocols where they appear as
> RESPONSIBLE (see §3.5). The UI makes this distinction explicit: when
> adding a RESPONSIBLE contact, the admin can see whether the contact
> has a linked account. If not, an "Invite to system" button initiates
> account creation (local account with a temporary password) and sends
> an email invitation with an activation link. On first login the system
> automatically links the new User record to the existing ProjectContact
> via matching email address.

#################### 1.15 UnitMembership (new in v2.8)

Formalises the relationship between a user and a unit with an explicit
per-unit role. Replaces the implicit unit_id field and the global
UNIT_MANAGER role. A user can be MANAGER in one unit and READER in
another.

  ------------------ ----------------------------------------------------
  **Field**          **Type / Description**

  user_id            UUID --- FK to User

  unit_id            UUID --- FK to Unit

  role               enum --- MANAGER / OPERATOR / READER

  granted_by         UUID --- FK to User (the MANAGER or SYSTEM_ADMIN who
                     granted this membership)

  created_at         datetime
  ------------------ ----------------------------------------------------

#################### 1.16 UnitPolicy (new in v2.8)

Defines configurable permissions for each role within a unit. Each unit
has one UnitPolicy. A system-level DefaultUnitPolicy provides baseline
values; unit-level overrides take precedence. SYSTEM_ADMIN manages all
UnitPolicies; a unit MANAGER manages only their own unit\'s policy.

  -------------------------------- ----------------------------------------------
  **Field**                        **Type / Description**

  unit_id                          UUID / null --- FK to Unit; null =
                                   DefaultUnitPolicy (system-wide baseline)

  operator_can_delete_protocol     bool --- default false

  operator_can_move_protocol       bool --- default false

  operator_can_lock_protocol       bool --- default true

  operator_can_change_visibility   bool --- default true

  operator_can_export_pdf          bool --- default true

  reader_can_export_pdf            bool --- default true

  reader_can_comment               bool --- default true
  -------------------------------- ----------------------------------------------

> **NOTE:** If a unit has no UnitPolicy record, all permission checks
> fall back to the DefaultUnitPolicy (unit_id=null). New permission
> flags added in future releases only require updating the
> DefaultUnitPolicy --- no migration of existing unit records.

#################### 1.17 Comment (new in v2.8)

A threaded comment attached to a protocol, a sample, or a picture. Any
user with read access to a protocol can add comments, including
RESPONSIBLE contacts and members of responsible users' units. Comments
are visible to all users who can see the protocol. When a comment is
posted, the assigned operator receives an email notification
(best-effort, fire-and-forget).

  --------------------- -------------------------------------------------
  **Field**             **Type / Description**

  id                    UUID

  protocol_id           UUID --- FK to Protocol; always set; used for
                        access checks

  target_type           enum(PROTOCOL, SAMPLE, PICTURE) --- entity type
                        the comment is attached to

  target_id             UUID --- polymorphic FK to the target entity
                        identified by target_type

  parent_id             UUID --- FK to Comment (nullable); one-level-deep
                        threading; null for top-level comments

  author_id             UUID --- FK to User

  body                  string --- Comment text. Set to \'\[deleted\]\'
                        on soft-delete.

  is_deleted            bool --- Soft-delete flag

  created_at            datetime

  updated_at            datetime
  --------------------- -------------------------------------------------

> **NOTE:** Comments are not blocked by protocol.status=LOCKED. Locking
> prevents data modifications; discussion continues on locked protocols.

########## 2. Functional Requirements --- Backend & Business Logic

All heavy processing runs asynchronously via Celery. HTTP endpoints
return immediately with a task_id. This chapter contains all functional
requirements RF-01 through RF-22. RF-09 has been removed (content fully
covered by RF-01, RF-16 and RF-17); requirements are renumbered from
RF-10 onward. The underlying data-service technical protocol is detailed
in §8.

#################### 2.1 RF-01 --- Unified Server-Side Ingestion Pipeline

> **ARCHITECTURE DECISION:** The pipeline is organised in guarded
> levels. All plugins within the same level execute in parallel (Celery
> group / thread pool). Execution proceeds to the next level only when
> all plugins in the current level have completed. Each plugin declares
> a guard() function that checks PipelineContext preconditions --- if
> the guard fails the plugin is skipped without error. New instrument
> types and processing steps are registered as plugins without modifying
> the pipeline coordinator.

Trigger: data-service POST to /api/v1/data-service/upload (after ACCEPT
from RF-16).

############################## Pipeline levels

  ----------- ------------ --------------------- -----------------------------------------
  **Level**   **Mode**     **Plugins**           **Description**

  0           Sequential   ReceiveHandler        Persist raw bytes to object storage;
                                                 initialise PipelineContext. Barrier: all
                                                 subsequent levels depend on the context
                                                 object created here.

  1           Parallel     FileTypeHandler,      FileTypeHandler: guess ElementType from
                           PictureTypeHandler    filename regex. PictureTypeHandler: open
                                                 with Pillow, run registered
                                                 \_am_i_right() chain, set
                                                 context.picture_type. Independent --- run
                                                 simultaneously.

  2           Parallel     MetadataHandler,      MetadataHandler: dispatch to per-type
                           StorageHandler        extractor, populate context.params JSONB.
                                                 StorageHandler: move object to final key
                                                 {protocol_id}/{sample_path}/{filename}.
                                                 Both read from temp object; independent.

  3           Parallel     DerivativeHandler     Generate THUMBNAIL, FULLSIZE_PNG, DZI
                                                 (\>10 MP), FRAME_PNG (XL40 multiframe).
                                                 Sub-tasks per derivative type. Create
                                                 ImageDerivative records.

  4           Parallel     CalibrationHandler,   CalibrationHandler: select
                           DatabarHandler,       CalibrationConfig, run calibration if
                           EmbeddingHandler      enabled. DatabarHandler: crop_databar if
                                                 enabled. EmbeddingHandler: compute vector
                                                 embedding (GPU-eligible --- see §6). All
                                                 three are independent.

  5           Sequential   SampleTreeHandler     check_and_add_parents(): create missing
                                                 Sample nodes from context.sample_path.
                                                 Sequential --- writes to Sample tree with
                                                 potential parent creation.

  6           Sequential   NotifyHandler         WebSocket push: new image available,
                                                 processing status. Runs last to ensure
                                                 all data is committed.
  ----------- ------------ --------------------- -----------------------------------------

> **NOTE:** EmbeddingHandler guard: skips GENERIC_MICROSCOPE_PICTURE and
> images in ERROR state. The embedding field on MicroscopePicture is
> null until this handler completes. Embedding model and dimensionality
> are configurable per deployment. GPU use is optional --- falls back to
> CPU if no CUDA device is available.
>
> **NOTE:** Out-of-band: embed_vega_jpeg_metadata --- triggered by .hdr
> sidecar arrival for VEGA JPEG; independent of the main pipeline.

#################### 2.2 RF-02 --- Metadata Extraction

-   FEI: read proprietary tags; compute magnification = display_width /
    horizontal_field_of_view

-   VEGA TIFF: parse VegaMetadataParser from TIFF tag 50431 via regex
    MetadataDecoder chain

-   VEGA JPEG: parse piexif MakerNote; if .hdr absent, set
    has_metadata=False and schedule embed_vega_jpeg_metadata task when
    sidecar arrives

-   XL40: parse XMPMETA XML via XMPMixin.find_xmp_element(); handle
    multi-page TIFF frames

#################### 2.3 RF-03 --- Thumbnail and Derivative Generation

-   THUMBNAIL: PNG at max_width=400px (configurable per
    ExperimentConfiguration)

-   FULLSIZE_PNG: full-size PNG conversion; 16-bit TIFF applies numpy
    intensity normalisation

-   DZI: Deep Zoom Image tile set via libvips for images \>10 megapixels

-   FRAME_PNG: one ImageDerivative per frame for XL40 multiframe
    (frame_index set)

-   Idempotent: skip if derivative already exists in object storage
    (force_regen=False default)

#################### 2.4 RF-04 --- Image Calibration

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

#################### 2.5 RF-05 --- FEI Databar Removal

-   Detect databar height from image data

-   Save cropped version as CROPPED ImageDerivative; original is never
    overwritten

-   Controlled by databar_removal field in the QUATTRO/VERSA/FEI
    CalibrationConfig entry

#################### 2.6 RF-06 --- Protocol CRUD

  -------------------------------------- ------------ ------------------------------------
  **Endpoint**                           **Method**   **Description**

  /api/v1/protocols                      POST         Create protocol; assign
                                                      protocol_number from DB sequence;
                                                      set acquisition_status=ONGOING

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

  /api/v1/protocols                      GET          Search/list with SQL-level
                                                      visibility filter
  -------------------------------------- ------------ ------------------------------------

#################### 2.7 RF-07 --- Protocol Item Annotation

> **KEY CHANGE v2.3:** v2.8: YAMLRecycler logic removed entirely. All
> annotation fields (caption, description, extra_info) live directly on
> each ProtocolItem record. PATCH on any field updates the record in
> place --- there is no YAML file, no sync, no recycler. extra_info is
> JSONB (was string).

Any entity inheriting ProtocolItem (MicroscopePicture, Attachment,
OpticalImage, NavigationImage, Video) supports PATCH on caption,
description, and extra_info. PATCH triggers a WebSocket push so the UI
updates immediately. Annotation fields are preserved automatically
during reassignment (RF-13) because they live on the record --- no
special preservation logic required.

#################### 2.8 RF-08 --- Protocol Export (PDF / HTML)

> **KEY CHANGE v2.3:** v2.8: output upgraded from HTML-only to
> PDF-primary via WeasyPrint. HTML remains available as secondary
> format. The Jinja2 template is shared between both formats; a separate
> PDF CSS file adds pagination rules. The export cache on Protocol
> stores the last generated output regardless of format.

Generated on-demand only. The export is a complete snapshot of the
protocol at the time of the request --- images, metadata, annotations,
contacts, operator. It is not a live view.

  --------------- ----------------------------------------------------------------------------------
  **Aspect**      **Specification**

  Endpoint        GET
                  /api/v1/protocols/{id}/export?format=pdf\|html&image_quality=thumbnail\|fullsize

  Default         format=pdf, image_quality=thumbnail

  PDF generation  WeasyPrint renders the Jinja2 template + PDF CSS; returns application/pdf

  HTML generation Jinja2 template + HTML CSS; returns text/html as download

  Image quality   thumbnail: uses THUMBNAIL derivative (400px, fast). fullsize: uses FULLSIZE_PNG
                  (can produce large PDFs for long sessions --- warn user)

  PDF/A-1b        Optional flag: ?archival=true. WeasyPrint produces PDF/A-1b conformant output
                  suitable for long-term archival (ISO 19005-1)

  Caching         html_export_cache stores last generated blob; invalidated only on explicit
                  re-export request

  Access          Any user with read access to the protocol may request an export, subject to
                  UnitPolicy.reader_can_export_pdf
  --------------- ----------------------------------------------------------------------------------

> **DEPLOYMENT:** WeasyPrint system dependencies must be present in the
> Docker image: libpango-1.0-0, libpangoft2-1.0-0, libharfbuzz0b,
> libfontconfig1, libcairo2. See §5.2.

#################### 2.9 RF-09 --- Integrated Logbook

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

#################### 2.10 RF-10 --- File Ingestion Transport

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

#################### 2.11 RF-11 --- New Experiment Wizard (API Flow)

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

#################### 2.12 RF-12 --- Labtools Endpoints

-   POST /api/v1/tools/metadata --- dump all TIFF/EXIF/XMP metadata as
    JSON

-   POST /api/v1/tools/fei/calibrate --- standalone FEI calibration on
    an uploaded file

-   POST /api/v1/tools/fei/crop-databar --- standalone databar removal

-   POST /api/v1/tools/convert --- convert TIFF to PNG/JPEG with
    optional resize

-   POST /api/v1/tools/fei/check --- detect FEI subtype (FEI_SFEG vs
    FEI_HELIOS)

#################### 2.13 RF-13 --- Post-Ingestion Element Reassignment

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

#################### 2.14 RF-14 --- Data-Service Registration & Session Authentication

Machine-to-machine authentication pattern: one-time API key
registration; per-connection session token. Full implementation details
in §8.1.

  ------------------------------- ------------ -------------------------------------
  **Endpoint**                    **Method**   **Description**

  /api/v1/data-service/register   POST         One-time registration: body {
                                               hostname, watch_folder, os_info,
                                               agent_version, registration_secret };
                                               response { client_id, api_key } ---
                                               api_key returned in plain text
                                               exactly once; 403 if
                                               registration_secret does not match
                                               server-side REGISTRATION_SECRET env
                                               var

  /api/v1/data-service/auth       POST         Per-connection auth: body {
                                               client_id, api_key }; response {
                                               session_token, expires_at };
                                               session_token is JWT RS256 with 8h
                                               TTL
  ------------------------------- ------------ -------------------------------------

> **NOTE:** TLS mandatory on all data-service endpoints. api_key stored
> server-side as bcrypt hash only. session_token used as Bearer token on
> all subsequent requests.

############################## TLS specification

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

#################### 2.15 RF-15 --- Heartbeat & Task Delivery

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

#################### 2.16 RF-16 --- File Event Notification (Notify → ACCEPT/IGNORE)

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
                                                  exposing domain logic to the
                                                  client. The token is generated
                                                  server-side as an HMAC-SHA256 over
                                                  the encoded payload using a
                                                  dedicated secret key; the backend
                                                  rejects any upload whose context_id
                                                  fails MAC verification. The
                                                  relative_path field is validated
                                                  server-side against a strict
                                                  allowlist pattern before routing
                                                  --- path traversal sequences are
                                                  rejected with 400.
  ---------------------------------- ------------ -----------------------------------

############################## ACCEPT/IGNORE decision rules

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

#################### 2.17 RF-17 --- File Upload (post-ACCEPT)

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
                                             FileEvent.uploaded_at and
                                             FileEvent.sha256 (hex-encoded
                                             SHA-256 of the received bytes,
                                             computed server-side before writing
                                             to object storage) on completion
  ----------------------------- ------------ -----------------------------------

#################### 2.18 RF-18 --- Task Execution & Acknowledgement

The data-service executes tasks delivered in the heartbeat response
(RF-15) and reports results.

> **KEY CHANGE v2.3:** v2.7: task_type is no longer a closed enum. Tasks
> are now command objects with a category and operation. The
> data-service is a generic command executor --- it does not need domain
> knowledge to execute a task. New task types can be added server-side
> without updating the data-service binary, as long as they use existing
> categories.

  ------------------------------- ---------------- ------------ ----------------- -----------------------------------
  **Field**                       **Example                     **Description**   
                                  value**                                         

  task_type                       FILESYSTEM                    Top-level         
                                                                category. Current 
                                                                supported value:  
                                                                FILESYSTEM.       
                                                                Extensible to     
                                                                NETWORK, CONFIG,  
                                                                PROCESS without   
                                                                data-service code 
                                                                changes.          

  operation                       CREATE_DIR                    Operation within  
                                                                the category.     
                                                                Current           
                                                                FILESYSTEM        
                                                                operations:       
                                                                CREATE_DIR,       
                                                                DELETE_DIR        
                                                                (future),         
                                                                RENAME_DIR        
                                                                (future).         

  params                          {\"path\":                    Operation         
                                  \"2024-0042\"}                parameters. For   
                                                                CREATE_DIR: path  
                                                                relative to       
                                                                watch_folder. The 
                                                                data-service does 
                                                                not interpret the 
                                                                path semantics.   

  **Endpoint**                                     **Method**                     **Description**

  /api/v1/data-service/task-ack                    POST                           Body: { task_id, status:
                                                                                  SUCCESS\|ERROR, error_message? };
                                                                                  backend updates
                                                                                  DataServiceTask.status,
                                                                                  completed_at, error_message
  ------------------------------- ---------------- ------------ ----------------- -----------------------------------

> **NOTE:** FILESYSTEM / CREATE_DIR is idempotent: if the directory
> already exists the task reports SUCCESS. Tasks remain PENDING until
> ACKed --- a client restart before ACKing causes re-delivery at the
> next heartbeat.

#################### 2.19 RF-19 --- Acquisition Status --- Manual Transition Only

> **KEY CHANGE v2.3:** acquisition_status has no automatic transitions.
> idle_timeout_minutes has been removed from ExperimentConfiguration.
> acquisition_status=COMPLETED is set exclusively by an authenticated
> user via PATCH /api/v1/protocols/{id} or the \'Mark acquisition
> complete\' button in the Protocol Workspace. The data-service going
> offline does not change acquisition_status.

Rationale: automatic timeout transitions caused false COMPLETED states
for overnight or multi-day sessions. Operators are responsible for
explicitly closing a session.

#################### 2.20 RF-20 --- Data-Service Admin Panel

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

#################### 2.21 RF-21 --- Experiment Wizard --- Folder Deployment

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

#################### 2.22 RF-22 --- Post-Creation Folder Deployment

From the Protocol Workspace, an operator can add the protocol folder to
any ONLINE or OFFLINE data-service client at any time after protocol
creation, as long as protocol.status != LOCKED. Uses the same POST
/api/v1/protocols/{id}/folder-tasks endpoint as RF-21. NEVER_SEEN
clients are excluded. Clients with an existing SUCCESS CREATE_FOLDER
task for this protocol are excluded.

#################### 2.23 RF-23 --- Protocol Comments

Any user with read access to a protocol --- including RESPONSIBLE
contacts with a system account and users granted access via
responsible-unit propagation --- can add comments at protocol, sample,
or picture level. Comments support one-level-deep threading via
parent_id. When a comment is posted, the assigned operator receives an
email notification (best-effort). Comments are visible to all users who
can see the protocol.

  --------------------------------------- ------------ -----------------------------------
  **Endpoint**                            **Method**   **Description**

  /api/v1/protocols/{id}/comments         GET          List all comments for this
                                                       protocol, ordered by created_at.
                                                       Optional query params: target_type,
                                                       target_id to filter by entity.

  /api/v1/protocols/{id}/comments         POST         Add a comment. Body: { body:
                                                       string, target_type:
                                                       enum(PROTOCOL,SAMPLE,PICTURE),
                                                       target_id: UUID, parent_id?: UUID
                                                       }. Author set from JWT. Returns
                                                       Comment record. Triggers
                                                       best-effort email notification to
                                                       the assigned operator.

  /api/v1/protocols/{id}/comments/{cid}   DELETE       Author or UNIT_MANAGER /
                                                       SYSTEM_ADMIN only. Soft-delete ---
                                                       body replaced with \'\[deleted\]\'.
  --------------------------------------- ------------ -----------------------------------

> **NOTE:** Comments are not blocked by protocol.status=LOCKED. A locked
> protocol can still receive comments --- locking controls data
> modifications, not discussion. Email notifications to the assigned
> operator are fire-and-forget; delivery failure does not affect the
> HTTP response.

#################### 2.24 RF-24 --- Data-Service Auto-Update

The data-service checks for available updates at every heartbeat and
applies them automatically when a new version is available and the
update has been approved by an admin.

  ------------------------------------ ------------ -----------------------------------
  **Endpoint**                         **Method**   **Description**

  /api/v1/data-service/version         GET          Returns { current_version,
                                                    latest_version, download_url,
                                                    signature, auto_update_enabled }

  /api/v1/admin/data-service/release   POST         Admin publishes a new release:
                                                    uploads signed binary, sets version
                                                    string and auto_update_enabled flag
  ------------------------------------ ------------ -----------------------------------

############################## Update flow on the client

-   At each heartbeat the data-service compares its agent_version
    against latest_version from the server

-   If a newer version is available and auto_update_enabled=true:
    download binary from download_url, verify signature (Ed25519
    detached signature over the binary SHA-256 hash; public key is
    embedded in the data-service binary at build time and cannot be
    changed without a full reinstall), write to temp path

-   If signature verification passes: atomically replace the running
    binary. On Windows: schedule replacement on next service restart via
    SC config; on Linux: systemd ExecStartPre script handles atomic swap

-   If verification fails or download is incomplete: discard temp file,
    log error, continue running current version

-   Rollback: if new binary fails to start (health check timeout),
    service manager restores previous binary from backup copy

-   Admin can disable auto-update per client via the Admin Panel (RF-20)
    --- sets auto_update_enabled=false for that client

########## 3. Access Control Model

v2.8: Access control model extended with configurable per-unit
permissions (UnitPolicy), formalised unit membership (UnitMembership),
and access propagation via RESPONSIBLE contacts. The three UI-facing
visibility presets (Public, Unit, Restricted) are unchanged from the
user\'s perspective.

#################### 3.1 Principals

  ---------------- ------------------------------------------------------
  **Principal**    **Description**

  User             Individual authenticated account. Has a primary
                   unit_id. Belongs to one or more units via
                   UnitMembership with a role per unit.

  Unit             Organisational group (e.g. a laboratory). Has one or
                   more members with role MANAGER.

  Role per unit    MANAGER / OPERATOR / READER --- defined in
                   UnitMembership, not globally. A user can be MANAGER in
                   unit A and READER in unit B.

  SYSTEM_ADMIN     Global role. Can manage all units, all policies, all
                   clients. Not bound to a unit.
  ---------------- ------------------------------------------------------

#################### 3.2 UnitMembership

Formalises the relationship between a user and a unit with an explicit
role. Replaces the implicit unit_id field and the hardcoded UNIT_MANAGER
global role.

  ------------------ ----------------------------------------------------
  **Field**          **Type / Description**

  user_id            UUID --- FK to User

  unit_id            UUID --- FK to Unit

  role               enum --- MANAGER / OPERATOR / READER

  granted_by         UUID --- FK to User (the MANAGER or SYSTEM_ADMIN who
                     granted membership)

  created_at         datetime
  ------------------ ----------------------------------------------------

> **NOTE:** A user can have multiple UnitMembership records with
> different roles in different units. Permissions are evaluated
> per-protocol by looking up the user\'s role in the protocol\'s owner
> unit.

#################### 3.3 UnitPolicy

Defines what members of each role can do within a unit. Each unit has
one UnitPolicy. A system-level DefaultUnitPolicy provides baseline
values; unit-level overrides take precedence. SYSTEM_ADMIN manages all
UnitPolicies; a unit MANAGER manages only their unit\'s policy.

  -------------------------------- ------------- -------------------------------------
  **Permission flag**              **Default**   **Description**

  operator_can_delete_protocol     false         OPERATOR can delete their own
                                                 protocols

  operator_can_move_protocol       false         OPERATOR can move a protocol to a
                                                 different unit

  operator_can_lock_protocol       true          OPERATOR can lock/unlock their own
                                                 protocols

  operator_can_change_visibility   true          OPERATOR can change the AccessPolicy
                                                 of their own protocols

  operator_can_export_pdf          true          OPERATOR can request PDF/HTML export

  reader_can_export_pdf            false         READER can request PDF/HTML export

  reader_can_comment               true          READER can add comments to visible
                                                 protocols
  -------------------------------- ------------- -------------------------------------

> **NOTE:** The DefaultUnitPolicy is system-wide and set by
> SYSTEM_ADMIN. Individual units can override any flag. If a unit has no
> explicit override for a flag, the system default applies. This means
> adding new permission flags in future releases requires only updating
> the DefaultUnitPolicy --- no migration of existing unit policies.

#################### 3.4 AccessPolicy --- Protocol and Sample Visibility

Every Protocol and Sample carries an AccessPolicy (§1.12). The backend
evaluates access by inspecting scope_type and matching against the
requesting user\'s UnitMembership records.

  ---------------- ------------------------------------------- ---------------
  **scope_type**   **Access rule**                             **UI label**

  OPEN             Any authenticated user can see this         Public
                   resource                                    

  GROUP            Only members of the unit identified by      Unit only
                   group_id can see this resource              (default)

  EXPLICIT         Only the resource owner and users in        Restricted
                   allowed_ids. Invisible to everyone else     
                   including group members.                    
  ---------------- ------------------------------------------- ---------------

> **SECURITY:** EXPLICIT scope is the strongest restriction. The
> resource is completely invisible --- no title, metadata, or thumbnail
> leaks --- to users not in allowed_ids, including unit members.

#################### 3.5 Access via RESPONSIBLE Contacts

If a Protocol has a ProjectContact with role=RESPONSIBLE and that
contact has a user_id (i.e. a system account), access is automatically
granted to:

-   The responsible user themselves: read access + ability to add
    comments

-   All members of the responsible user\'s primary unit: read-only
    access (cannot annotate, cannot export unless
    reader_can_export_pdf=true in their unit\'s UnitPolicy)

This propagation is orthogonal to AccessPolicy --- it applies even if
the protocol is EXPLICIT-scope. It can be disabled per-protocol via
Protocol.responsible_access_enabled=false.

> **NOTE:** The RESPONSIBLE access grant does not stack with ownership
> privileges. A responsible user who is not the owner cannot edit
> annotations, reassign elements, or change visibility --- unless their
> UnitMembership role in the owner unit permits it. If a RESPONSIBLE
> contact has user_id=null (informative mode, see §1.14), no access
> propagation occurs --- the contact's name appears in the protocol and
> export only. Access propagation is triggered exclusively when user_id
> is non-null.

#################### 3.6 Extensibility

New AccessPolicy scope types can be introduced without schema changes
--- scope_type is evaluated in the AuthorizationService. Planned future
types:

  --------------- -------------------------------------------------------
  **Future type** **Intended semantics**

  TIMED           Visible to all after embargo_until date --- useful for
                  pre-publication data

  CONSORTIUM      Visible to members of a defined inter-unit consortium

  DEPARTMENT      Visible to all members of a parent department (requires
                  group hierarchy --- §7.1)
  --------------- -------------------------------------------------------

#################### 3.7 Permission Evaluation Summary

For any action on a protocol, the backend evaluates in order:

-   1\. Is the user SYSTEM_ADMIN? → full access

-   2\. Is the user the protocol owner? → full access subject to
    UnitPolicy flags

-   3\. Does the user have a MANAGER role in the protocol\'s owner unit?
    → management access subject to UnitPolicy

-   4\. Does the user have an OPERATOR role in the owner unit? →
    operator access subject to UnitPolicy

-   5\. Is the user a RESPONSIBLE contact with a system account? →
    read + comment

-   6\. Is the user a member of a RESPONSIBLE contact\'s unit? →
    read-only

-   7\. Is the user in AccessPolicy.allowed_ids? → read + comment

-   8\. Is AccessPolicy.scope_type=GROUP and user is a member of
    group_id? → read-only for READERs, operator access for OPERATORs

-   9\. Is AccessPolicy.scope_type=OPEN? → read-only for all
    authenticated users

-   All other cases: no access --- resource is invisible

#################### 3.8 API Enforcement

-   All API endpoints check permissions via dependency-injected
    AuthorizationService

-   Protocol and sample list queries apply access filters at SQL level
    via RLS --- never post-filtered

-   UnitPolicy flags are checked by the AuthorizationService before any
    write operation

-   Object storage URLs are pre-signed with 15-minute TTL

-   Audit log: all access to EXPLICIT-scope resources logged (user,
    timestamp, endpoint, IP)

#################### 3.9 Authentication (Human Users)

-   JWT Bearer tokens (15 min) + refresh tokens (7 days)

-   Integration with institutional LDAP/Active Directory via
    oauth2-proxy or python-ldap

-   Fallback: local accounts for external collaborators

-   MFA optional --- enforced by SYSTEM_ADMIN per user or per unit

########## 4. User Flows --- Web UI

The React SPA is the primary interface for all protocol viewing and
annotation. File content enters the system exclusively via the
data-service. This chapter covers all user flows, including those
introduced in v2.2 for data-service management and folder deployment.

#################### 4.1 Flow 1 --- New Experiment

############################## Step 1 --- Parameters

-   Microscope type (Quattro / Versa / Vega / XL40 / Multi)

-   Operator (pre-filled from authenticated user, editable)

-   Project name, Customer

-   Visibility (PUBLIC / UNIT / RESTRICTED) --- default UNIT

-   If RESTRICTED: user search to pre-populate allowed_users

-   Protocol number: read-only, assigned by server on creation

############################## Step 2 --- Confirm & Download Data-Service Config

-   \'Create experiment\' → server creates Protocol
    (acquisition_status=ONGOING)

-   Download JSON config file for the data-service

############################## Step 3 --- Folder Deployment (optional, new in v2.2)

-   See Flow 8 --- operator selects acquisition PCs; CREATE_FOLDER tasks
    queued

############################## Step 4 --- Workspace opens

-   Protocol Workspace opens empty, waiting for first file from
    data-service

-   Acquisition status banner: \'Acquisition in progress\'

#################### 4.2 Flow 2 --- Protocol Dashboard

-   Search bar: full-text search across project, responsible,
    protocol_number, customer

-   Filter chips: microscope type, unit, date range, status,
    acquisition_status, visibility

-   Results grid: card per protocol (thumbnail, number, project, date,
    status chips)

-   UNIT and RESTRICTED protocols of other units absent from results

-   Click card → Protocol Workspace

#################### 4.3 Flow 3 --- Protocol Workspace

Three-column layout --- all data fetched via REST API and rendered by
the React SPA.

############################## Left panel --- Sample Tree

-   Collapsible tree; populated exclusively from API data as the
    data-service pushes files

-   Status badges: image count, processing state (PENDING / DONE /
    ERROR)

-   RESTRICTED samples shown as \'\[Confidential\]\' for unauthorised
    users

-   Context menu (authorised users): Move to sample, Rename, Remove,
    Restrict, Lock, View audit log

############################## Centre panel --- Content Area

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

############################## Right panel --- Edit Panel

-   caption, description, extra_info --- auto-save with debounce via
    PATCH API calls

-   Protocol-level introduction and conclusion: inline text areas at
    top/bottom of protocol view

############################## Top bar

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

#################### 4.4 Flow 4 --- Post-Ingestion Correction (RF-14)

-   Operator right-clicks misplaced image in Sample Tree → \'Move to
    sample\...\'

-   Modal shows full sample tree with picker; operator selects correct
    target → \'Move\'

-   Server: copies object to new key, updates DB, preserves custom
    fields, deletes old key, triggers WebSocket push

-   Audit log entry written with old and new sample path

> **CONSTRAINT:** Reassignment is blocked if protocol.status=LOCKED.
> Operator must unlock first, correct, then re-lock.

#################### 4.5 Flow 5 --- Sensitivity Management

-   Protocol owner or UNIT_MANAGER can change visibility while status !=
    LOCKED

-   Changing to RESTRICTED: modal prompts to add allowed_users

-   Changing from RESTRICTED: modal warns images will become visible to
    unit

-   Sample-level: right-click sample → \'Restrict this sample\' →
    allowed_users modal

#################### 4.6 Flow 6 --- Labtools Standalone Page

-   Metadata Viewer: upload TIFF/JPEG → display full metadata tree as
    JSON (stateless)

-   FEI Tools: calibrate / crop-databar on individual files without
    creating a protocol

-   Image Converter: upload TIFF → configure output format/size →
    download

-   All labtools operations are stateless --- files are not persisted
    server-side

#################### 4.7 Flow 7 --- Admin Panel: Data-Service Client Management (RF-20)

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

#################### 4.8 Flow 8 --- Experiment Wizard: Folder Deployment Step (RF-21)

Optional step in the New Experiment Wizard (Flow 1), immediately after
protocol creation.

############################## Client list

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

############################## After confirming selection

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

#################### 4.9 Flow 9 --- Post-Creation Folder Deployment (Protocol Workspace) (RF-22)

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

########## 5. Architectural Proposal --- Stack & System Design

#################### 5.1 High-Level Architecture

Browser SPA (React 18 + TypeScript) communicates via HTTPS REST +
WebSocket with a FastAPI backend behind Nginx TLS termination. Celery
workers handle all async image processing. PostgreSQL stores all domain
entities; Redis serves as Celery broker, cache and WebSocket pub/sub.
Object storage (MinIO / S3-compatible) holds all binary files. The
data-service daemon runs on acquisition PCs and communicates exclusively
with the FastAPI backend using the two-step notify→upload protocol
(RF-17, RF-18).

#################### 5.2 Backend --- FastAPI

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

  Jinja2                  Protocol PDF/HTML export only (RF-08)

  WeasyPrint              PDF generation from Jinja2-rendered HTML
                          (RF-08). Requires system packages:
                          libpango-1.0-0, libpangoft2-1.0-0,
                          libharfbuzz0b, libfontconfig1, libcairo2 in the
                          Docker image.

  boto3 / minio-py        Object storage client

  python-jose             JWT token creation and validation

  python-ldap / ldap3     Institutional directory integration

  bcrypt                  API key hashing for DataServiceClient

  torch / transformers    EmbeddingHandler --- GPU-accelerated image
  (optional)              embedding. Optional dependency; pipeline falls
                          back to CPU if not available. See §6.
  ----------------------- -----------------------------------------------

#################### 5.3 Task Queue --- Celery

The ingestion pipeline is organised in guarded levels (RF-01). Plugins
within the same level execute as a Celery group (parallel). The pipeline
coordinator dispatches levels sequentially; within each level all tasks
are dispatched simultaneously and the coordinator waits for all to
complete before advancing.

  ----------- --------------------------- ------------------------ --------------
  **Level**   **Handler / Task**          **Trigger / Condition**  **Priority**

  0           ReceiveHandler              Data-service POST to     HIGH
                                          /upload (after ACCEPT)   

  1           FileTypeHandler             Level 0 complete         HIGH

  1           PictureTypeHandler          Level 0 complete ---     HIGH
                                          parallel with            
                                          FileTypeHandler          

  2           MetadataHandler             Level 1 complete ---     HIGH
                                          dispatches to per-type   
                                          extractor                

  2           StorageHandler              Level 1 complete ---     HIGH
                                          parallel with            
                                          MetadataHandler          

  3           DerivativeHandler           Level 2 complete ---     HIGH
                                          generates all derivative 
                                          types                    

  4           CalibrationHandler          Level 3 complete         MEDIUM

  4           DatabarHandler              Level 3 complete ---     MEDIUM
                                          guard: FEI types only    

  4           EmbeddingHandler            Level 3 complete ---     MEDIUM
                                          GPU-eligible; guard:     
                                          non-GENERIC              

  5           SampleTreeHandler           Level 4 complete ---     MEDIUM
                                          sequential DB write      

  6           NotifyHandler               Level 5 complete ---     MEDIUM
                                          WebSocket push           

  ---         embed_vega_jpeg_metadata    On .hdr sidecar arrival  HIGH
                                          (out-of-band)            

  ---         generate_export             User requests RF-08      LOW
                                          export --- on-demand     

  ---         reassign_element            User RF-13 action via UI HIGH

  ---         process_task_ack            Data-service ACK         MEDIUM
                                          received (RF-18)         
  ----------- --------------------------- ------------------------ --------------

#################### 5.4 Frontend --- React SPA

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

#################### 5.5 Data Storage

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

############################## PostgreSQL

-   All domain entities including DataServiceClient, DataServiceTask,
    FileEvent

-   JSONB for params (MicroscopePicture) and payload (DataServiceTask)

-   Row-Level Security (RLS) policies enforce visibility at the database
    layer

-   Full-text search on project, responsible, description (tsvector
    index)

############################## Object Storage (MinIO / S3-compatible)

-   Original TIFF and JPEG uploads; all ImageDerivative files
    (THUMBNAIL, FULLSIZE_PNG, DZI tiles, CROPPED, FRAME_PNG); HTML
    export files; attachments

-   Pre-signed URLs with 15-minute TTL --- browser downloads directly
    from storage, no backend proxy

-   Soft-deleted images retained 30 days before purge (RF-13 remove
    operation)

-   Target deployment: MinIO on-premise on same local network as
    backend. MinIO must not be reachable directly from the institutional
    LAN --- it must be accessible only from the backend container
    network. Browser access to files is exclusively via pre-signed URLs
    proxied through the backend; MinIO does not require a public-facing
    port.

############################## Redis

-   Celery broker and result backend; HTTP session and JWT blacklist
    cache. Redis must be configured with requirepass authentication and
    must not be reachable outside the backend container network --- bind
    address restricted to the internal Docker bridge interface.

-   WebSocket pub/sub for real-time events; protocol-level write lock

-   JWT blacklist for revoked data-service session tokens (RF-14, RF-20)

#################### 5.6 API Design Conventions

-   Base path: /api/v1/

-   Human auth: JWT Bearer (15 min) + refresh tokens (7 days). Refresh
    tokens are stored server-side (hashed in PostgreSQL); disabling or
    deleting a user account immediately invalidates all associated
    refresh tokens. JWT access tokens are stored client-side in
    httpOnly, Secure, SameSite=Strict cookies --- never in localStorage
    or sessionStorage.

-   Data-service auth: API key → session JWT (8h) per RF-15; see §8.1
    for full protocol

-   Async responses: 202 Accepted + { task_id, status_url } for all
    pipeline operations

-   WebSocket: WS /api/v1/ws/protocols/{id} --- real-time events

-   Pagination: cursor-based for all list endpoints

-   Error format: RFC 7807 Problem Details

-   Visibility filtering: SQL RLS --- never post-filtered in application
    code

########## 6. Hardware Requirements

This section specifies the minimum and recommended hardware for running
the autologbook platform in a university laboratory deployment. The
primary variables are the number of concurrent acquisition sessions and
the use of the EmbeddingHandler (GPU-accelerated). A dedicated physical
server is not required: the application stack runs equally well on a
virtual machine (VM) or a cloud/IaaS instance, provided the hosting
infrastructure delivers the services described below (backup, network
connectivity, uptime). Similarly, object storage does not require a
dedicated machine --- a shared institutional NAS mounted at /data on the
application server is a fully supported deployment option, as long as it
meets the capacity and throughput specifications in §6.2.

#################### 6.1 Server (Application + Backend)

  --------------- --------------- ------------------ -----------------------
  **Component**   **Minimum**     **Recommended**    **Notes**

  CPU             4 cores         8+ cores           Celery workers are
                                                     CPU-bound for image
                                                     processing. Each worker
                                                     uses one core. Minimum
                                                     4 workers recommended
                                                     (NFR-04).

  RAM             16 GB           32 GB              Each Celery worker may
                                                     load a 2 GB TIFF into
                                                     memory for processing.
                                                     At 4 parallel workers,
                                                     8 GB reserved for
                                                     workers plus OS
                                                     overhead.

  GPU             None (optional) CUDA-compatible, 8 Required only for
                                  GB VRAM            EmbeddingHandler.
                                                     NVIDIA RTX 3080 or
                                                     equivalent. Falls back
                                                     to CPU if absent ---
                                                     embedding computation
                                                     will be significantly
                                                     slower (\~10x).

  Storage         SSD, 100 GB     SSD, 1 TB+         OS, application,
                                                     PostgreSQL data, and
                                                     temporary Celery task
                                                     files. Object storage
                                                     (MinIO) is separate ---
                                                     see §6.2.

  Network         1 Gbps          10 Gbps            For acquisition PC →
                                                     server TIFF uploads. A
                                                     500 MB TIFF takes \~4
                                                     seconds on 1 Gbps;
                                                     \~0.4 seconds on 10
                                                     Gbps.
  --------------- --------------- ------------------ -----------------------

NOTE ON DEPLOYMENT FORM FACTOR: A dedicated physical server is not
required. The application stack (FastAPI, Celery, PostgreSQL, Redis,
Nginx) runs on any of the following, provided the host meets the CPU,
RAM, and storage specifications above: (1) a physical server owned by
the laboratory or institution; (2) a virtual machine (VM) on
institutional virtualisation infrastructure (VMware, Proxmox, KVM,
Hyper-V, or equivalent); (3) a cloud or IaaS instance (AWS EC2, Azure
VM, institutional OpenStack, or equivalent). For VM and IaaS
deployments, the hosting infrastructure is responsible for providing the
services that physical hardware would otherwise imply: regular snapshots
or backups of the VM disk, network connectivity to acquisition PCs, and
uptime SLAs consistent with the RPO/RTO targets in §11.4. autologbook
itself has no dependency on the underlying hypervisor or cloud provider.

#################### 6.2 Object Storage (MinIO)

  --------------- ---------------- ------------------ ---------------------
  **Component**   **Minimum**      **Recommended**    **Notes**

  Storage         SSD or HDD, 2 TB SSD, 10 TB+        All original TIFFs +
                                                      derivatives +
                                                      exports. A SEM
                                                      session with 100
                                                      images at 50 MB each
                                                      = 5 GB per session
                                                      for originals;
                                                      derivatives add \~2x.
                                                      SSD strongly
                                                      preferred for
                                                      derivative generation
                                                      throughput.

  Network         1 Gbps to server 10 Gbps            MinIO and the
                                                      application server
                                                      should be on the same
                                                      LAN. Pre-signed URL
                                                      generation adds
                                                      latency proportional
                                                      to network RTT.

  Redundancy      Single node      MinIO distributed  Single-node MinIO is
                                   mode (min 4 nodes) acceptable for a
                                                      small lab;
                                                      distributed mode for
                                                      production with
                                                      durability
                                                      requirements.
  --------------- ---------------- ------------------ ---------------------

NOTE ON SHARED NAS: A dedicated MinIO server is not required. The object
storage backend can use any of the following: (1) a standalone MinIO
instance on a dedicated server; (2) MinIO running on the same server as
the application backend, storing data on a volume at /data --- this
volume may be a locally attached disk or a shared NAS (NFS, SMB/CIFS, or
similar) mounted at that path by the host OS. When using a shared
institutional NAS, the NAS is not required to be dedicated to
autologbook --- other data may coexist on the same NAS, provided the
capacity and throughput specifications above are met for the autologbook
share. The NAS administrator is responsible for providing backup and
redundancy at the NAS level; autologbook's MinIO backup procedure
(§11.4) applies to the MinIO data directory regardless of the underlying
storage medium. (3) any S3-compatible object storage endpoint (AWS S3,
Wasabi, MinIO cluster, institutional Ceph, etc.) --- note that if a
remote S3 endpoint is used outside the institutional LAN, a GDPR
transfer impact assessment is required before activation (§11.6).

#################### 6.3 Acquisition PCs (data-service)

  --------------- ------------------ --------------------------------------
  **Component**   **Minimum**        **Notes**

  OS              Windows 7 SP1 /    The data-service Go binary is
                  Linux kernel 3.x+  statically compiled with no OS runtime
                                     dependencies.

  RAM             256 MB available   The data-service daemon has a \~20 MB
                                     footprint at rest. SQLite offline
                                     buffer uses disk, not RAM.

  Disk            10 GB free         Default SQLite offline buffer limit.
                                     Configurable.

  Network         Any connectivity   Can operate over VPN. File upload
                  to server          speed determines ingestion throughput
                                     --- 1 Gbps LAN recommended for large
                                     TIFFs.
  --------------- ------------------ --------------------------------------

#################### 6.4 GPU Configuration for EmbeddingHandler

The EmbeddingHandler is an optional pipeline plugin that computes dense
vector embeddings of SEM images for similarity search and future
AI-assisted annotation. It is disabled by default and can be enabled per
deployment.

-   Minimum VRAM: 4 GB (small embedding models, e.g. CLIP ViT-B/32)

-   Recommended VRAM: 8 GB (larger models, batch processing of multiple
    images concurrently)

-   CUDA 11.8+ required for GPU acceleration

-   If no GPU is present, EmbeddingHandler runs on CPU --- adds
    \~30--120 seconds per image depending on model size; not recommended
    for production with high acquisition volume

-   The embedding model is configurable per deployment (see
    ExperimentConfiguration); the default model and vector
    dimensionality are defined in the system DefaultUnitPolicy

########## 7. Non-Functional Requirements

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

  NFR-08    Data integrity  Reassignment (RF-13) must be atomic: DB update
                            and object storage move succeed together or
                            both roll back

  NFR-09    Security        EXPLICIT-scope protocol thumbnails must never
                            appear in API responses for unauthorised users

  NFR-10    Security        Object storage URLs must be pre-signed with
                            15-min TTL --- no public permanent URLs

  NFR-11    Security        All access to EXPLICIT-scope resources must be
                            written to the audit log

  NFR-12    Security        Data-service session tokens scoped only to
                            /api/v1/data-service/\* endpoints

  NFR-21    Security        Each Celery task in the ingestion pipeline
                            must have a hard execution timeout (default
                            300 s for image processing tasks, 60 s for
                            metadata tasks). A task exceeding the timeout
                            is terminated and its status set to ERROR ---
                            no worker must be blocked indefinitely by a
                            malformed or adversarial file.

  NFR-22    Security        Rate limiting must be enforced at Nginx level
                            on all authentication and data-service
                            endpoints: POST /api/v1/auth/login limited to
                            10 requests/min per IP; POST
                            /api/v1/data-service/auth limited to 5
                            requests/min per client_id; POST
                            /api/v1/data-service/file-notify and /upload
                            limited to 120 requests/min per session_token.
                            Requests exceeding the limit receive HTTP 429.

  NFR-23    Security        All user-supplied text fields rendered in the
                            SPA (caption, description, extra_info,
                            introduction, conclusion, comment body) must
                            be sanitised before rendering using DOMPurify
                            with the default configuration
                            (allowlist-based, strips all event handlers
                            and javascript: URIs). The extra_info JSONB
                            field requires special handling: values are
                            rendered as plain text (never as HTML)
                            regardless of content. The backend serves the
                            following Content-Security-Policy header on
                            all responses: default-src \'self\'; img-src
                            \'self\' blob: data:; script-src \'self\';
                            style-src \'self\' \'unsafe-inline\';
                            connect-src \'self\' wss:; font-src \'self\';
                            object-src \'none\'; base-uri \'self\';
                            frame-ancestors \'none\'. Inline scripts are
                            prohibited. The \'unsafe-inline\' allowance
                            for style-src is required by the component
                            library (shadcn/ui); all other directives
                            follow strict same-origin policy.
                            Additionally, the backend sets:
                            X-Content-Type-Options: nosniff;
                            X-Frame-Options: DENY; Referrer-Policy:
                            strict-origin-when-cross-origin on all
                            responses.

  NFR-24    Security        PostgreSQL must accept connections only from
                            the backend container network. pg_hba.conf
                            must reject all connections from outside the
                            Docker bridge interface. The database
                            superuser credentials must not be available to
                            the FastAPI service account --- the service
                            account must connect with a dedicated role
                            that has no SUPERUSER, CREATEDB, or CREATEROLE
                            privileges.

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

########## 8. Open Questions & Migration Notes

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

#################### 7.2 Modules reusable as-is (strip Qt imports only)

-   microscope_picture.py --- MicroscopePicture, FEIPicture,
    VegaPicture, XL40Picture, MicroscopePictureFactory

-   autotools.py --- PictureType, FEITagCodes, VegaMetadataParser, all
    formatters

-   file_type_guesser.py --- ElementTypeGuesser, RegexpRepository (zero
    Qt deps)

-   attachment.py --- Attachment, AttachmentFactory, AttachmentType

-   Jinja2 templates (.yammy files) --- repurposed for RF-08 HTML export
    only

#################### 7.3 Modules to rewrite

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

########## 9. Data-Service --- Technical Protocol

This chapter defines the technical implementation of the data-service
daemon, written in Go (see §8.3 for the language decision rationale). It
covers the authentication mechanism, wire protocol, offline behaviour,
and operational requirements. Functional requirements RF-14 through
RF-22 are specified in §2. UI flows (Flow 7, 8, 9) are in §4.

#################### 9.1 Authentication Implementation --- Session Token Pattern

> **ARCHITECTURE DECISION:** The data-service is a machine client, not a
> human user. Authentication occurs once per connection/reconnect, not
> per message. The pattern follows OAuth2 Client Credentials semantics
> implemented directly in FastAPI --- no external Authorization Server
> required. If an AS is integrated in a future release, the client wire
> protocol (Bearer token) does not change.

############################## Registration (one-time, admin-initiated)

  ------------------------------- ----------------------------------------------
  **Step**                        **Detail**

  POST                            Body: { hostname, watch_folder, os_info,
  /api/v1/data-service/register   agent_version, registration_secret }

  Response (one-time)             { client_id, api_key } --- api_key shown in
                                  plain text exactly once; never retrievable
                                  again

  Client storage                  api_key persisted in local config file (OS
                                  keystore on Windows; 0600-permission file on
                                  Linux)

  Server storage                  api_key_hash (bcrypt, cost factor 12); plain
                                  text discarded immediately
  ------------------------------- ----------------------------------------------

############################## Per-connection authentication flow

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

############################## Session token --- local validation (configurable)

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

#################### 9.2 Language --- Go (Confirmed)

############################## Requirements driving the decision (NFR-16 to NFR-20)

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

############################## Comparison matrix

  ------------------ ------------- ---------------------------- -------------------
  **Criterion**      **Python**    **Go**                       **Rust / C++**

  Windows 7+         ✓ Python 3.8  ✓ static binary, no runtime  ✓ / complex
  compatibility      (EOL but                                   toolchain
                     functional)                                

  Linux legacy       ✓             ✓ (kernel 2.6.23+)           ⚠ MUSL recommended
  kernel                                                        / ✓

  Windows Service    ⚠ via pywin32 ✓ native                     ⚠ crates available
                     (fragile)     (golang.org/x/sys/windows)   / ✓ native

  Linux systemd      ✓ via unit    ✓                            ✓
  daemon             file                                       

  Crash recovery /   ⚠ requires    ✓ goroutine + context cancel ✓ / ✓
  reconnect          explicit      idiom                        
                     design                                     

  Filesystem         ⚠ watchdog    ✓                            ✓
  monitoring         lib;                                       
                     sufficient                                 
                     for SEM                                    

  Memory footprint   ✗ 60--150 MB  ✓ 10--20 MB                  ✓ \<10 MB
                     with                                       
                     interpreter                                

  Distribution       ⚠ PyInstaller ✓ single binary \<15 MB      ✓ \<10 MB / ✗ MSVC
                     \>50 MB; AV                                deps
                     false pos.                                 

  Maintainability    ✓ team knows  ✓ simple syntax              ⚠ steep curve / ✗
                     Python                                     complex

  Legacy code reuse  ✓ watchdog,   ✗ full rewrite               ✗ full rewrite
                     tenacity,                                  
                     requests                                   

  Time to market     ✓ immediate   ✓ 2--3 week rewrite          ✗ months
  ------------------ ------------- ---------------------------- -------------------

############################## Decision

> **CONFIRMED:** The data-service is implemented in Go. Go satisfies all
> NFR-16 through NFR-20: static binary with no runtime dependencies,
> native Windows Service and systemd support, goroutines for crash
> recovery and automatic reconnect, 10--20 MB footprint, compilation
> targeting Windows 7+ and Linux legacy kernels. The comparison table
> above documents the rationale. Python and Rust/C++ were evaluated and
> rejected.

############################## Go library selection

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

############################## Key implementation patterns

############################## Authentication and session management

On startup the data-service reads client_id and api_key from the config
file, calls POST /auth, and stores the session_token in memory. A
background goroutine monitors token expiry (exp claim minus a 5-minute
safety margin) and proactively re-authenticates before expiry. If /auth
fails (network error or 403 revoked), the goroutine retries with
exponential backoff and logs a warning. All other goroutines block on a
sync.RWMutex until a valid token is available.

############################## Filesystem monitoring and XL40 stability debounce

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

############################## Reconnect and crash recovery

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

#################### 9.3 Folder Naming Convention & Protocol Number Extraction

The relative_path sent by the data-service contains the protocol folder
as its first component. The folder name must include the protocol number
in a format parseable by the backend regex (e.g.
\'2024-0042-project-alpha\' --- backend extracts \'0042\'). The folder
is created by the data-service on receipt of a CREATE_FOLDER task
(RF-19). The local folder structure is otherwise unconstrained --- the
legacy NNN-project-resp naming convention is no longer enforced.

########## 10. Legacy Migration Reference

This chapter provides a consolidated reference mapping legacy desktop
application components and ELOG features to their web platform
equivalents. It supplements §7.2 and §7.3.

#################### 10.1 ELOG Feature Mapping

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

#################### 10.2 Desktop Component Mapping

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

########## 11. Security & Compliance

This chapter defines the security requirements, controls and operational
procedures applicable to the autologbook platform. The deployment
context is a university research laboratory: acquisition PCs are
standalone, not managed by central IT, and often run legacy operating
systems. There are no formal certification requirements (ISO 27001,
IT-Grundschutz audit) and no mandatory data retention periods. The
controls defined here are proportionate to the actual risk profile of
this environment.

#################### 11.1 Threat Model

A realistic threat model for this deployment focuses on insider risk and
opportunistic access, not sophisticated external attackers. The system
is not internet-facing by default --- it runs on an institutional
intranet. The analysis follows the STRIDE per-component methodology
applied to six system components: (1) data-service daemon, (2)
data-service → backend communication channel, (3) FastAPI backend +
Celery workers, (4) PostgreSQL + Redis, (5) MinIO object storage, (6)
browser SPA + user channel. Data Flow Diagrams for each component are
provided in §11.7 (Security Design Rationale). The table below maps each
threat to the specific attack vector --- endpoint, port, file, or
configuration element --- through which it is exercised.

  ---------------- ---------------- ------------------- -------------------------
  **Threat**       **Likelihood**   **Impact**          **Primary control**

  Operator reads   MEDIUM --- PCs   HIGH --- attacker   API key stored in OS
  another          are physically   can impersonate the keystore (§10.2);
  operator\'s API  shared in open   PC and inject files revocation procedure
  key from         labs             into any ONGOING    (§10.2)
  acquisition PC                    protocol            
  filesystem                                            

  PC lost, stolen  LOW--MEDIUM ---  HIGH --- same as    OS keystore encryption
  or               lab hardware is  above               (§10.2); immediate
  decommissioned   occasionally                         revocation on incident
  with API key on  misplaced or                         (§10.2)
  disk             repurposed                           

  Operator         LOW --- requires HIGH ---            RLS at DB layer (§3.6);
  accesses a       exploiting an    confidential        audit log (§10.3)
  RESTRICTED       application bug  research data       
  protocol they    or DB access     exposed             
  are not                                               
  authorised for                                        

  Unauthorised     LOW --- requires MEDIUM --- tampered Append-only audit table;
  modification of  SYSTEM_ADMIN     logs reduce         no DELETE/UPDATE
  audit logs       compromise or    incident response   permission for any app
                   direct DB access capability          role (§10.3)

  Data loss due to LOW --- hardware VERY HIGH --- SEM   Daily backup with 30-day
  server failure   failure is       data is             retention (§10.4)
  (PostgreSQL or   infrequent but   non-reproducible;   
  MinIO)           non-zero         sample may be       
                                    destroyed           
                                    post-acquisition    

  Malicious or     LOW --- requires MEDIUM --- file     File type validation in
  corrupted file   valid session    enters ingestion    pipeline (RF-01 step
  injected via     token            pipeline;           2--3); defusedxml for XML
  data-service                      Pillow/defusedxml   parsing
                                    parse it            

  Outdated         LOW--MEDIUM ---  MEDIUM --- depends  Version reporting at
  data-service     Windows 7 PCs    on vulnerability    heartbeat; admin alert on
  binary with      rarely updated   class               outdated agents (§10.5)
  known                                                 
  vulnerability                                         

  Attacker uses a  MEDIUM           HIGH --- file       OS keystore (§11.2);
  static API key                    injection into any  revocation procedure
  from a                            ONGOING protocol;   (§11.2); anomaly
  decommissioned                    no expiry on key    detection on file-notify
  or shared PC to                                       rate per client (NFR-22)
  impersonate the                                       
  data-service                                          
  indefinitely                                          

  Attacker with    LOW--MEDIUM      HIGH --- silent     Auto-update with Ed25519
  physical access                   exfiltration of all signature verification
  replaces the                      SEM data and API    (RF-24); binary hash
  data-service                      key                 check at startup against
  binary with a                                         expected value published
  malicious                                             on admin panel; physical
  version that                                          access control (out of
  exfiltrates                                           scope, institutional)
  files or API key                                      

  Attacker with    LOW              HIGH --- all        Redis requirepass +
  network access                    revocations         network isolation to
  clears the Redis                  bypassed; full      Docker bridge only
  JWT blacklist,                    access control      (§5.5); Redis not
  re-enabling                       compromise          reachable from
  previously                                            institutional LAN
  revoked session                                       
  tokens and                                            
  data-service                                          
  keys                                                  
  ---------------- ---------------- ------------------- -------------------------

> **SCOPE:** SCOPE: This threat model explicitly excludes: nation-state
> attackers, ransomware targeting the server infrastructure, and
> supply-chain attacks on Go dependencies. These threats exist but are
> out of scope for a laboratory-scale deployment without dedicated
> security operations. A full per-component STRIDE analysis has been
> conducted separately and informs the security requirements in
> §11.2--§11.5 and NFR-21--NFR-24; the table above summarises the
> highest-priority residual threats only.

#################### 11.2 Credential & Secret Management

############################## API key storage on acquisition PCs --- mandatory requirements

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

############################## Memory hygiene

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

############################## Revocation procedure

If a PC is lost, stolen, decommissioned, or an operator suspects key
compromise, the following procedure must be executed immediately:

  ---------- ------------------------------ -----------------------------------
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
  ---------- ------------------------------ -----------------------------------

############################## Backend secret management

-   JWT signing key (RS256 private key): generated at deployment, stored
    as an environment variable or mounted secret --- never committed to
    version control. Key rotation procedure: generate a new RS256 key
    pair, add the new public key to the JWKS endpoint alongside the old
    one, update the private key secret, allow existing tokens to expire
    naturally (max 15 min for access tokens), then remove the old public
    key. In case of suspected key compromise, invalidate all active
    sessions immediately by flushing the JWT blacklist and rotating the
    key; all users and data-service clients will be required to
    re-authenticate.

Ed25519 signing key (binary release signing): the private key used to
sign data-service release binaries is a dedicated Ed25519 key pair,
separate from all JWT keys. Custody requirements: the private key must
be stored in a hardware security module (HSM) or, at minimum, in an
encrypted secrets vault (e.g. HashiCorp Vault, AWS Secrets Manager)
accessible exclusively from the CI/CD release pipeline. It must never be
stored on a developer workstation, a version control system, or a
general-purpose server. The corresponding public key is embedded in the
data-service binary at build time. Key rotation: if the private key is
suspected compromised, a new key pair must be generated, all existing
data-service installations must be updated via an out-of-band channel
(not the auto-update mechanism, which would require a valid signature
from the old key), and the old public key must be considered untrusted.
The release pipeline must log every signing operation with a timestamp
and the identity of the triggering build job.

-   Database credentials: stored in environment variables, injected via
    .env file (excluded from git) or a secrets manager (Vault, Docker
    secrets)

-   MinIO credentials: same pattern as DB credentials

-   bcrypt cost factor for API key hashing: 12 (default) --- reviewed if
    hardware changes significantly

-   REGISTRATION_SECRET: pre-shared secret that authorises new
    data-service registrations. Configured as a backend environment
    variable; never exposed via API. The data-service installer includes
    it out-of-band. The backend compares the value using a constant-time
    comparison to prevent timing attacks. Rotate by updating the env var
    and redistributing the new value to installers --- existing
    registered clients are unaffected.

#################### 11.3 Audit Logging

############################## Events logged

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

############################## Retention and access

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

############################## **Cryptographic Log Integrity (Log Chaining)**

The append-only constraint prevents modification via the application
service account but does not prevent tampering by a database superuser.
Each audit log entry therefore carries a hash_chain field:
HMAC-SHA256(previous_entry_hash \|\| entry_payload, chain_key). The
chain_key is a deployment secret stored in the secrets vault,
inaccessible to the application write role. Any deletion or modification
of a historical entry breaks the chain and is detectable by recomputing
hashes forward from genesis. The genesis hash is stored out-of-band
(e.g. in a separate institutional record) to bootstrap verification.
Chain integrity is verified weekly by an automated job; any break
triggers a SYSTEM_ADMIN alert.

############################## **External Verification and Chain of Custody**

External parties (scientific reviewers, auditors, collaborators) can
verify data integrity without access to internal systems via a
Verification Package. Generated on SYSTEM_ADMIN request, it contains:
(1) the FileEvent record including sha256, client_id, notified_at,
uploaded_at; (2) the corresponding audit log entries; (3) their
hash_chain values; (4) a signed manifest over items 1--3 using a
dedicated Ed25519 verification key pair, separate from the binary
signing key. The external party verifies the manifest signature using
the published public key and checks the sha256 against the file received
through other channels --- establishing chain of custody from
acquisition to delivery without exposing internal infrastructure.

For deployments requiring RFC 3161-compliant trusted timestamping (legal
or patent contexts), the platform optionally submits the sha256 of each
ingested file to a configured external Time Stamping Authority (TSA) at
ingestion time. The TSA token is stored in FileEvent.tsa_token (nullable
field, null when TSA integration is disabled).

#################### 11.4 Backup & Recovery

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

############################## PostgreSQL backup

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

  Encryption         Backup files encrypted at rest (AES-256) ---
                     mandatory regardless of storage location. The
                     encryption key must be stored separately from the
                     backup files (e.g. in a password manager or secrets
                     vault).
  ------------------ ----------------------------------------------------

############################## MinIO backup

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

############################## Recovery procedure (outline)

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

#################### 11.5 Patch & Update Management

############################## Server-side components

-   FastAPI backend, PostgreSQL, Redis, MinIO: managed via standard OS
    package manager or Docker image updates; follow upstream security
    advisories

-   Python dependencies: pip-audit run monthly in CI; critical
    vulnerabilities patched within 7 days

-   Go backend libraries (if any): govulncheck run monthly; critical
    vulnerabilities patched within 7 days

############################## Data-service binary on acquisition PCs

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
                 OS-level TLS libraries (uses Go's crypto/tls). Risk from
                 OS-level vulnerabilities is acknowledged and accepted for
                 this deployment context.
  -------------- ---------------------------------------------------------

############################## **Minimum Viable Hardening for Windows 7 Acquisition PCs**

Because Windows 7 acquisition PCs are outside managed IT perimeters and
receive no OS security updates, the following hardening checklist is
mandatory at installation time and must be re-verified at each
data-service binary update.

**Services to disable:** Windows Remote Registry (RemoteRegistry);
Server service (lanmanserver) --- disables SMB file sharing; Telnet
(tlntsvr) if present; Remote Desktop Services (TermService) unless
explicitly required; Windows Error Reporting (WerSvc); Secondary Logon
(seclogon). Disable via: sc config \[service\] start= disabled followed
by sc stop \[service\].

**OS keystore hardening:** The data-service runs as a dedicated Windows
Service account (not SYSTEM, not the logged-in user). The Credential
Manager entry for the API key (target name: autologbook-data-service) is
created under this service account using DPAPI user scope --- not
machine scope, which would allow any local user to read the credential.
The service account password is a random 32-character string set by the
installer and never disclosed to lab personnel.

**Network hardening:** Windows Firewall must be enabled. Inbound: block
all except ports required by the SEM instrument software (documented
per-deployment). Outbound: allow only HTTPS (443) to the backend server
IP; block all other outbound traffic. This prevents the data-service
from being used as a lateral movement pivot even if the PC is
compromised.

**User accounts:** The default Administrator account must be renamed and
its password changed to a random value stored by IT. Lab operators must
use standard (non-administrator) accounts. The data-service service
account must not be a member of the Administrators group. The Guest
account must be disabled.

**Residual risk acknowledgement:** These measures reduce but do not
eliminate risk from an unpatched OS. The residual risk --- primarily
kernel-level exploits and unpatched SMB vulnerabilities --- is accepted
as a deployment constraint given the operational infeasibility of
replacing Windows 7 PCs physically coupled to SEM instruments. This
acceptance must be documented in the deployment record and reviewed
annually.

############################## Go dependency vulnerability management

-   govulncheck is run against the data-service module on every release
    build

-   Critical CVEs in direct dependencies trigger an out-of-band patch
    release

-   The static binary eliminates runtime dependency on OS libraries ---
    the attack surface is limited to the Go standard library and
    declared module dependencies

#################### 11.6 GDPR --- Minimal Compliance

The platform processes a limited set of personal data. There are no
special category data (no health data, no biometric data). The
deployment is on-premise within the EU. No data is transferred to third
countries.

  ---------------- ------------------------------ ---------------- -----------------------
  **Data           **Where stored**               **Legal basis**  **Retention**
  category**                                                       

  User accounts    PostgreSQL users table         Legitimate       Duration of
  (name, email,                                   interest ---     employment + 6 months
  institutional                                   necessary to     
  ID)                                             operate access   
                                                  control          

  Operator name on PostgreSQL protocols table     Legitimate       Duration of data
  protocols                                       interest ---     retention policy
  (responsible                                    scientific       (institution-defined;
  field)                                          record-keeping   no mandatory period
                                                                   applies here ---
                                                                   recommended minimum 5
                                                                   years for research
                                                                   data)

  Audit log        PostgreSQL audit_log table     Legitimate       12 months (§10.3)
  (user_id,                                       interest --- IT  
  ip_address,                                     security         
  timestamps)                                                      

  Data-service     PostgreSQL                     Legitimate       Duration of client
  client IP        DataServiceClient.ip_address   interest --- IT  registration; deleted
  address                                         security         on client removal
  ---------------- ------------------------------ ---------------- -----------------------

############################## Data subject rights

-   Right of access: SYSTEM_ADMIN can export all personal data
    associated with a user account on request

-   Right to erasure: user accounts can be deleted; operator names on
    protocols are replaced with \'\[Deleted User\]\' to preserve
    scientific record integrity; audit log entries are retained for the
    full 12-month period even after account deletion (legitimate
    interest override)

-   Right to rectification: username and email editable by SYSTEM_ADMIN

############################## No data transfers outside EU

-   MinIO runs on-premise --- no data leaves the institution

-   No third-party analytics, telemetry or cloud services are used by
    the platform

-   If a cloud MinIO / S3 endpoint is configured in future, a GDPR
    transfer impact assessment is required before activation

########## 12. Future Extension Points

This chapter describes planned integration directions that are not part
of the current implementation scope. They are documented here to ensure
architectural decisions made today do not foreclose these options. None
of the items in this chapter represent functional requirements.

#################### 12.1 Additional Media Types (e.g. Spectroscopy)

The system is designed to support media types beyond electron microscopy
images. The plugin architecture of the ingestion pipeline (RF-01) and
the ProtocolItem mixin (§1.0) make this extension path straightforward.

############################## Extension mechanism

-   New entity type inheriting ProtocolItem (e.g. SpectroscopySpectrum)
    with domain-specific fields (wavenumber range, acquisition mode,
    baseline correction params)

-   New PictureType values registered in the \_am_i_right() chain or a
    parallel detection chain for non-image data

-   New metadata extractor handler registered at pipeline Level 2 with
    an appropriate guard

-   New derivative types if applicable (e.g. spectrum plot PNG, peak
    table CSV)

############################## Frontend viewer extension

The Content Area in the Protocol Workspace currently dispatches on
element type to the appropriate viewer (DZI image viewer, video player,
PDF viewer). This dispatch should be formalised as a viewer registry: a
map of element_type → React component. A new media type requires
registering a new viewer component without modifying the Content Area
layout logic.

-   Viewer registry: { MICROSCOPE_PICTURE: DeepZoomViewer, VIDEO:
    VideoPlayer, SPECTROSCOPY: SpectrumViewer, \... }

-   Each viewer receives the entity record and its derivatives as props

-   Viewers are lazy-loaded --- new media types do not increase the
    initial bundle size

> **DESIGN NOTE:** This extension point does not require backend API
> changes beyond adding the new entity endpoints. The Protocol, Sample,
> and ProtocolItem structures are media-type-agnostic.

#################### 12.2 LIMS Integration --- Measurement Request Workflow

A Laboratory Information Management System (LIMS) layer would allow
external users or internal groups to request measurements, have them
approved by a lab manager, and have protocols created automatically.
This is a significant workflow extension that should be implemented as
an optional module, not embedded in the core.

############################## Proposed entities

  ----------------------- -----------------------------------------------
  **Entity**              **Description**

  MeasurementRequest      A request for a measurement: requested_by (User
                          or external email), sample_description,
                          requested_technique (SEM, TEM, etc.), priority,
                          status (PENDING / APPROVED / REJECTED /
                          COMPLETED)

  RequestApproval         Approval record: approved_by (MANAGER),
                          approved_at, assigned_operator_id,
                          resulting_protocol_id
  ----------------------- -----------------------------------------------

############################## Workflow

-   1\. Requester submits MeasurementRequest via a simplified request
    form (separate UI route, no access to protocol internals)

-   2\. UNIT_MANAGER receives notification; reviews request; approves
    with assignment of operator and pre-set protocol parameters
    (visibility, microscope type)

-   3\. On approval: system automatically creates Protocol with
    status=DRAFT, operator=assigned_operator, contacts pre-populated
    from request, visibility set by manager

-   4\. Operator receives notification; performs acquisition; closes
    acquisition when complete

-   5\. Manager or operator marks protocol as complete; requester is
    notified; access granted according to pre-set visibility

############################## Access constraints for commissioned protocols

-   Operators assigned via the LIMS workflow cannot change protocol
    visibility --- it was set by the manager at approval time

-   Operators cannot delete a commissioned protocol --- only MANAGER or
    SYSTEM_ADMIN can

-   This is enforced via a protocol.commissioned: bool flag that
    triggers stricter UnitPolicy evaluation regardless of unit settings

> **DESIGN NOTE:** The LIMS module communicates with the core system
> exclusively via the existing Protocol API (RF-06) and UnitPolicy
> (§1.16). No core system changes are required to add this module --- it
> is additive only.

#################### 12.3 API-First Extension Pattern

Both extension points above follow the same pattern: new functionality
is implemented as a separate module that calls the existing API, not as
changes to the core. This keeps the core system stable and makes each
extension independently deployable and removable. The autologbook API is
the integration surface; the core does not need to know about its
consumers.

#################### **11.7 Security Design Rationale**

This section documents the rationale behind each significant security
design decision in autologbook, tracing each decision to the STRIDE
threat it mitigates and to the literature that informed it. It is
intended as a reference for security reviewers, thesis examiners, and
future maintainers.

############################## **Data Flow Diagrams (Level 1)**

**DFD-1 --- Ingestion flow:** Acquisition PC \[unmanaged OT endpoint\] →
filesystem event → data-service → HTTPS/TLS 1.2+, Bearer JWT, port 443 →
\[institutional network boundary\] → Nginx (TLS termination) → plain
HTTP loopback → FastAPI → Celery → MinIO \[S3 API, Docker bridge only\].
Secrets in transit: session_token (memory only); context_id
(HMAC-protected). Key attack surfaces on this flow: TLS channel (Canale
S1/T1), context_id forgery (Canale E1), Pillow TIFF processing (Backend
D1).

**DFD-2 --- M2M authentication:** data-service startup → OS keystore
(DPAPI user scope, local IPC) → api_key in memory → POST
/api/v1/data-service/auth \[HTTPS port 443\] → backend bcrypt verify →
session_token JWT RS256 8h → data-service memory. api_key zeroed after
auth. Key attack surfaces: api_key from keystore (DS I1), static key no
expiry (DS S1), Redis blacklist erasure (PG+Redis T2).

**DFD-3 --- Browser user flow:** Browser \[uncontrolled endpoint\] →
HTTPS port 443 → Nginx → FastAPI (JWT in httpOnly cookie, RLS-filtered
DB queries) → PostgreSQL. File access: FastAPI generates pre-signed URL
TTL 15 min → browser → MinIO \[Docker bridge only, not LAN-reachable\].
Key attack surfaces: XSS via user fields (Browser T1), pre-signed URL
sharing (Backend I2).

**DFD-4 --- Internal data stores:** FastAPI service account (limited
role, no SUPERUSER) → PostgreSQL \[port 5432, Docker bridge, RLS
enforced, audit INSERT-only\]. FastAPI → Redis \[port 6379, Docker
bridge, requirepass, JWT blacklist + Celery broker\]. FastAPI/Celery →
MinIO \[S3 API, Docker bridge\]. All three stores inside container
network trust boundary; no external access. Key attack surfaces: Redis
bypass (PG+Redis T2/D1), DB superuser (PG+Redis E1), MinIO direct (MinIO
S1/I1).

############################## **Threat-to-Control Mapping**

  ---------------- ----------------------- ---------- -----------------------
  **STRIDE         **Control Implemented** **SRS      **Literature Basis**
  Threat**                                 Ref**      

  DS S1 --- API    bcrypt cost 12; OS      §§11.2,    He et al. (IEEE Access,
  key              keystore DPAPI user     8.1,       2018); RFC 8705 (IETF,
  impersonation    scope; Redis blacklist; NFR-22     2020); Brossard &
                   rate limiting on /auth             Rjaskova (IEEE S&P,
                   (NFR-22)                           2012)

  DS T1 --- Binary Ed25519 release         §§RF-24,   FIDO FDO Spec (2021);
  tampering        signature; signing key  11.2, 11.5 Schmittner et al.
                   in HSM/vault; Windows              STRIDE-LM (2022)
                   Firewall egress to                 
                   backend IP only                    

  MinIO T1 ---     FileEvent.sha256 at     §§1.11,    W3C PROV (2013);
  Silent           ingestion; MinIO        11.3, 5.5  Buneman et al. (2000);
  post-ingestion   network isolation;                 Stodden et al.
  file             Verification Package;              (Science, 2016); Iqbal
  modification     optional RFC 3161 TSA              (2023)

  PG+Redis T2 ---  Redis requirepass;      §§5.5,     ISO/IEC 27001:2022
  Blacklist bypass Docker bridge           5.6,       A.8.20; NIST SP 800-82
                   isolation; short JWT    NFR-24     Rev.3 (2023)
                   TTL limits blast radius            

  Browser T1 ---   DOMPurify allowlist;    §NFR-23,   OWASP Top 10 A03
  XSS via          extra_info plain-text   5.6        (2021); Jalali & Kaiser
  user-supplied    only; CSP blocks inline            (JMIR, 2018)
  fields           scripts; JWT in                    
                   httpOnly cookie                    

  Audit log R1 --- HMAC-SHA256 hash chain; §§11.3     Iqbal DFET (2023);
  Tampered log     chain_key in vault;                ISO/IEC 27001:2022
                   weekly verification;               A.8.12; Sandve et al.
                   genesis hash                       (PLOS, 2013)
                   out-of-band                        
  ---------------- ----------------------- ---------- -----------------------

############################## **Key Design Decisions and Rationale**

**Decision 1 --- API key + session JWT over certificate-based M2M.** RFC
8705 Mutual-TLS and FIDO FDO provide stronger M2M authentication
guarantees but require PKI infrastructure or hardware TEE support
unavailable on Windows 7. The adopted pattern --- long-lived API key in
OS keystore exchanged for a short-lived session JWT --- follows OAuth
2.0 Client Credentials semantics without external infrastructure. The
acknowledged tradeoff is that the API key has no expiry, making
revocation the primary security control, and motivating future work on
automatic key rotation.

**Decision 2 --- Server-side SHA-256 at ingestion over end-to-end file
signing.** End-to-end signing requires per-device key pairs,
reintroducing the PKI problem. SHA-256 computed server-side proves the
file has not changed since ingestion but does not prove origin. This
scope is sufficient for scientific reproducibility and forensic
readiness per the W3C PROV wasGeneratedBy model, and is the pragmatic
choice given deployment constraints.

**Decision 3 --- HMAC hash chain over immutable log storage.**
Write-once storage (S3 Object Lock, WORM) and blockchain-based audit
logs provide stronger tamper evidence but require infrastructure changes
incompatible with a university lab deployment. The HMAC hash chain over
a standard PostgreSQL table is deployable with no infrastructure changes
and is verifiable externally given the genesis hash. Residual risk --- a
party with both DB superuser access and the chain_key could rewrite the
chain --- is accepted and documented.

**Decision 4 --- Security-by-design over security-by-policy.** Jalali
and Kaiser (2018) and CISA (2021) document that security policies in
non-IT-specialist environments are routinely ignored when they create
friction. Throughout autologbook the secure behaviour is therefore the
default: the installer writes the API key to the OS keystore
automatically; the JWT is stored in an httpOnly cookie without requiring
developer discipline; the Windows Firewall egress rule is applied by the
installer script. Where this principle was not fully achieved --- the
Windows 7 hardening checklist in §11.5 still requires manual steps ---
the residual risk is explicitly documented.
