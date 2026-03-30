# Legacy Application Analysis

## Scope and Assumptions
- The requested input path `./legacy-app` does not exist in this workspace.
- This analysis assumes the intended legacy codebase is [`/home/luc/Documents/migration-workspace/autologbook`](/home/luc/Documents/migration-workspace/autologbook).
- The analysis is based on source inspection only. No code was executed.

## Current Architecture Summary
- The legacy system is a Windows-oriented PyQt5 desktop application with two related GUI surfaces:
  - the main `autologbook` desktop application
  - the `experiment-wizard` desktop flow
- It also ships separate `labtools` utilities for metadata dumping, image conversion, mirroring, and FEI image manipulation.
- The application is not a client/server system. It is a local desktop process that:
  - watches folders on disk with `watchdog`
  - builds in-memory protocol objects
  - reads and writes files directly on the filesystem
  - renders HTML locally with Jinja/Yammy templates
  - posts protocol content to an external ELOG server
- There is no internal database layer visible in the codebase.
- Persistence is distributed across:
  - local filesystem folders and media files
  - `.ini` and `.exp` configuration files
  - YAML customization files
  - Qt `QSettings`
  - remote ELOG entries and attachments

## Top-Level Structure

### Main Packages
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook`](/home/luc/Documents/migration-workspace/autologbook/autologbook): main desktop application, core models, watchdog logic, rendering, ELOG integration.
- [`/home/luc/Documents/migration-workspace/autologbook/expwizard`](/home/luc/Documents/migration-workspace/autologbook/expwizard): experiment creation and recovery wizard.
- [`/home/luc/Documents/migration-workspace/autologbook/labtools`](/home/luc/Documents/migration-workspace/autologbook/labtools): standalone utilities and one separate GUI.

### Static Assets and Config
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/ui`](/home/luc/Documents/migration-workspace/autologbook/autologbook/ui): Qt Designer `.ui` files for the main app.
- [`/home/luc/Documents/migration-workspace/autologbook/expwizard/ui`](/home/luc/Documents/migration-workspace/autologbook/expwizard/ui): wizard UI files.
- [`/home/luc/Documents/migration-workspace/autologbook/labtools/ui`](/home/luc/Documents/migration-workspace/autologbook/labtools/ui): labtools UI files.
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/templates`](/home/luc/Documents/migration-workspace/autologbook/autologbook/templates): Jinja/Yammy HTML templates.
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/conf/type_guesser_regexp.yaml`](/home/luc/Documents/migration-workspace/autologbook/autologbook/conf/type_guesser_regexp.yaml): filename/path classification rules.
- [`/home/luc/Documents/migration-workspace/autologbook/expwizard/conf/unit_list.yaml`](/home/luc/Documents/migration-workspace/autologbook/expwizard/conf/unit_list.yaml): wizard unit metadata.

## Entry Points

### Main Desktop App
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/__main__.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/__main__.py): module entry point for `python -m autologbook`.
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autologbook_app.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autologbook_app.py): chooses GUI or CLI mode.
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autogui.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autogui.py): bootstraps the main PyQt window and background worker threads.

### Experiment Wizard
- [`/home/luc/Documents/migration-workspace/autologbook/expwizard/experiment_wizard_app.py`](/home/luc/Documents/migration-workspace/autologbook/expwizard/experiment_wizard_app.py): wizard GUI entry point.
- [`/home/luc/Documents/migration-workspace/autologbook/expwizard/experiment_wizard.py`](/home/luc/Documents/migration-workspace/autologbook/expwizard/experiment_wizard.py): `QWizard` orchestration.

### Labtools
- Package scripts defined in [`/home/luc/Documents/migration-workspace/autologbook/pyproject.toml`](/home/luc/Documents/migration-workspace/autologbook/pyproject.toml):
  - `metadata-reader`
  - `fei-image-manipulator`
  - `event-logger`
  - `image-converter`
  - `mirror-maker`
  - `image-converter-gui`

## Main Modules and Responsibilities

### UI Layer
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autogui.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autogui.py)
  - Main window
  - input validation
  - recent-file handling
  - thread startup for watchdog processing
  - protocol list updates to ELOG
  - experiment load/save
  - browser and editor launching
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/protocol_editor.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/protocol_editor.py)
  - protocol tree browsing
  - metadata preview
  - caption/description/extra editing
  - rename, move, remove, restore workflows
  - synchronization between model state and YAML customization
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/dialog_windows.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/dialog_windows.py)
  - configuration dialog
  - rename dialog
  - sample-change dialog
  - user editor
  - read-only overwrite dialog
- [`/home/luc/Documents/migration-workspace/autologbook/expwizard/*.py`](/home/luc/Documents/migration-workspace/autologbook/expwizard)
  - multi-step wizard for new or existing experiments
- [`/home/luc/Documents/migration-workspace/autologbook/labtools/image_converter_gui.py`](/home/luc/Documents/migration-workspace/autologbook/labtools/image_converter_gui.py)
  - standalone GUI for image conversion

### Domain and Business Logic
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autoprotocol.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autoprotocol.py)
  - core `Protocol` object
  - ELOG-backed protocol subclasses
  - HTML generation
  - YAML initialization/loading
  - protocol posting/updating against ELOG
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/microscope_picture.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/microscope_picture.py)
  - microscope picture model hierarchy
  - microscope type detection hooks
  - metadata extraction
  - PNG and thumbnail generation
  - FEI calibration and databar crop helpers
  - VEGA JPEG metadata handling
  - XL40 multi-frame support
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/sample.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/sample.py)
  - hierarchical sample model
  - containers for images, videos, optical images, attachments
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/attachment.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/attachment.py)
  - attachment model
  - attachment typing
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/optical_image.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/optical_image.py)
  - optical image model types and factory
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/video.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/video.py)
  - video model
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/navigation_image.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/navigation_image.py)
  - Quattro navigation image container
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/file_type_guesser.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/file_type_guesser.py)
  - filename/path classification by regex repository
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autotools.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autotools.py)
  - shared enums, parser utilities, metadata helpers, YAML helpers, formatting, config generation
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/containers.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/containers.py)
  - resettable collection helpers used across domain objects

### Background Processing and Filesystem Automation
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autowatchdog.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autowatchdog.py)
  - watchdog event handlers
  - mirror event handling
  - protocol event handling by microscope type
  - file create/modify/delete routing
  - local metadata sidecar handling
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/thread_worker.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/thread_worker.py)
  - `QThread`-backed worker setup
  - watchdog observer lifecycle
  - protocol instance creation and event handler wiring
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/file_system_command.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/file_system_command.py)
  - rename/move/delete command abstraction executed against the local filesystem

### Rendering and External Integrations
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/jinja_integration.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/jinja_integration.py)
  - Jinja/Yammy environment
  - template filters
  - filesystem path to image-server URL conversion
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/elog_interface.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/elog_interface.py)
  - ELOG connection parameters
  - logbook handle factory
  - higher-level ELOG wrappers
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/elog_post_splitter.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/elog_post_splitter.py)
  - ELOG page splitting for size limits

## UI-Specific Code Detection

### Confirmed Qt/PyQt UI Modules
- `autologbook/autogui.py`
- `autologbook/protocol_editor.py`
- `autologbook/dialog_windows.py`
- `autologbook/protocol_editor_models.py`
- `autologbook/restore_element.py`
- `expwizard/*.py`
- `labtools/image_converter_gui.py`

### Generated Qt UI Wrappers
- Files ending with `_ui.py` in `autologbook`, `expwizard`, and `labtools`
- `.ui` sources under each package’s `ui` directory
- `resource_rc.py` files generated from Qt resources

### UI Coupling Observations
- UI code directly instantiates and mutates domain objects.
- UI code also performs filesystem operations and ELOG posting.
- Qt signal dispatchers are embedded into core model classes such as `Protocol` and `Sample`.
- This means the legacy system is not cleanly layered into presentation, application, and domain boundaries.

## Business Logic vs UI Separation

### Relatively Reusable Logic
- microscope metadata parsing and picture subtype handling
- filename/path type classification
- FEI/VEGA/XL40 parsing logic
- image thumbnail and PNG generation
- FEI calibration and databar crop algorithms
- HTML template structure and filters
- YAML key recycling logic for rename/move preservation

### Logic Currently Mixed with UI or Desktop Concerns
- protocol state changes are tied to Qt signals
- watchdog setup is tied to `QThread` worker orchestration
- path validation assumes local Windows paths and a specific image server base path
- experiment creation is tied to ELOG protocol-list posting and folder generation
- element reassignment is implemented as local filesystem mutation rather than service-level logical reassignment

## Data Model Hints

### Core Domain Objects Observed
- `Protocol`
- `Sample`
- `MicroscopePicture` and specialized subclasses
- `Attachment`
- `GenericOpticalImage` and specializations
- `Video`
- `NavigationImagesList`

### Persistence Shape in Legacy
- The primary runtime model is in-memory object graphs.
- Media records are keyed by local filesystem paths.
- Custom annotation fields are stored in a YAML dictionary keyed by path-like identifiers.
- There is no relational persistence model in the legacy codebase.
- Some state also exists remotely in ELOG attributes and attachments.

### Important Structural Hints
- Sample hierarchy is derived from directory structure, not from an explicit `sample_path` field.
- Protocol identity is inferred partly from folder naming conventions and partly from ELOG protocol list entries.
- Media derivatives are represented as ad hoc path parameters on image objects, not as a separate derivative entity.
- Edit state appears to rely on ELOG attributes such as `Edit Lock` and `Analysis status`, not on first-class local entities.

## Configuration, Storage, and External Integrations

### Configuration Sources
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autoconfig.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autoconfig.py): hard-coded defaults, including image server paths and ELOG credentials.
- `.ini` files: general configuration.
- `.exp` files: experiment-specific configuration with GUI state.
- Qt `QSettings`: persisted desktop settings.
- YAML:
  - file type regex config
  - unit list config
  - protocol customization content

### External Integrations
- ELOG via `py_elog`
- local and network filesystems
- image server URL generation by path substitution
- external desktop applications through `subprocess.Popen`
- browser launching through `webbrowser`
- HTTP download of remote experiment files via `requests` in the wizard

### Database Access
- No database library or ORM usage was found.
- No SQLite, SQLAlchemy, PostgreSQL, or equivalent persistence layer was found.
- This conclusion is strong because repository-wide searches for common DB libraries returned no matches.

## Background Tasks and Concurrency
- No async server-side job queue exists in the legacy architecture.
- Background work is handled by:
  - `watchdog.observers.Observer`
  - Qt `QThread`
  - local event handlers
- Real-time UI updates happen through Qt signal/slot propagation, not over a network transport.
- Some labtools also run observer-based background tasks.

## Imports, Exports, and File I/O

### Input Sources
- filesystem events in acquisition folders
- experiment `.exp` files
- configuration `.ini` files
- YAML customization files
- TIFF/JPEG/PNG/media files
- remote experiment file downloads in the wizard

### Output Artifacts
- generated thumbnail and PNG files
- YAML customization files
- experiment `.exp` files
- mirrored files to network share
- HTML content posted to ELOG
- ELOG attachments
- text/metadata exports in labtools

### Filesystem Dependence
- The application assumes direct read/write access to protocol folders and mirrored storage locations.
- Local path naming conventions are part of the business flow.
- Windows-specific executable paths and drive letters are hard-coded in defaults.

## Dependency Hotspots and Tightly Coupled Areas
- `autogui.py`: very large orchestration surface combining UI, config, threads, ELOG, logging, and workflow control.
- `protocol_editor.py`: large mixed-responsibility module covering UI, filesystem operations, YAML synchronization, preview behavior, and editing logic.
- `autowatchdog.py`: large module implementing ingestion-like logic, mirroring, sidecar handling, and microscope-specific behavior.
- `autoprotocol.py`: central model that still depends on Qt signaling and ELOG concerns.
- `microscope_picture.py`: likely reusable, but large and internally dense.

## Candidate Reusable Logic
- `microscope_picture.py`
- `autotools.py`
- `file_type_guesser.py`
- `attachment.py`
- parts of `optical_image.py`, `video.py`, and `sample.py`
- Jinja/Yammy templates and formatting filters

### Reuse Caveats
- Many reusable modules still reference:
  - filesystem paths instead of storage keys
  - Qt signal dispatchers
  - template assumptions based on local files
  - ELOG-oriented rendering or posting expectations

## Gaps Against the Target Requirements Model
- No web API layer is present.
- No server-side agent upload API is present.
- No internal data store for protocols, users, units, or audit logs is present.
- No role/visibility model matching `PUBLIC` / `UNIT` / `RESTRICTED` is present.
- No object storage abstraction is present.
- No WebSocket or browser-based real-time transport is present.
- No standalone authentication/authorization service is present.
- No server-side logical reassignment exists; legacy reassignment mutates local files.

## Legacy-Only or Spec-Misaligned Behaviors
- External ELOG is a first-class dependency.
- Protocol number creation is coupled to ELOG list messages.
- Folder naming conventions encode protocol ownership values.
- Mirroring to a network share is core behavior.
- Experiment files are attached back to ELOG entries.
- The protocol editor includes recycle-bin restore behavior.
- The wizard compares local vs remote `.exp` files and may overwrite one with the other.

## Obvious Dead Code or Obsolete Areas
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/model_test_ui.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/model_test_ui.py) and the related `.ui` file look like internal test or prototype UI assets. No active runtime entry point was found.
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autocli.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autocli.py) contains only a minimal active CLI logger setup. The more substantial CLI workflow is commented out, which suggests obsolete or abandoned CLI behavior.
- The misspelled module name [`/home/luc/Documents/migration-workspace/autologbook/autologbook/object_factoy.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/object_factoy.py) is still imported, so it is not dead code, but it is a maintenance smell.
- Some uncertainty remains for `examples/` because those scripts may be ad hoc tools rather than product features.

## Unknowns and Uncertainties
- Some behaviors may exist deeper in long modules that were only partially read.
- It is not yet certain whether all microscope-specific subclasses are fully feature-complete or partially stubbed.
- It is not yet certain whether the recycle-bin restore flow is used in production or is only an editor convenience.
- It is not yet certain whether all ELOG attributes referenced in wizard flows are consistently required across microscope setups.
