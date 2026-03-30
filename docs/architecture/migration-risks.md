# Migration Risks

## Summary
- The largest migration risk is architectural, not algorithmic.
- The legacy application is a desktop monolith built around local filesystem monitoring and ELOG integration.
- The target requirements describe a web platform with backend APIs, persistent application data, access control, object storage, and server-driven workflows.

## High Risks

### R-001: Filesystem-Coupled Ingestion Model
- Severity: High
- Legacy behavior depends on local folder monitoring with `watchdog`.
- Target behavior requires agent-to-server upload with explicit `sample_path`, asynchronous processing, and server-owned storage.
- Risk:
  - core workflows may be incorrectly migrated if the legacy folder semantics are copied too literally
  - implicit directory-derived behavior must be made explicit in API contracts

### R-002: Heavy ELOG Coupling
- Severity: High
- Protocol creation, numbering, search, editing status, rendered output, and experiment tracking are tightly tied to ELOG.
- Risk:
  - hidden product rules may currently live in ELOG attributes and message conventions rather than in Python code
  - migration could accidentally drop business meaning embedded in ELOG fields such as protocol numbering or status handling

### R-003: No Internal Database or Authorization Model
- Severity: High
- The legacy app has no visible relational persistence, users/units model, or audit log subsystem.
- Risk:
  - major target requirements for visibility, role-based access, restricted resources, and auditability must be designed from scratch
  - there is little direct legacy behavior to reuse for FR-014 and FR-015

### R-004: UI and Business Logic Are Tightly Interleaved
- Severity: High
- Key business workflows are mixed with PyQt windows, Qt signals, and direct file operations.
- Risk:
  - extracting reusable domain logic will be slower than it first appears
  - hidden side effects may live in UI event handlers rather than clean service functions

### R-005: Path-Based Identity and State
- Severity: High
- Many entities are keyed by filesystem path, and customization is keyed in YAML by path-like strings.
- Risk:
  - path changes currently act as identity changes
  - migration to stable IDs and storage keys will require explicit translation rules
  - rename/move workflows may lose annotations if key-mapping behavior is not preserved

## Medium Risks

### R-006: Global or Microscope-Level Configuration vs Target Per-Image Configuration
- Severity: Medium
- Legacy calibration behavior appears configuration-driven at the microscope or experiment level.
- Target requirements expect per-image configuration resolution by detected picture type.
- Risk:
  - calibration behavior may subtly change in mixed-instrument sessions

### R-007: Derivative Model Mismatch
- Severity: Medium
- Legacy code stores generated PNG and thumbnail paths as ad hoc image parameters.
- Target requirements require normalized derivative entities with typed variants.
- Risk:
  - legacy rendering assumptions may rely on direct path fields that do not map cleanly to the new model

### R-008: Status Semantics Drift
- Severity: Medium
- Legacy uses ELOG concepts such as `Edit Lock` and `Analysis status`.
- Target requirements separate edit status from acquisition status.
- Risk:
  - migration may merge or misinterpret two different legacy concepts

### R-009: Hidden Operational Assumptions in Config Defaults
- Severity: Medium
- Defaults include Windows drive letters, image-server paths, executables, and hard-coded network shares.
- Risk:
  - product logic may rely on environment assumptions that are not obvious from the UI
  - some behaviors may fail when moved to platform-neutral services

### R-010: Sidecar and Multi-Frame Edge Cases
- Severity: Medium
- VEGA JPEG metadata and XL40 multi-frame handling contain specialized logic.
- Risk:
  - these microscope-specific edge cases are easy to regress during migration because they are buried inside large modules

## Lower but Notable Risks

### R-011: Incomplete or Obsolete Code Paths
- Severity: Low
- Some modules look like prototypes or partially abandoned code, such as `model_test_ui.py` and the commented CLI path.
- Risk:
  - teams may overestimate or underestimate actual production coverage if obsolete code is mistaken for live behavior

### R-012: Template Migration Complexity
- Severity: Low
- Jinja/Yammy templates likely encode important presentation and content-order rules.
- Risk:
  - rendering may lose parity if template behavior is rewritten from scratch without extracting business display rules

## Unknowns

### U-001: Real Production Usage of Editor Restore Flow
- Uncertainty: Medium
- A recycle-bin restore dialog exists, but its operational importance is not yet clear.

### U-002: Full Coverage of All Microscope Variants
- Uncertainty: Medium
- Multiple microscope subclasses exist, but feature completeness across all supported variants was not fully validated.

### U-003: ELOG Data Semantics Outside Code
- Uncertainty: High
- Some behavior may depend on the structure and conventions of the external ELOG instance rather than source code alone.

### U-004: Production Importance of `.exp` Reconciliation
- Uncertainty: Medium
- The wizard contains significant logic for local vs remote experiment-file comparison.
- It is unclear whether this is central operational behavior or a niche recovery path.

## Tightly Coupled Hotspots to De-Risk Early
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autogui.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autogui.py)
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/protocol_editor.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/protocol_editor.py)
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autowatchdog.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autowatchdog.py)
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/autoprotocol.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/autoprotocol.py)
- [`/home/luc/Documents/migration-workspace/autologbook/autologbook/microscope_picture.py`](/home/luc/Documents/migration-workspace/autologbook/autologbook/microscope_picture.py)

## Recommended Next Analysis Steps
- Extract an explicit legacy domain model independent of Qt and ELOG.
- Trace one end-to-end ingestion flow per microscope family.
- Inventory every ELOG attribute used in code and map it to target data fields.
- Trace YAML customization keys and rename/move recycling rules.
- Separate reusable algorithms from desktop orchestration code before planning implementation.
