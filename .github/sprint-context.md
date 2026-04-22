# Current Sprint context

## Completed Sprints
- Sprint 0: INFRA-01, BE-01 ✓
- Sprint 1: BE-02, BE-03, BE-04, DS-01 ✓

## Current Sprint focus
Sprint 2 — BE-05: File notify → upload endpoints

## Decisions taken from Sprint 1
- PathResolver: stub with TODO, do not hardcode path logic
- JWT RS256 keypair generated at startup in backend/app/core/security.py
- bcrypt in asyncio.to_thread confirmed
- Token blacklist in Redis: key pattern blacklist:{jti}

## SRS upgrade: v2.7 → v2.10 — changes affecting data-service and Sprint 2

### SEC-1 (breaking — affects BE-05 and DS registration)
POST /api/v1/data-service/register now requires `registration_secret` in
the request body. Backend compares it constant-time against the
REGISTRATION_SECRET environment variable; returns 403 on mismatch.
  - Backend: add REGISTRATION_SECRET to .env and Pydantic Settings
  - Backend: update RegisterRequest schema + endpoint handler
  - Data-service: update internal/client/client.go RegisterPayload struct
    to include RegistrationSecret field; read value from config/env at
    registration time (not stored in keystore — provided out-of-band)

### SEC-3 (context_id is now HMAC-SHA256 — affects BE-05 upload handler)
context_id is explicitly HMAC-SHA256 over {protocol_id, sample_path},
generated server-side at file-notify time using a dedicated HMAC secret
(CONTEXT_ID_HMAC_KEY env var). The upload endpoint verifies MAC before
routing; returns 400 on failure.
  - Backend: add CONTEXT_ID_HMAC_KEY to .env and Pydantic Settings
  - Backend: generate context_id via hmac.new(key, payload, sha256) in
    file-notify handler; verify in upload handler before decoding
  - Data-service: no change — context_id already treated as opaque token

### FileEvent.sha256 (new field — affects BE-05 upload handler)
After receiving file bytes and before writing to MinIO, the backend
computes SHA-256 of the received bytes and stores it in
FileEvent.sha256 (hex-encoded). Used for post-ingestion tamper detection.
  - Backend: add sha256 column to file_events table (Alembic migration)
  - Backend: compute in ReceiveHandler before boto3 put_object call
  - Data-service: no change (server-side only)

### RF-24 Auto-update (new stub — Sprint 2 scope: endpoint stub only)
Add GET /api/v1/data-service/version endpoint returning:
  { current_version, latest_version, download_url, signature,
    auto_update_enabled }
Stub returns latest_version = current_version and auto_update_enabled=false.
Full Ed25519 verification and atomic binary replacement deferred to Sprint 5+.
  - Data-service: add version check at heartbeat time (compare
    agent_version vs latest_version from /version response); log if
    newer version available; do NOT implement download/replace yet

### YAMLRecycler — REMOVED (v2.8 change, now confirmed)
YAMLRecycler stub in backend/app/services/yaml_recycler.py can be
deleted. RF-07 annotation fields (caption, description, extra_info JSONB)
live directly on ProtocolItem records. No recycler logic required.
RF-13 reassignment preserves annotations automatically because they are
on the record — no special preservation code needed.

### ProtocolItem mixin (v2.8 — affects backend models)
All annotatable entities (MicroscopePicture, Attachment, OpticalImage,
NavigationImage, Video) now inherit ProtocolItem fields:
  caption: str, description: str, extra_info: JSONB (was str)
extra_info type change str → JSONB requires Alembic migration if not
already done in Sprint 1.

### MicroscopePicture.embedding (new field — Sprint 4+)
New nullable List[float] field for vector similarity search populated by
EmbeddingHandler. Add column now (nullable) to avoid future migration
on a large table; leave EmbeddingHandler implementation to Sprint 4.

## Open stubs (carried forward)
- YAMLRecycler: DELETE the no-op stub — no longer referenced by any RF
- §9.3 folder naming: PathResolver interface with TODO (unchanged)
- LDAP: stub in backend/app/core/security.py (unchanged)
- RF-24 auto-update: stub /version endpoint; defer binary replacement