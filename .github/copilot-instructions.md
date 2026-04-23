# autologbook — Agent Context
## Project
Web platform replacing PyQt5 autologbook desktop app (v0.1.8).
Backend: FastAPI + Celery + PostgreSQL + Redis + MinIO.
Frontend: React 18 + TypeScript + TanStack Query + shadcn/ui.
Data-service: Go daemon on acquisition PCs (Windows 7+, Linux).
## Repository layout
autologbook/
├── backend/          # FastAPI app + Celery workers
├── frontend/         # React SPA
├── data-service/     # Go agent
├── legacy/           # PyQt5 v0.1.8 — reference only, do NOT modify
└── docs/srs/         # SRS versionate
## Execution environment
All code runs inside Docker containers. NEVER assume a local Python,
Node, or Go runtime on the host.
### Backend commands
docker compose -f backend/docker-compose.yml run --rm backend <cmd>
# examples:
docker compose -f backend/docker-compose.yml run --rm backend pytest backend/tests/ -v
docker compose -f backend/docker-compose.yml run --rm backend alembic upgrade head
### Data-service commands
docker compose -f data-service/docker-compose.yml run --rm agent go test ./... -v
### Frontend commands
docker compose -f frontend/docker-compose.yml run --rm frontend npm test
### Never do this
- pip install / pytest / go test / npm outside docker compose run
- Assume any port available without checking compose ports config

## Key architecture rules — non-negotiable
- acquisition_status NEVER transitions automatically (RF-19, manual only)
- Pipeline is a registerable handler chain — never modify the coordinator
  to add instrument types; register a new handler instead (RF-01)
- data-service is domain-opaque: it uses context_id as an opaque token,
  never sees protocol_id or sample_path decoded (RF-16, RF-17)
- context_id is HMAC-SHA256 over {protocol_id, sample_path} generated
  server-side; the backend rejects uploads whose context_id fails MAC
  verification. The data-service treats it as opaque and must not
  attempt to parse or construct it (RF-16, §2.16)
- All object storage operations are backend-side only (RF-10)
- AccessPolicy enforcement happens at SQL/RLS level, never post-filter
  in application code (§3.8)
- PictureType detection order is critical: QUATTRO → VERSA → FEI →
  VEGA_TIFF → VEGA_JPEG → XL40 variants → GENERIC. GENERIC always last.
- Registration requires a registration_secret in the POST /register body
  (RF-14, SEC-1). The backend compares it constant-time against the
  REGISTRATION_SECRET env var; responds 403 if it does not match.
  The data-service installer provides this secret out-of-band.
- API key must be stored in the OS keystore (DPAPI on Windows, Secret
  Service on Linux, Keychain on macOS) — never in a plaintext config
  file in production (§11.2). After POST /auth succeeds, the api_key
  must be zeroed in memory.
- InsecureSkipVerify must never be set to true in production TLS config.
  Use ca_cert_path in config for internal/self-signed CAs (§8.1, TLS spec).

## Known stubs — do not invent behaviour
- §9.3 folder naming (relative_path → protocol_id mapping): implement as
  a configurable PathResolver interface with a single TODO stub.
  Do NOT hardcode any path logic.
- YAMLRecycler: REMOVED in v2.8 — do not implement. Annotation fields
  (caption, description, extra_info JSONB) live directly on ProtocolItem
  records. No YAML file, no sync, no recycler (RF-07).
- AccessPolicy enforcement: schema and FK present from Sprint 0.
  Permission checks are stubs returning True until Sprint 3.
- LDAP/AD integration (§3.9): stub only, local JWT auth for now.
- RF-24 Auto-update (data-service): stub GET /api/v1/data-service/version
  endpoint and client-side version check. Ed25519 signature verification
  and atomic binary replacement are Sprint 5+ work. Do NOT implement
  the binary replacement logic now.

## Tech stack
Backend: FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2,
  Celery + Redis, Pillow, numpy, piexif, pyvips, boto3,
  python-jose (JWT RS256), bcrypt, Jinja2, WeasyPrint,
  hmac (stdlib, for context_id HMAC-SHA256 generation and verification)
Frontend: React 18 + TypeScript, TanStack Query, Zustand,
  React Router v6, Tailwind CSS, shadcn/ui, OpenSeadragon, DOMPurify
Data-service: Go (static binary, CGO_ENABLED=0), fsnotify,
  SQLite (offline queue), TLS 1.2+,
  github.com/golang-jwt/jwt/v5 (session_token verification),
  github.com/zalando/go-keyring (OS keystore for api_key)

## Data-service protocol — quick reference (SRS §8 / RF-14–RF-24)
All endpoints under /api/v1/data-service/* require Bearer session_token
unless noted. TLS mandatory on all connections.

| Endpoint                          | Method | Auth          | Notes                                      |
|-----------------------------------|--------|---------------|--------------------------------------------|
| /api/v1/data-service/register     | POST   | none          | Body includes registration_secret (SEC-1)  |
| /api/v1/data-service/auth         | POST   | none          | Returns JWT RS256 8h session_token          |
| /api/v1/data-service/heartbeat    | POST   | session_token | Returns pending tasks                      |
| /api/v1/data-service/file-notify  | POST   | session_token | Returns ACCEPT/IGNORE + opaque context_id  |
| /api/v1/data-service/upload       | POST   | session_token | multipart; includes context_id             |
| /api/v1/data-service/task-ack     | POST   | session_token | Reports task SUCCESS/ERROR                 |
| /api/v1/data-service/version      | GET    | session_token | RF-24 auto-update check (stub for now)     |

## Config fields (data-service)
Required: client_id, api_key (read from OS keystore at runtime),
  watch_folder, server_url, heartbeat_interval
Security: ca_cert_path (path to PEM file for internal/self-signed CA;
  if absent, Go uses OS trust store)
Tuning: stability_window (default 5s), buffer_path, buffer_max_gb,
  vega_jpeg_sidecar_timeout (default 30s), max_upload_attempts (default 5)

## Security invariants (data-service)
- api_key zeroed in memory immediately after POST /auth succeeds
- session_token never written to disk or logs
- context_id treated as opaque — never parsed or constructed client-side
- TLS certificate always verified (InsecureSkipVerify = false)
- File-notify rate: max 120 req/min per session_token (enforced by Nginx)
- Auth rate: max 5 req/min per client_id (enforced by Nginx; retry with
  backoff on 429)