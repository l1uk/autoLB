# autologbook — Agent Context
## Project
Web platform replacing PyQt5 autologbook desktop app (v0.1.8).
Backend: FastAPI + Celery + PostgreSQL + Redis + MinIO.
Frontend: React 18 + TypeScript + TanStack Query + shadcn/ui.
Data-service: Go daemon on acquisition PCs (Windows 7+, Linux).
## Repository layout
autologbook/
├── backend/ # FastAPI app + Celery workers
├── frontend/ # React SPA
├── data-service/ # Go agent
├── legacy/ # PyQt5 v0.1.8 — reference only, do NOT modify
└── docs/srs/ # SRS versionate
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
- All object storage operations are backend-side only (RF-10)
- AccessPolicy enforcement happens at SQL/RLS level, never post-filter
in application code (§3.7)
- PictureType detection order is critical: QUATTRO → VERSA → FEI →
VEGA_TIFF → VEGA_JPEG → XL40 variants → GENERIC. GENERIC always last.
## Known stubs — do not invent behaviour
- §8.5 folder naming (relative_path → protocol_id mapping): implement as
a configurable PathResolver interface with a single TODO stub.
Do NOT hardcode any path logic.
- YAMLRecycler: referenced in RF-07 and RF-13 — implement as a no-op
stub with a clear interface. Logic will be ported from legacy later.
- AccessPolicy enforcement: implement schema and FK in Sprint 0.
Permission checks are stubs returning True until Sprint 3.
- LDAP/AD integration (§3.8): stub only, local JWT auth for now.
## Tech stack
Backend: FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2,
Celery + Redis, Pillow, numpy, piexif, pyvips, boto3,python-jose (JWT RS256), bcrypt, Jinja2
Frontend: React 18 + TypeScript, TanStack Query, Zustand,
React Router v6, Tailwind CSS, shadcn/ui, OpenSeadragon
Data-service: Go (static binary, CGO_ENABLED=0), fsnotify,
SQLite (offline queue), TLS 1.2+
## Current sprint focus
SPRINT 0 - INFRA-01 — Backend Docker Compose & BE-01 — Domain Models + Alembic Migration 
