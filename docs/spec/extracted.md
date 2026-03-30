**autologbook**

**Web Platform**

**Software Requirements Specification**

**& Architecture Document**

Version 2.1 --- Review-Amended

2026-03-27

  -----------------------------------------------------------------------
  **Property**                        **Value**
  ----------------------------------- -----------------------------------
  Status                              Draft --- Review-Amended

  Source                              autologbook v0.1.8
                                      (reverse-engineered)

  Changes vs v2.0                     RF-14 (post-ingestion correction);
                                      ImageDerivative model; per-image
                                      calibration for Multi;
                                      acquisition_status flag; agent path
                                      contract; XL40 multiframe debounce
                                      spec; local folder decoupling
  -----------------------------------------------------------------------

> **1. Domain Model --- Core Entities**

This section documents the core business entities derived from
reverse-engineering autologbook v0.1.8. Qt-specific references (signals,
slots, QThread) have been omitted. All entities are expressed as data
structures independent of any UI or transport layer.

v2.1 changes: ImageDerivative sub-entity replaces flat URL fields on
MicroscopePicture; acquisition_status added to Protocol; per-image
calibration_config replaces global ExperimentConfiguration flags;
sample_path contract added to Section 1.7.

**1.1 MicroscopePicture**

The central domain object. Detection always runs server-side immediately
after file receipt --- the client never sends a separate detection
request.

**Base fields**

  ----------------------------------------------------------------------------
  **Field**               **Type**                  **Description**
  ----------------------- ------------------------- --------------------------
  id                      int                       DB sequence (replaces
                                                    legacy class-level
                                                    \_used_ids registry)

  storage_key             string                    Object-storage path
                                                    (replaces local filesystem
                                                    path)

  original_filename       string                    Filename as provided by
                                                    the agent

  sample_path             string                    Relative path from
                                                    protocol root, e.g.
                                                    SampleA/SubB ---
                                                    authoritative source for
                                                    sample hierarchy

  picture_type            enum PictureType          Instrument type, detected
                                                    server-side by
                                                    MicroscopePictureFactory

  params                  JSONB                     Dynamic metadata bag:
                                                    magnification, HV, WD,
                                                    pixel size, etc.

  derivatives             List\[ImageDerivative\]   Generated file variants
                                                    --- see below (replaces
                                                    flat URL fields in v2.0)

  caption                 string                    User-supplied caption

  description             string                    User-supplied description

  extra_info              string                    User-supplied additional
                                                    information

  has_metadata            bool                      False for VEGA JPEG before
                                                    .hdr sidecar arrives

  calibration_config      CalibrationConfig         Per-image calibration
                                                    settings --- see Section
                                                    1.7

  processing_status       enum                      PENDING / PROCESSING /
                                                    DONE / ERROR

  created_at              datetime                  Acquisition timestamp from
                                                    TIFF tags or file stat

  updated_at              datetime                  Last processing timestamp
  ----------------------------------------------------------------------------

**ImageDerivative sub-entity**

Replaces the flat thumbnail_url, fullsize_png_url, dzi_base_url and
cropped_storage_key fields present in v2.0. Storing derivatives as a
typed list keeps the MicroscopePicture entity clean of infrastructure
details and allows new derivative types to be added without schema
migration.

  -----------------------------------------------------------------------
  **Field**               **Type**                **Description**
  ----------------------- ----------------------- -----------------------
  id                      UUID                    

  picture_id              int                     FK to MicroscopePicture

  derivative_type         enum                    THUMBNAIL /
                                                  FULLSIZE_PNG / DZI /
                                                  CROPPED / FRAME_PNG

  storage_key             string                  Object-storage path for
                                                  this derivative

  url                     string                  Pre-signed URL (15-min
                                                  TTL), refreshed on
                                                  request

  frame_index             int / null              Populated for FRAME_PNG
                                                  derivatives of XL40
                                                  multiframe images

  created_at              datetime                
  -----------------------------------------------------------------------

> **FRAME_PNG derivatives replace the params array of URLs used in v2.0
> for XL40 multiframe images. Each SE/BSE frame is a separate
> ImageDerivative with frame_index set.**

**PictureType enum --- detection order is critical**

The factory\'s \_am_i_right() chain must be registered in this exact
priority order. GENERIC must always be last.

  --------------------------------------------------------------------------------------------------------------------------------
  **Value**                                       **Instrument**          **Detection key**
  ----------------------------------------------- ----------------------- --------------------------------------------------------
  QUATTRO_MICROSCOPE_PICTURE                      FEI Quattro S           FEI tag 34680 (FEI_SFEG) + filename
                                                                          \^(?P\<ID\>\[0-9\]+)\[\\w\\W\]\*\$

  VERSA_MICROSCOPE_PICTURE                        FEI Versa 3D            FEI tag 34680 + filename
                                                                          \^\[\\w\\W\]\*\[-\_\](?P\<ID\>\[0-9\]+).\[\\w\\W\]\*\$

  FEI_MICROSCOPE_PICTURE                          Generic FEI             FEI tag 34680 or 34682 (FEI_HELIOS), no filename match

  VEGA_MICROSCOPE_PICTURE                         TESCAN Vega TIFF        Proprietary TIFF tag 50431 (VEGA_TIFFCODE)

  VEGA_JPEG_MICROSCOPE_PICTURE                    TESCAN Vega JPEG        JPEG format + piexif MakerNote or .hdr sidecar

  XL40_MICROSCOPE_PICTURE                         Philips XL40            XMPMETA XML in TIFF IFD, single frame

  XL40_MULTIFRAME_MICROSCOPE_PICTURE              Philips XL40            XMPMETA + multi-page TIFF (SE + BSE)

  XL40_MULTIFRAME_WITH_STAGE_MICROSCOPE_PICTURE   Philips XL40            Multi-page + stage XMP elements

  XL40_WITH_STAGE_MICROSCOPE_PICTURE              Philips XL40            Single frame + stage XMP elements

  GENERIC_MICROSCOPE_PICTURE                      Unknown                 Fallback --- \_am_i_right() always True, registered last
  --------------------------------------------------------------------------------------------------------------------------------

**Variant-specific params fields**

**FEI / Quattro / Versa**

-   magnification --- calculated as display_width /
    horizontal_field_of_view

-   high_voltage (kV), working_distance (mm), horizontal_field_of_view
    (µm)

-   pixel_width, pixel_height (nm), detector_mode (SE/BSE/etc.),
    dwell_time (µs)

-   system_type: \'Quattro S\' or \'Versa 3D\'

-   fei_tag_code: FEI_SFEG (34680) or FEI_HELIOS (34682)

-   acquisition_date --- from FEI proprietary tag, not file mtime

**VEGA / TESCAN**

-   pixel_size_x, pixel_size_y --- from TIFF tag 50431 via
    VegaMetadataParser.pattern_dict

-   All standard SEM params decoded via regex-based MetadataDecoder
    chain

-   For JPEG: metadata sourced from piexif MakerNote or companion .hdr
    plain-text sidecar

**XL40 / Philips**

-   All metadata from XMPMETA XML via XMPMixin.find_xmp_element()

-   stage_x, stage_y, stage_z, stage_tilt, stage_rotation (WithStageInfo
    variants)

-   frame_count --- number of pages in multi-page TIFF (one per
    detector)

-   No databar crop: acquisition parameters are rasterised directly onto
    image pixels

**1.2 Sample**

Hierarchical container. The sample hierarchy is derived exclusively from
the sample_path field sent by the agent with each file. The server
creates all intermediate parent nodes automatically via the
check_and_add_parents() logic (see RF-01).

  ----------------------------------------------------------------------------------
  **Field**               **Type**                    **Description**
  ----------------------- --------------------------- ------------------------------
  id                      UUID                        

  protocol_id             UUID                        Parent protocol

  full_name               string                      Hierarchical path, e.g.
                                                      SampleA/SubB/SubC --- matches
                                                      agent sample_path

  last_name               string                      Leaf node name only

  parent_id               UUID / null                 null = top-level sample

  description             string                      User-supplied

  microscope_pictures     List\[MicroscopePicture\]   

  videos                  List\[Video\]               

  optical_images          List\[OpticalImage\]        

  attachments             List\[Attachment\]          

  subsamples              List\[Sample\]              Recursive --- access rules
                                                      propagate down

  sample_visibility       enum                        Inherits from Protocol. Can be
                                                      overridden to RESTRICTED.

  sample_allowed_users    List\[UUID\]                Populated when
                                                      sample_visibility=RESTRICTED
  ----------------------------------------------------------------------------------

**1.3 Protocol**

Root document for a complete SEM analysis session. The Protocol IS the
logbook entry --- there is no external ELOG server. Two orthogonal state
fields are now distinguished: status (authorisation/edit lock) and
acquisition_status (whether the agent is still active).

  -------------------------------------------------------------------------
  **Field**               **Type**                  **Description**
  ----------------------- ------------------------- -----------------------
  id                      UUID                      

  protocol_number         int                       Unique numeric ID ---
                                                    application-managed
                                                    sequence

  project                 string                    Project name

  responsible             string                    Operator name

  microscope_type         enum                      Quattro / Versa / Vega
                                                    / XL40 / Multi

  introduction            text                      Rendered in HTML only
                                                    if non-empty

  conclusion              text                      Rendered in HTML only
                                                    if non-empty

  samples                 List\[Sample\]            Ordered, hierarchical

  optical_images          List\[OpticalImage\]      Project-level

  attachments             List\[Attachment\]        Project-level

  navigation_images       List\[NavigationImage\]   Quattro only --- navcam
                                                    images

  status                  enum                      DRAFT / ACTIVE / LOCKED
                                                    --- controls edit
                                                    authorisation

  acquisition_status      enum                      ONGOING / COMPLETED ---
                                                    see note below

  visibility              enum                      PUBLIC / UNIT /
                                                    RESTRICTED (see Section
                                                    3)

  owner_id                UUID                      User who created the
                                                    protocol

  unit_id                 UUID                      Organisational unit
                                                    (group) owning this
                                                    protocol

  allowed_users           List\[UUID\]              Explicit user-level
                                                    grants (RESTRICTED
                                                    protocols)

  yaml_customization      JSONB                     Merged customization
                                                    store (replaces .yaml
                                                    sidecar)

  html_cache              text                      Last rendered HTML ---
                                                    invalidated on any
                                                    protocol change

  html_rendered_at        datetime                  Timestamp of last HTML
                                                    render

  created_at              datetime                  

  updated_at              datetime                  
  -------------------------------------------------------------------------

> **KEY CHANGE v2.1: Two separate state fields. \'status\' controls who
> can edit the logbook (DRAFT/ACTIVE/LOCKED --- maps to legacy Edit
> Lock). \'acquisition_status\' indicates whether the agent is still
> pushing files (ONGOING/COMPLETED) and is orthogonal to authorisation.
> A LOCKED protocol can still be ONGOING if the operator forgot to stop
> the agent.**
>
> **acquisition_status=COMPLETED is set automatically when the agent
> disconnects cleanly (sends a POST
> /api/v1/protocols/{id}/close-session) or after a configurable idle
> timeout (e.g. 2 hours without new files). The UI shows a banner:
> \'Acquisition in progress\' / \'Acquisition completed\'.**

**1.4 Attachment**

  -----------------------------------------------------------------------
  **Field**               **Type**                **Description**
  ----------------------- ----------------------- -----------------------
  id                      UUID                    

  protocol_id / sample_id UUID                    Owner --- project-level
                                                  or sample-level

  storage_key             string                  Object-storage path

  original_filename       string                  

  file_size               int                     bytes

  attachment_type         enum                    GENERIC (link only) /
                                                  UPLOAD (embedded in
                                                  protocol page)

  caption                 string                  

  description             string                  

  extra_info              string                  
  -----------------------------------------------------------------------

**1.5 OpticalImage / NavigationImage / Video**

Lightweight entities sharing the same caption / description / extra_info
customization fields as MicroscopePicture. OpticalImageType enum:
GENERIC / KEYENCE / DIGITAL_CAMERA / DIGITAL_CAMERA_WITH_GPS.
NavigationImage is Quattro-only. All carry the same access control
fields as MicroscopePicture.

**1.6 ExperimentConfiguration**

Replaces the legacy .exp / .ini file. Persisted in the database,
downloadable as JSON for agent configuration. v2.1 change:
auto_calibration and databar_removal flags removed from this entity ---
they are now per-image in CalibrationConfig (see 1.7).

  -----------------------------------------------------------------------
  **Field**               **Type**                **Description**
  ----------------------- ----------------------- -----------------------
  id                      UUID                    

  protocol_id             UUID                    FK to Protocol

  microscope_type         enum                    

  watch_folder            string                  Path on acquisition PC
                                                  (agent only --- not
                                                  used server-side)

  remote_storage_bucket   string                  Object storage
                                                  destination

  mirroring_enabled       bool                    Whether agent mirrors
                                                  to remote storage

  thumbnail_max_width     int                     Default 400px

  operator                string                  

  idle_timeout_minutes    int                     After this period with
                                                  no new files,
                                                  acquisition_status →
                                                  COMPLETED. Default 120.
  -----------------------------------------------------------------------

> **The local watch_folder path is stored for documentation only. The
> server never uses it. The sample hierarchy is derived entirely from
> the sample_path field the agent sends per file, not from the local
> folder structure.**

**1.7 CalibrationConfig (new in v2.1)**

Extracted from ExperimentConfiguration to resolve the Multi-microscope
pipeline gap. In a Multi protocol, files from FEI and XL40 instruments
may arrive interleaved. A single global auto_calibration flag cannot
determine which algorithm to apply. CalibrationConfig is resolved per
MicroscopePicture based on its detected picture_type.

  -----------------------------------------------------------------------
  **Field**               **Type**                **Description**
  ----------------------- ----------------------- -----------------------
  picture_type            enum PictureType        Which instrument type
                                                  this config applies to

  auto_calibration        bool                    Run calibration task
                                                  for this instrument
                                                  type

  databar_removal         bool                    FEI only --- run
                                                  crop_databar task

  calibration_algorithm   enum                    FEI_TAG /
                                                  VEGA_PIXEL_SIZE /
                                                  XL40_XMP --- resolved
                                                  automatically from
                                                  picture_type
  -----------------------------------------------------------------------

ExperimentConfiguration holds a List\[CalibrationConfig\], one entry per
instrument type expected in the session. During ingestion, the pipeline
selects the matching CalibrationConfig by picture_type. For a Multi
protocol this means the chain may apply FEI calibration to one file and
XL40 calibration to the next.

> **Example Multi session: CalibrationConfig\[QUATTRO\] =
> {auto_calibration: true, databar_removal: false},
> CalibrationConfig\[XL40\] = {auto_calibration: true, databar_removal:
> false}. VEGA files arriving in the same session use
> CalibrationConfig\[VEGA\] if defined, or skip calibration if not.**
>
> **2. Functional Requirements --- Backend & Business Logic**

All heavy processing runs asynchronously via Celery. HTTP endpoints
return immediately with a task_id. Image type detection always happens
server-side as the first step of the ingestion pipeline --- no separate
client request is needed or allowed.

**2.1 RF-01 --- Unified Server-Side Ingestion Pipeline**

> **ARCHITECTURE DECISION: The client sends the raw file once.
> Detection, storage, metadata extraction and thumbnail generation are
> all steps in a single server-side pipeline. There is no \'detect
> type\' client call. File ingestion is exclusively agent-driven.
> Post-ingestion reassignment of elements to different samples is
> possible via the UI (see RF-14) --- but file content is never uploaded
> or reordered manually.**

Triggered by: agent POST to /api/v1/ingest with fields: protocol_id
(authenticated via scoped token), sample_path (mandatory --- relative
path from protocol root), and the file binary.

**Pipeline steps (Celery chain)**

-   Step 1 --- Receive raw bytes; persist to object storage under a
    temporary key

-   Step 2 --- FileTypeGuesser: guess ElementType (MICROSCOPE_PICTURE /
    VIDEO / OPTICAL_IMAGE / ATTACHMENT) from filename regex via
    RegexpRepository

-   Step 3 --- MicroscopePictureFactory.guess_type(): open file with
    Pillow, run \_am_i_right() chain (Quattro → Versa → FEI → VEGA →
    XL40 → GENERIC)

-   Step 4 --- Metadata extraction (RF-02)

-   Step 5 --- Move object to final storage key:
    {protocol_id}/{sample_path}/{filename}

-   Step 6 --- Thumbnail & PNG generation (RF-03); generate
    ImageDerivative records

-   Step 7 --- Select CalibrationConfig by picture_type; run calibrate
    task (RF-04) if auto_calibration=True

-   Step 8 --- Run crop_databar task (RF-05) if databar_removal=True in
    selected CalibrationConfig

-   Step 9 --- check_and_add_parents(): create missing Sample nodes from
    sample_path

-   Step 10 --- Protocol HTML re-render (debounced, at most once per 10
    minutes)

> chain( receive_and_store.s(raw, sample_path), guess_type.s(),
> extract_metadata.s(), move_to_final.s(), generate_derivatives.s(), \#
> creates ImageDerivative records select_and_calibrate.s(), \# uses
> CalibrationConfig by picture_type
> check_and_add_parents.si(protocol_id, sample_path),
> render_protocol_html.si(protocol_id) ).apply_async()
>
> **Multi-microscope sessions: select_and_calibrate resolves
> CalibrationConfig by the picture_type detected in Step 3. Each image
> is calibrated independently. No global flag is applied uniformly
> across the session.**

**2.2 RF-02 --- Metadata Extraction**

Per picture type, extract all instrument-specific params and persist
them in the JSONB params column.

-   FEI: read proprietary tags, compute magnification = display_width /
    horizontal_field_of_view

-   VEGA TIFF: parse VegaMetadataParser from TIFF tag 50431 using regex
    MetadataDecoder chain

-   VEGA JPEG: parse piexif MakerNote; if .hdr sidecar absent, set
    has_metadata=False and schedule re-processing via
    embed_vega_jpeg_metadata task when sidecar arrives

-   XL40: parse XMPMETA XML via XMPMixin.find_xmp_element(); handle
    multi-page TIFF frames

**2.3 RF-03 --- Thumbnail and Derivative Generation**

All generated files are persisted as ImageDerivative records, replacing
the flat URL fields from v2.0.

-   THUMBNAIL: PNG at max_width=400px (configurable per
    ExperimentConfiguration)

-   FULLSIZE_PNG: full-size PNG conversion; 16-bit TIFF applies numpy
    intensity normalisation

-   DZI: Deep Zoom Image tile set via libvips for images \>10 megapixels

-   FRAME_PNG: one derivative per frame for XL40 multiframe (frame_index
    set); replaces the params URL array from v2.0

-   Idempotent: skip if derivative already exists in object storage
    (force_regen=False default)

**2.4 RF-04 --- Image Calibration**

Algorithm is selected per image based on picture_type via
CalibrationConfig --- not from a global ExperimentConfiguration flag.

-   FEI (FEI_TAG algorithm): compare ResolutionSource.TIFF_TAG vs
    ResolutionSource.FEI_TAG. If different, write corrected values to
    standard TIFF tags and persist updated file to object storage. Set
    params\[\'calibration_applied\'\]=True

-   VEGA (VEGA_PIXEL_SIZE algorithm): use pixel_size_x / pixel_size_y
    from tag 50431. Write corrected resolution to standard TIFF tags

-   XL40 (XL40_XMP algorithm): use resolution data from XMP metadata.
    Write corrected resolution

-   GENERIC: no calibration --- skip silently

-   If TIFF_TAG and FEI_TAG already match: no-op --- set
    calibration_applied=True without file modification

**2.5 RF-05 --- FEI Databar Removal**

-   Detect databar height from image data

-   Save cropped version as CROPPED ImageDerivative (replaces
    cropped_storage_key field from v2.0)

-   Original is never overwritten --- both original and CROPPED
    derivative coexist

-   Controlled by databar_removal field in the QUATTRO/VERSA/FEI
    CalibrationConfig entry

**2.6 RF-06 --- Protocol CRUD**

  --------------------------------------------------------------------------
  **Endpoint**                           **Description**
  -------------------------------------- -----------------------------------
  POST /api/v1/protocols                 Create protocol, assign
                                         protocol_number from DB sequence

  GET /api/v1/protocols/{id}             Retrieve with all nested data

  PATCH /api/v1/protocols/{id}           Update intro, conclusion, status,
                                         visibility, acquisition_status

  POST                                   Agent calls this on clean shutdown
  /api/v1/protocols/{id}/close-session   → sets acquisition_status=COMPLETED

  POST /api/v1/protocols/{id}/samples    Add a sample (server creates parent
                                         chain from path)

  DELETE                                 Remove sample, cascade-remove empty
  /api/v1/protocols/{id}/samples/{sid}   parents

  GET /api/v1/protocols/{id}/render      Return rendered HTML --- from cache
                                         if valid

  GET /api/v1/protocols                  Search/list with SQL-level
                                         visibility filter
  --------------------------------------------------------------------------

**2.7 RF-07 --- Protocol Customization**

caption, description, extra_info fields live directly on each entity
record. PATCH on any element updates the field and invalidates the HTML
cache. The YAMLRecycler logic (preserving custom fields on item
move/rename) is a server-side service operation triggered by RF-14.

**2.8 RF-08 --- Protocol HTML Rendering**

The backend renders the full protocol to HTML using Jinja2 templates
(ported from .yammy files). Output stored in html_cache. Cache is
invalidated on any protocol mutation. Rendering is debounced to at most
once every 10 minutes during active ingestion.

**2.9 RF-09 --- Automatic Ingestion Workflow**

> **ARCHITECTURE DECISION: File ingestion is exclusively agent-driven.
> There is no drag-and-drop interface and no manual file upload from the
> browser. The UI is read/annotate-only for file content. Post-ingestion
> corrections to sample assignment are handled by RF-14 (reassignment),
> not by re-uploading.**

The agent monitors the local acquisition folder and POSTs new files to
/api/v1/ingest. The server triggers the pipeline (RF-01). The UI updates
via WebSocket push. No user interaction is needed or possible for file
ingestion.

**2.10 RF-10 --- Integrated Logbook**

The application IS the logbook. There is no external ELOG dependency.

  -----------------------------------------------------------------------
  **Legacy ELOG feature**             **Web platform equivalent**
  ----------------------------------- -----------------------------------
  ELOG entry per protocol             Protocol record with rendered HTML
                                      page

  ELOG attributes (Operator, Protocol Protocol entity fields with
  ID, Project, Customer)              search/filter

  ELOG Edit Lock                      Protocol.status = LOCKED / ACTIVE
  (Protected/Unprotected)             

  Analysis Status field (On going /   Protocol.acquisition_status =
  Completed)                          ONGOING / COMPLETED

  ELOG message parent/child hierarchy Protocol page rendered natively ---
                                      no external tree

  ELOG page size limit (240 KB)       Not applicable --- server renders
                                      and serves natively

  ELOG search (Protocol ID, Project,  PostgreSQL full-text search on
  Customer)                           Protocol fields

  elog_post_splitter (large entry     Not needed --- native pagination in
  splitting)                          web renderer

  Write URL file                      Each protocol has a permanent
  (protocol-XXXXX-url.txt)            shareable URL

  ListLogbook (microscopy protocol    Protocol list view with filters ---
  list)                               same DB

  AnalysisLogbook per microscope      Protocol filtered by
                                      microscope_type

  Edit via ELOG web editor            Edit panel in Protocol Workspace
                                      (caption/description/extra_info)
  -----------------------------------------------------------------------

**2.11 RF-11 --- File Mirroring / Sync**

The agent handles mirroring from the acquisition PC to the configured
object storage bucket. The server never pulls files --- the agent always
pushes. Retry logic uses exponential backoff (tenacity: max_attempts=2,
wait=0.5s). GET /api/v1/protocols/{id}/storage-status returns which
files are present in object storage vs expected from the protocol tree.

**2.12 RF-12 --- New Experiment Wizard (API Flow)**

-   Step 1: GET /api/v1/protocols/next-number --- next available
    protocol_number from DB sequence

-   Step 2: POST /api/v1/protocols --- create Protocol, assign number,
    set unit_id from authenticated user, set acquisition_status=ONGOING

-   Step 3: GET /api/v1/protocols/{id}/agent-config --- download JSON
    config file for the acquisition PC agent

-   Step 4: Agent starts, reads config, begins monitoring local folder
    --- no further user action required

**2.13 RF-13 --- Labtools Endpoints**

-   POST /api/v1/tools/metadata --- dump all TIFF/EXIF/XMP metadata from
    an uploaded file as JSON

-   POST /api/v1/tools/fei/calibrate --- standalone FEI calibration on
    an uploaded file

-   POST /api/v1/tools/fei/crop-databar --- standalone databar removal

-   POST /api/v1/tools/convert --- convert TIFF to PNG/JPEG with
    optional resize

-   POST /api/v1/tools/fei/check --- detect FEI subtype (FEI_SFEG vs
    FEI_HELIOS)

**2.14 RF-14 --- Post-Ingestion Element Reassignment (new in v2.1)**

> **FUNCTIONAL GAP ADDRESSED: The legacy FileSystemCommander (gui.py)
> allowed operators to rename and move files after acquisition in case
> of errors (e.g. image saved in wrong sample folder). This capability
> must survive in the new system. It is implemented as a UI-driven
> server-side operation --- not a filesystem operation.**

An operator may discover after ingestion that an image was saved to the
wrong sample (e.g. SampleA instead of SampleB). The legacy system
allowed physical file rename/move via FileSystemCommander. In the web
system, this is a logical reassignment: the server updates the database
record and moves the object storage key. The local file on the
acquisition PC is not touched.

**Reassignment operations**

  ------------------------------------------------------------------------------
  **Operation**           **Endpoint**                   **Description**
  ----------------------- ------------------------------ -----------------------
  Move image to different PATCH                          Update sample_id and
  sample                  /api/v1/images/{id}/sample     storage_key; create
                                                         parent samples if
                                                         needed; preserve all
                                                         custom fields
                                                         (YAMLRecycler logic)

  Move image to different PATCH                          Restricted to
  protocol                /api/v1/images/{id}/protocol   UNIT_MANAGER or
                                                         SYSTEM_ADMIN only

  Rename image            PATCH                          Updates
                          /api/v1/images/{id}/filename   original_filename and
                                                         storage_key suffix;
                                                         does not touch the
                                                         object in storage (key
                                                         is internal)

  Remove image from       DELETE /api/v1/images/{id}     Soft-delete: marks as
  protocol                                               REMOVED, retains object
                                                         in storage for 30 days
                                                         before purge

  Move sample subtree     PATCH                          Reassign a sample and
                          /api/v1/samples/{id}/parent    all its contents to a
                                                         new parent; updates
                                                         full_name of all
                                                         descendants
  ------------------------------------------------------------------------------

**Constraints and rules**

-   Reassignment is only available while status != LOCKED

-   All custom fields (caption, description, extra_info) are preserved
    during reassignment (YAMLRecycler-equivalent server logic)

-   Reassignment triggers HTML cache invalidation on both source and
    destination protocols

-   Object storage key is updated atomically with the DB record: the
    server copies the object to the new key, updates the DB, then
    deletes the old key. No orphaned objects.

-   Agent tokens have no permission to call reassignment endpoints. Only
    user JWT tokens can.

-   Reassignment is recorded in the audit log with old and new sample
    path

**UI entry point (Protocol Workspace)**

-   Right-click any image in the Sample Tree → \'Move to sample\...\' →
    sample picker modal

-   Right-click any image → \'Remove from protocol\' → confirmation
    modal

-   Right-click any sample → \'Move subtree\...\' → sample picker modal

-   All reassignment operations are shown as transient progress banners;
    UI tree updates via WebSocket on completion

> **3. Access Control Model**

Access control operates at two levels: group (unit/department) and
individual user. This supports protocols with sensitive images that must
be invisible to the rest of the organisation. Reassignment operations
(RF-14) also respect this model.

**3.1 Principals**

  -----------------------------------------------------------------------
  **Principal**                       **Description**
  ----------------------------------- -----------------------------------
  User                                Individual authenticated account.
                                      Has a primary unit_id and
                                      optionally belongs to additional
                                      units.

  Unit                                Organisational group (e.g. a
                                      laboratory department). Has one or
                                      more Unit Managers.

  Role                                System-wide role: SYSTEM_ADMIN /
                                      UNIT_MANAGER / OPERATOR / READER
  -----------------------------------------------------------------------

**3.2 Protocol Visibility Levels**

  -----------------------------------------------------------------------
  **Level**                           **Who can see the Protocol**
  ----------------------------------- -----------------------------------
  PUBLIC                              All authenticated users in the
                                      system

  UNIT                                Only members of the protocol\'s
                                      owner unit (unit_id). Default.

  RESTRICTED                          Only the protocol owner + users
                                      explicitly listed in allowed_users.
  -----------------------------------------------------------------------

> **RESTRICTED protocols are completely invisible in search results to
> unauthorised users. No title, no metadata, no thumbnail leaks through
> any API endpoint.**

**3.3 Permission Matrix**

  ----------------------------------------------------------------------------------
  **Action**      **SYSTEM_ADMIN**   **UNIT_MANAGER   **OPERATOR     **READER (unit
                                     (own unit)**     (own           member)**
                                                      protocol)**    
  --------------- ------------------ ---------------- -------------- ---------------
  List PUBLIC     Y                  Y                Y              Y
  protocols                                                          

  List UNIT       Y                  Y (own unit)     Y (own unit)   Y (own unit)
  protocols                                                          

  List RESTRICTED Y                  Y (own unit)     Y (own)        N
  protocols                                                          

  View protocol   Y                  Y (own unit)     Y (own)        Y (if
  detail                                                             PUBLIC/UNIT)

  View RESTRICTED Y                  Y (own unit)     Y (own)        Only if in
  protocol                                                           allowed_users

  Create protocol Y                  Y                Y              N

  Edit protocol   Y                  Y (own unit)     Y (own)        N
  metadata                                                           

  Change protocol Y                  Y (own unit)     Y (own)        N
  visibility                                                         

  Add user to     Y                  Y (own unit)     Y (own)        N
  allowed_users                                                      

  Reassign image  Y                  Y (own unit)     Y (own)        N
  to different                                                       
  sample (RF-14)                                                     

  Reassign image  Y                  Y (own unit)     N              N
  to different                                                       
  protocol                                                           
  (RF-14)                                                            

  Lock/Unlock     Y                  Y (own unit)     Y (own)        N
  protocol                                                           

  Delete protocol Y                  Y (own unit)     N              N

  View any        Y                  N                N              N
  protocol                                                           
  (override)                                                         
  ----------------------------------------------------------------------------------

**3.4 Unit Membership Model**

-   A User has one primary unit_id (the department where they work)

-   A User can be added as a guest member to other units by a
    UNIT_MANAGER

-   UNIT-visibility protocols are visible to all members (primary or
    guest) of the owner unit

-   Membership changes propagate immediately --- queries are DB-backed,
    no cache to invalidate

**3.5 Sample-Level Sensitivity**

For cases where a protocol is UNIT-visible but contains one or more
samples with particularly sensitive images, sample-level overrides can
be set via the right-click context menu in the Sample Tree.

> **Sample-level RESTRICTED: the sample node and all its images are
> hidden. The protocol remains visible to unit members but the
> restricted sample appears as \'\[Confidential sample\]\' with no
> content or count visible.**

**3.6 API Enforcement**

-   All API endpoints check permissions via a dependency-injected
    AuthorizationService

-   Protocol list queries apply visibility filters at the SQL level via
    Row-Level Security (RLS) --- never post-filtered in application code

-   Object storage URLs are pre-signed with 15-minute TTL --- cannot be
    shared without re-authentication

-   Audit log: all access to RESTRICTED protocols logged (user,
    timestamp, endpoint, IP)

-   Reassignment operations (RF-14) written to audit log with old and
    new sample path

-   Agent tokens: per-protocol, scoped only to /api/v1/ingest and
    /api/v1/protocols/{id}/close-session

**3.7 Authentication**

-   JWT Bearer tokens (15 min) + refresh tokens (7 days)

-   Integration with institutional LDAP/Active Directory via
    oauth2-proxy or python-ldap

-   Fallback: local accounts for external collaborators not in the
    institutional directory

-   MFA optional --- enforced by SYSTEM_ADMIN per user or per unit

> **4. User Flows --- Web UI**

The UI is a read/annotate interface. File content enters the system
exclusively via the agent. Post-ingestion corrections (wrong sample
assignment, rename) are performed via the context menu in the Protocol
Workspace (RF-14).

**4.1 Flow 1 --- New Experiment**

**Step 1 --- Parameters**

-   Microscope type (Quattro / Versa / Vega / XL40 / Multi)

-   Operator (pre-filled from authenticated user, editable)

-   Project name, Customer

-   Visibility (PUBLIC / UNIT / RESTRICTED) --- default UNIT

-   If RESTRICTED: user search to pre-populate allowed_users

-   Protocol number: read-only, assigned by server on creation

**Step 2 --- Confirm & Download Agent Config**

-   Summary card with all parameters

-   \'Create experiment\' button → server creates Protocol
    (acquisition_status=ONGOING)

-   Download JSON config file for the acquisition PC agent

-   Agent install instructions shown inline (pip install
    autologbook-agent)

**Step 3 --- Workspace opens**

-   Protocol Workspace opens immediately --- empty, waiting for first
    file from agent

-   Acquisition status banner: \'Acquisition in progress --- awaiting
    agent connection\'

**4.2 Flow 2 --- Protocol Dashboard**

-   Search bar: full-text search across project, responsible,
    protocol_number, customer

-   Filter chips: microscope type, unit, date range, status,
    acquisition_status, visibility

-   Results grid: card per protocol (thumbnail of first image, protocol
    number, project, date, status chip, acquisition_status chip)

-   UNIT and RESTRICTED protocols of other units completely absent from
    results

-   Click card → Protocol Workspace

-   \'New experiment\' button → Flow 1

**4.3 Flow 3 --- Protocol Workspace**

Three-column layout replacing the legacy main window + protocol editor:

> ┌──────────────┬─────────────────────────────┬───────────────────┐ │
> Sample Tree │ Content Area │ Edit Panel │ │ │ │ │ │ ▼ Protocol │
> \[Image viewer / video / │ Caption │ │ ▼ SampleA │ attachment
> preview\] │ Description │ │ ▼ SubB │ │ Extra info │ │ img1 │
> \[Thumbnail strip\] │ │ │ img2 │ │ Metadata table │ │ Attachm. │
> \[Processing status banner\] │ (read-only) │ │ Opt.Imgs │ │ │ │
> Nav.Imgs │ \[Acquisition status bar\] │ \[Save\] │
> └──────────────┴─────────────────────────────┴───────────────────┘

**Left panel --- Sample Tree**

-   Collapsible tree, populated exclusively by agent pipeline (no manual
    add/reorder)

-   Status badges: image count, processing state (PENDING / DONE /
    ERROR)

-   RESTRICTED samples show as \'\[Confidential\]\' for unauthorised
    users

-   Context menu (authorised users): Move to sample, Rename, Remove from
    protocol, Restrict sample, Lock sample, View audit log

**Centre panel --- Content Area**

-   Deep-zoom image viewer (OpenSeadragon) using DZI tiles for images
    \>10 MP

-   Frame selector for XL40 multiframe: click to switch between
    FRAME_PNG derivatives (SE/BSE)

-   Video player for .mp4

-   Processing status banner: \'Calibrating\...\', \'Generating
    thumbnail\...\', \'Cropped version available\'

-   Acquisition status bar: \'Acquisition in progress / Acquisition
    completed (idle Xh ago)\'

-   Metadata accordion: human-readable params using pretty_fmt\_\*
    formatting

-   FEI Cropped/Original toggle: switch between original TIFF and
    CROPPED ImageDerivative

**Right panel --- Edit Panel**

-   caption (images and videos only ---
    CustomEditVisibilityFlag.CAPTION)

-   description, extra_info --- auto-save with debounce

-   Protocol-level introduction and conclusion: inline text areas at
    top/bottom of protocol view

**Top bar**

-   Protocol status chip (DRAFT / ACTIVE / LOCKED) + acquisition_status
    chip (ONGOING / COMPLETED)

-   Visibility chip (PUBLIC / UNIT / RESTRICTED) --- click to change if
    authorised

-   \'Preview full protocol\' → rendered HTML in new tab

-   \'Export HTML\' → download rendered protocol as standalone .html
    file

-   \'Lock protocol\' → sets status=LOCKED, disables all edits and
    reassignment

-   \'Mark acquisition complete\' → sets acquisition_status=COMPLETED
    (can also be automatic via idle timeout)

-   Agent connection status with last-seen timestamp

-   Real-time task progress (WebSocket-driven)

**4.4 Flow 4 --- Post-Ingestion Correction (RF-14)**

This flow covers the case where an image was acquired into the wrong
sample folder on the microscope PC and the agent has already pushed it
to the wrong sample in the system.

-   Operator right-clicks the misplaced image in the Sample Tree

-   Selects \'Move to sample\...\' → modal shows the full sample tree
    with a picker

-   Operator selects the correct target sample → clicks \'Move\'

-   Server: copies object to new storage key, updates DB record,
    preserves all custom fields, deletes old storage key, triggers HTML
    cache invalidation

-   UI: Sample Tree updates via WebSocket --- image appears in correct
    sample

-   Audit log entry written with old and new sample path

> **Reassignment is blocked if protocol status=LOCKED. The operator must
> unlock the protocol first (requires OPERATOR or UNIT_MANAGER role),
> perform the correction, then re-lock.**

**4.5 Flow 5 --- Sensitivity Management**

-   Protocol owner or UNIT_MANAGER can change visibility at any time
    while status != LOCKED

-   Changing to RESTRICTED: modal prompts to add allowed_users

-   Changing from RESTRICTED: modal warns images will become visible to
    unit

-   Sample-level: right-click sample → \'Restrict this sample\' → same
    allowed_users modal

-   Audit log panel (admin/manager only): all access events for
    RESTRICTED resources

**4.6 Flow 6 --- Labtools Standalone Page**

-   Metadata Viewer: upload TIFF/JPEG → display full metadata tree as
    JSON

-   FEI Tools: calibrate / crop-databar on individual files without
    creating a protocol

-   Image Converter: upload TIFF → configure output format/size →
    download

-   All labtools operations are stateless --- files are not persisted
    server-side

-   Access: any authenticated user (no unit restriction)

> **5. Architectural Proposal --- Stack & System Design**

**5.1 High-Level Architecture**

> ┌──────────────────────────────────────────────────────────────┐ │
> Browser (SPA) │ │ React 18 + TypeScript + TanStack Query │
> └──────────────────────────┬───────────────────────────────────┘ │
> HTTPS / REST + WebSocket
> ┌──────────────────────────▼───────────────────────────────────┐ │ API
> Gateway / Nginx (TLS termination) │
> └─────────┬────────────────────────────────────┬───────────────┘ │ │
> ┌─────────▼────────┐ ┌────────▼───────────────┐ │ FastAPI (ASGI) │◄──
> task dispatch─┤ Celery Workers │ │ Python 3.12 │ │ (image pipeline) │
> │ │◄── task results │ Pillow, numpy, libvips │ └─────────┬────────┘
> └────────┬───────────────┘ │ │
> ┌───────▼───────────────────────────────────▼──────┐ │ PostgreSQL │
> Redis (broker + cache) │
> └───────┬──────────────────────────────────────────┘ │
> ┌───────▼───────────────┐ │ Object Storage │ │ (MinIO / S3) │ │ TIFF,
> PNG, DZI tiles │ └───────────────────────┘ │ ┌───────▼───────────────┐
> │ autologbook-agent │ ← on acquisition PC │ (Python, watchdog) │
> └───────────────────────┘

**5.2 Backend --- FastAPI**

FastAPI allows direct reuse of the existing Python domain code (Pillow,
numpy, piexif, defusedxml, Jinja2) with minimal changes. The ASGI
runtime provides the non-blocking I/O needed for concurrent image
upload + processing.

**Key packages**

  -----------------------------------------------------------------------
  **Package**                         **Role**
  ----------------------------------- -----------------------------------
  fastapi + uvicorn                   ASGI server and HTTP framework

  sqlalchemy (async) + alembic        ORM with async drivers + migrations

  pydantic v2                         Entity schemas and settings
                                      management (replaces QSettings and
                                      .ini)

  celery + redis                      Task queue, broker and result
                                      backend

  Pillow, numpy, piexif, defusedxml   Image processing --- reused from
                                      legacy requirements unchanged

  libvips / pyvips                    Deep Zoom Image tile generation for
                                      large TIFF files

  Jinja2                              Protocol HTML rendering ---
                                      templates ported from .yammy files

  PyYAML                              Configuration and customization
                                      parsing

  python-multipart                    File upload handling

  boto3 / minio-py                    Object storage client

  python-jose                         JWT token creation and validation

  python-ldap / ldap3                 Institutional directory integration
                                      for authentication
  -----------------------------------------------------------------------

**Domain code reuse strategy**

Modules reusable with minimal changes (strip Qt imports, replace
filesystem paths with storage keys):

-   microscope_picture.py --- MicroscopePicture, FEIPicture,
    VegaPicture, XL40Picture, MicroscopePictureFactory

-   autotools.py --- PictureType, FEITagCodes, VegaMetadataParser,
    PictureResolution, all formatters

-   file_type_guesser.py --- ElementTypeGuesser, RegexpRepository (zero
    Qt dependencies)

-   attachment.py --- Attachment, AttachmentFactory, AttachmentType

-   Jinja2 templates (.yammy files) --- usable without modification

Modules to rewrite:

-   autowatchdog.py → Celery task chain + autologbook-agent (separate
    installable package)

-   autoprotocol.py → strip Qt signals, replace filesystem paths with
    storage keys, remove all ELOG calls

-   sample.py → strip Qt signals, map to SQLAlchemy async model

-   elog_interface.py → deleted entirely; no equivalent

-   autoconfig.py → Pydantic BaseSettings + .env file

-   expwizard/ → replaced by web wizard flow (RF-12)

**5.3 Task Queue --- Celery**

  ---------------------------------------------------------------------------
  **Task**                    **Trigger**             **Priority**
  --------------------------- ----------------------- -----------------------
  receive_and_store           Agent POST to /ingest   HIGH

  guess_type                  After receive_and_store HIGH

  extract_metadata            After guess_type        HIGH

  generate_derivatives        After extract_metadata  HIGH
                              --- creates             
                              ImageDerivative records 

  generate_dzi_tiles          After derivatives       MEDIUM
                              (images \>10 MP only)   

  select_and_calibrate        After derivatives ---   MEDIUM
                              resolves                
                              CalibrationConfig by    
                              picture_type            

  crop_databar                After calibration (if   MEDIUM
                              databar_removal=True in 
                              CalibrationConfig)      

  embed_vega_jpeg_metadata    .hdr sidecar arrival    HIGH
                              (VEGA JPEG only)        

  reassign_element            User RF-14 action via   HIGH
                              UI                      

  render_protocol_html        Any protocol change     LOW
                              (debounced 10 min)      

  mark_acquisition_complete   Agent close-session or  LOW
                              idle timeout expiry     
  ---------------------------------------------------------------------------

Tasks are chained: failure in extract_metadata marks the image as ERROR
and stops the chain. The agent is notified via WebSocket. Task results
persist in Redis with a 24-hour TTL.

**5.4 Frontend --- React SPA**

  -----------------------------------------------------------------------
  **Library**                         **Role**
  ----------------------------------- -----------------------------------
  React 18 + TypeScript               Core SPA framework

  TanStack Query                      Server state management and cache
                                      invalidation

  Zustand                             Local UI state (selected item,
                                      panel sizes, etc.)

  React Router v6                     Client-side routing

  Tailwind CSS + shadcn/ui            Component library

  OpenSeadragon                       Deep-zoom TIFF viewer using DZI
                                      tiles

  native WebSocket API                Real-time task progress and
                                      protocol/acquisition_status updates
  -----------------------------------------------------------------------

> **TIFF files from modern SEMs can exceed 500 MB. The viewer uses DZI
> tiling via OpenSeadragon --- the full file is never sent to the
> browser. The server generates DZI tile sets during ingestion via
> libvips.**

**5.5 Data Storage**

**PostgreSQL**

-   All domain entities (Protocol, Sample, MicroscopePicture,
    ImageDerivative, CalibrationConfig, User, Unit, AuditLog)

-   JSONB column for params on MicroscopePicture

-   Row-Level Security (RLS) policies enforce visibility at the database
    layer

-   Full-text search on project, responsible, description (tsvector
    index)

**Object Storage (MinIO / S3-compatible)**

-   Original TIFF and JPEG uploads

-   All ImageDerivative files: THUMBNAIL, FULLSIZE_PNG, DZI tiles,
    CROPPED, FRAME_PNG

-   Rendered HTML exports

-   Attachment files

-   Pre-signed URLs with 15-minute TTL

-   Soft-deleted images retained for 30 days before purge (RF-14 remove
    operation)

**Redis**

-   Celery broker and result backend

-   HTTP session and JWT blacklist cache

-   WebSocket pub/sub for real-time task events, protocol updates,
    acquisition_status changes

-   Protocol-level write lock (prevents concurrent reassignment
    conflicts)

**5.6 autologbook-agent (revised in v2.1)**

A minimal Python daemon installable on the acquisition PC. Replaces
autowatchdog.py. Uses the same watchdog library but POSTs to the web API
instead of updating an in-process protocol object.

> class AutologbookAgent: def \_\_init\_\_(self, config: AgentConfig):
> self.api_url = config.api_url self.token = config.protocol_token \#
> scoped: protocol_id + /ingest only self.handler =
> AgentEventHandler(self.api_url, self.token) self.observer = Observer()
> def start(self): self.observer.schedule(self.handler,
> config.watch_folder, recursive=True) self.observer.start() \# same
> watchdog library as legacy def stop(self): self.observer.stop()
> self.observer.join() self.\_post_close_session() \# → sets
> acquisition_status=COMPLETED on server

**Critical agent requirements (v2.1 additions)**

**1. sample_path is mandatory in every upload**

The server derives the sample hierarchy exclusively from the sample_path
field sent with each file. The agent must compute sample_path as the
relative path of the file with respect to the configured watch_folder
root, with the filename removed:

> \# Example: watch_folder = C:\\Data\\2024-123-proj-resp\\ \# File
> arrives at: C:\\Data\\2024-123-proj-resp\\SampleA\\SubB\\image_001.tif
> \# sample_path to send: \'SampleA/SubB\' (forward slashes, no leading
> slash) \# filename to send: \'image_001.tif\'
>
> **The local folder structure on the acquisition PC is completely
> decoupled from the naming conventions of the legacy system. The folder
> can be named anything. The server does not validate or interpret
> folder names --- only sample_path and filename matter. This removes
> the legacy constraint that required folders to follow the
> NNN-project-resp naming convention.**

**2. XL40 multiframe and file-stability debounce**

The legacy wait_until_file_is_closed() polls file size. This is
insufficient for XL40 multiframe TIFF files, which are written
frame-by-frame (SE frame first, then BSE frame appended to the same
file). A simple \'file closed\' event fires after the first frame is
written, before the BSE frame is appended, resulting in a partial
upload.

The agent must implement an enhanced stability check for multi-page TIFF
files:

-   On FileCreated or FileModified event: record current file size and
    timestamp

-   After configurable stability_window (default 5 seconds): re-read
    file size

-   If size has not changed: proceed with upload (file is stable)

-   If size has changed: reset timer and repeat --- file is still being
    written

-   Apply the same logic to all TIFF files (not only XL40), as the FEI
    microscope software can also trigger a spurious FileModified event
    just after creation

> \# Pseudo-code for enhanced stability check STABILITY_WINDOW = 5 \#
> seconds (configurable) def wait_until_stable(path): while True:
> size_before = path.stat().st_size time.sleep(STABILITY_WINDOW)
> size_after = path.stat().st_size if size_before == size_after: return
> \# file is stable, safe to upload \# else: file still being written,
> loop
>
> **For VEGA JPEG: the agent must additionally wait for the paired .hdr
> sidecar file before uploading the JPEG. The sidecar may arrive several
> seconds after the image. The agent pairs them locally (same logic as
> VegaELOGProtocolEventHandler.create_header_file()) before POSTing both
> as a multipart upload to /api/v1/ingest.**

**3. Offline buffer and retry**

-   If the server is unreachable, the agent buffers pending uploads to a
    local SQLite queue

-   On reconnection, queued uploads are replayed in FIFO order

-   Retry uses exponential backoff (tenacity: max_attempts configurable,
    default 5, wait 0.5--30s)

-   Buffer size limit configurable (default 10 GB); agent warns operator
    if buffer approaches limit

**5.7 API Design Conventions**

-   Base path: /api/v1/

-   Authentication: JWT Bearer (15 min) + refresh tokens (7 days)

-   File ingestion: POST /api/v1/ingest --- multipart/form-data with
    protocol_id, sample_path (mandatory), filename, and file binary

-   Agent session close: POST /api/v1/protocols/{id}/close-session →
    sets acquisition_status=COMPLETED

-   Async responses: 202 Accepted + { task_id, status_url } for all
    pipeline operations

-   Task status: GET /api/v1/tasks/{task_id} → { status, result, error }

-   WebSocket: WS /api/v1/ws/protocols/{id} --- real-time events: task
    progress, new images, acquisition_status changes

-   Pagination: cursor-based for all list endpoints

-   Error format: RFC 7807 Problem Details

-   Visibility filtering: SQL RLS --- never post-filtered in application
    code

> **6. Non-Functional Requirements**

  ---------------------------------------------------------------------------------
  **ID**                  **Category**            **Requirement**
  ----------------------- ----------------------- ---------------------------------
  NFR-01                  Performance             Thumbnail generation for a 50 MB
                                                  TIFF must complete within 30
                                                  seconds

  NFR-02                  Performance             API response time for protocol
                                                  list \< 200ms at p95

  NFR-03                  Performance             DZI tile set generation for a 500
                                                  MB TIFF must complete within 5
                                                  minutes

  NFR-04                  Scalability             Celery worker pool scales
                                                  horizontally; minimum 4 workers
                                                  for image processing

  NFR-05                  File size               Must handle TIFF files up to 2 GB
                                                  (XL40 multiframe)

  NFR-06                  Availability            Server unavailability must not
                                                  prevent agent from queueing
                                                  uploads locally (SQLite buffer)

  NFR-07                  Data integrity          Calibration must never overwrite
                                                  original file without explicit
                                                  CalibrationConfig flag

  NFR-08                  Data integrity          Reassignment (RF-14) must be
                                                  atomic: DB update and object
                                                  storage move succeed together or
                                                  both roll back

  NFR-09                  Security                RESTRICTED protocol thumbnails
                                                  must never appear in API
                                                  responses for unauthorised users

  NFR-10                  Security                Object storage URLs must be
                                                  pre-signed with 15-min TTL --- no
                                                  public permanent URLs

  NFR-11                  Security                All access to RESTRICTED
                                                  resources must be written to the
                                                  audit log

  NFR-12                  Security                Agent tokens are per-protocol and
                                                  scoped only to /api/v1/ingest and
                                                  /close-session

  NFR-13                  Backwards compat        .exp config files from legacy
                                                  expwizard importable via POST
                                                  /api/v1/protocols/import-config

  NFR-14                  Browser support         Chrome 110+, Firefox 110+, Safari
                                                  16+

  NFR-15                  Accessibility           WCAG 2.1 AA for all primary user
                                                  flows
  ---------------------------------------------------------------------------------

> **7. Open Questions & Migration Notes**

**7.1 Critical design decisions to resolve**

-   Protocol number sequence: import existing ELOG protocol numbers at
    migration time and start the DB sequence above the highest existing
    value to avoid collisions.

-   XL40 stability window: the default 5-second stability_window in the
    agent may be insufficient for very large multiframe TIFF files from
    high-resolution XL40 sessions. Confirm maximum expected write
    duration with operators.

-   Multi-user concurrent annotation: optimistic locking via updated_at
    ETag. Confirm if real-time collaborative editing (two users in same
    protocol simultaneously) is a requirement.

-   VEGA JPEG sidecar timing: confirm maximum expected delay between
    JPEG creation and .hdr sidecar arrival from the microscope software.
    This determines the agent\'s pairing timeout.

-   Unit structure: the model assumes a flat list of units. Confirm if a
    hierarchical unit tree (department \> section \> group) is required
    --- this would require changes to the RLS policies and permission
    matrix.

-   CalibrationConfig defaults for Multi protocols: confirm whether a
    Multi protocol should inherit default calibration settings from a
    primary microscope, or require explicit CalibrationConfig entries
    for every instrument type expected in the session.

-   Idle timeout for acquisition_status: the default 120-minute idle
    timeout that triggers acquisition_status=COMPLETED may be too short
    for overnight acquisition sessions. Make this configurable per
    ExperimentConfiguration.

**7.2 Modules reusable as-is (strip Qt imports only)**

-   microscope_picture.py --- MicroscopePicture, FEIPicture,
    VegaPicture, XL40Picture, MicroscopePictureFactory

-   autotools.py --- PictureType, FEITagCodes, VegaMetadataParser,
    PictureResolution, all formatters

-   file_type_guesser.py --- ElementTypeGuesser, RegexpRepository (zero
    Qt deps)

-   attachment.py --- Attachment, AttachmentFactory, AttachmentType

-   Jinja2 templates (.yammy files)

**7.3 Modules to rewrite**

-   autowatchdog.py → Celery task chain + autologbook-agent (separate
    installable package)

-   autoprotocol.py → strip Qt signals, replace filesystem paths with
    storage keys, remove all ELOG calls, add acquisition_status
    management

-   sample.py → strip Qt signals, map to SQLAlchemy async model

-   elog_interface.py → deleted entirely

-   autoconfig.py → Pydantic BaseSettings + .env file; QSettings removed

-   expwizard/ → replaced by web wizard flow (RF-12)

-   autogui.py, autologbook_app.py → replaced by React SPA

-   protocol_editor.py → replaced by Protocol Workspace Edit Panel +
    RF-14 context menus

-   file_system_command.py (FileSystemCommander) → replaced by RF-14
    server-side reassignment service
