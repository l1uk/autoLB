# autologbook

Web replacement for the legacy PyQt5 autologbook desktop application.

Current status: Sprint 1 objective is implemented for the auth and data-service communication path.

Implemented so far

- Backend FastAPI app skeleton with lifespan, CORS, router wiring, and health endpoint.
- Human authentication with RS256 JWT access and refresh tokens.
- Data-service machine registration and authentication flow:
  `register -> auth -> heartbeat`
- Data-service heartbeat delivery and task acknowledgement flow.
- Offline client detection with a scheduled Celery beat task.
- Go data-service daemon with:
  - TOML config loading
  - backend HTTP client with TLS 1.2 minimum
  - recursive filesystem watcher
  - SQLite offline upload queue
  - heartbeat loop and task execution
- Automated tests for backend and data-service.
- Live smoke test for the Go agent against the real backend.

Implemented Sprint 1 goal

The current end-to-end path is:

1. The Go agent registers itself with the backend if it has no `client_id`.
2. The backend returns `client_id` and a plaintext `api_key` once.
3. The agent authenticates with `client_id + api_key` and receives a session token.
4. The agent sends heartbeat requests at the configured interval.
5. The backend can return pending tasks on heartbeat.
6. The agent executes supported filesystem tasks and acknowledges them.

Repository layout

- [backend](/home/luc/Documents/autologbook/backend): FastAPI app, Celery worker, Alembic migrations, backend tests
- [data-service](/home/luc/Documents/autologbook/data-service): Go daemon, Docker assets, Go tests
- [legacy](/home/luc/Documents/autologbook/legacy): reference PyQt5 app, not to be modified
- [docs](/home/luc/Documents/autologbook/docs): SRS and ADR material

How to run the backend

Start the backend stack:

```bash
docker compose -f backend/docker-compose.yml up -d postgres redis backend
```

Apply database migrations:

```bash
docker compose -f backend/docker-compose.yml run --rm backend alembic upgrade head
```

The API is then available on `http://localhost:8000`.

Useful backend commands:

```bash
docker compose -f backend/docker-compose.yml run --rm backend pytest backend/tests/ -v
docker compose -f backend/docker-compose.yml logs -f backend
docker compose -f backend/docker-compose.yml up -d worker
```

How to run the data-service tests

Run the Go test suite:

```bash
docker compose -f data-service/docker-compose.yml run --rm agent go test ./... -v
```

This includes package tests for:

- config loading
- backend client behavior
- watcher behavior
- SQLite queue behavior

How to run the live agent smoke test

Make sure the backend is already running and migrated, then run:

```bash
docker compose -f data-service/docker-compose.yml run --rm \
  -e DATA_SERVICE_LIVE_BACKEND_URL=http://host.docker.internal:8000 \
  agent go test ./cmd/agent -run TestLiveRegisterAuthHeartbeat -v
```

This test verifies the real `register -> auth -> heartbeat` path from the Go agent container to the FastAPI backend.

How the Go agent is intended to be used

The Go daemon entrypoint is [main.go](/home/luc/Documents/autologbook/data-service/cmd/agent/main.go).

Expected startup flow:

1. Create a TOML config file with at least:
   - `backend_url`
   - `watch_folder`
2. Start the agent.
3. On first startup, it registers and persists `client_id`, `api_key`, and `session_token`.
4. It starts:
   - the recursive filesystem watcher
   - the SQLite upload queue processor
   - the heartbeat loop

Example config:

```toml
backend_url = "http://host.docker.internal:8000"
watch_folder = "/data/watch"
heartbeat_interval = "30s"
ca_cert_path = ""
client_id = ""
api_key = ""
session_token = ""
registration_secret = "replace-with-your-shared-secret"
```

Example agent run command:

```bash
docker compose -f data-service/docker-compose.yml run --rm agent \
  go run ./cmd/agent -config /workspace/data-service/config.toml
```

Deployment & Installation

For a Windows workstation, create a real config file first and place it in a stable location such as `C:\ProgramData\autologbook\config.toml`. The `registration_secret` value must match the shared secret expected by your backend. The agent uses that value only when `client_id` is empty, which makes it safe to keep in the file after the first successful registration.

Example Windows config:

```toml
backend_url = "http://backend.company.local:8000"
watch_folder = "D:\\Autologbook\\Watch"
heartbeat_interval = "30s"
ca_cert_path = ""
client_id = ""
api_key = ""
session_token = ""
registration_secret = "replace-with-your-shared-secret"
```

You can install the agent as a Windows Service in either of these ways:

1. Built-in service control flag

```powershell
autologbook-agent.exe -config "C:\ProgramData\autologbook\config.toml" -service install
autologbook-agent.exe -config "C:\ProgramData\autologbook\config.toml" -service start
```

To stop or remove it later:

```powershell
autologbook-agent.exe -config "C:\ProgramData\autologbook\config.toml" -service stop
autologbook-agent.exe -config "C:\ProgramData\autologbook\config.toml" -service uninstall
```

2. NSSM

```powershell
nssm install autologbook-agent "C:\Program Files\Autologbook\autologbook-agent.exe"
nssm set autologbook-agent AppParameters "-config C:\ProgramData\autologbook\config.toml"
nssm start autologbook-agent
```

When the agent runs as a service, it writes persistent logs to `%ProgramData%\autologbook\logs\agent.log`. If you run it in a terminal for debugging, logs go to the console instead.

To verify that the service is running, use Services.msc, `Get-Service autologbook-agent`, or `sc query autologbook-agent`. If the service starts but does not register correctly, check the log file above first; it records configuration load failures, registration errors, authentication errors, and heartbeat problems.

Current limitations

- The frontend is not documented here because Sprint 1 work focused on backend and data-service communication.
- LDAP/AD remains a backend stub.
- The Go agent implements the requested transport and queue structure, but backend endpoints for file notification and upload are not documented here unless and until they are implemented server-side.

Verification completed

- `docker compose -f backend/docker-compose.yml run --rm backend pytest backend/tests/ -v`
- `docker compose -f backend/docker-compose.yml run --rm backend pytest backend/tests/integration/ -v`
- `docker compose -f data-service/docker-compose.yml run --rm agent go test ./... -v`
- `docker compose -f data-service/docker-compose.yml run --rm -e DATA_SERVICE_LIVE_BACKEND_URL=http://host.docker.internal:8000 agent go test ./cmd/agent -run TestLiveRegisterAuthHeartbeat -v`
