This is a comprehensive `README.md` (or `INSTALL.md`) designed for both the developers and the technicians who will install the agent on the laboratory workstations. It covers the architecture, the "Shared Secret" security, and the Windows Service installation.

---

# Autologbook Data Service Agent

The **Autologbook Data Service Agent** is a lightweight background service written in Go. It is designed to run on laboratory workstations connected to microscopes. Its primary job is to monitor a specific folder, detect new files, and synchronize them with the Autologbook backend.

## ⚙️ How it Works

The agent operates using three main concurrent loops:

1.  **File Watcher**: Constantly monitors the configured `WatchFolder`. When a new file is detected, it is added to a local upload queue.
2.  **Queue Processor**: Manages file uploads to the backend. It ensures that files are uploaded sequentially and handles temporary network failures.
3.  **Heartbeat Loop**: Every few seconds, the agent "pulses" the backend to report its status (Online/Offline) and check for pending **Tasks** (e.g., remote folder creation).



---

## 🔒 Security & Registration

The agent uses a two-tier authentication system:

* **Registration Secret**: To prevent unauthorized devices from connecting, the first-time registration requires a "Shared Secret" (Registration Token).
* **API Key & JWT**: Once registered, the agent receives a unique `ClientID` and `APIKey`. For daily operations, it exchanges these for short-lived **JWT Session Tokens**, ensuring high security and low database overhead.

---

## 🚀 Installation Guide (Windows)

### 1. Prerequisites
* Windows 10/11 or Windows Server.
* Administrator privileges.
* Network access to the Autologbook Backend URL.

### 2. Preparation
1.  Place the `agent.exe` in a permanent folder (e.g., `C:\AutologbookAgent\`).
2.  Create a `config.toml` file in the same directory.

### 3. Configuration (`config.toml`)
Edit the file with the following parameters:

```toml
# Backend Connection
BackendURL = "https://your-api-url.com"
RegistrationSecret = "YOUR_SHARED_SECRET_HERE" # Ask your Admin

# Local Settings
WatchFolder = "C:\\MicroscopeData\\Acquisitions"
HeartbeatInterval = "30s"

# Leave these empty; the agent will fill them during bootstrap
ClientID = ""
APIKey = ""
```

### 4. Install as a Windows Service
Open **PowerShell (as Administrator)** and run:

```powershell
# Install the service
.\agent.exe -service install -config "C:\AutologbookAgent\config.toml"

# Start the service
.\agent.exe -service start
```

*The agent is now running in the background. It will start automatically every time the PC boots.*

---

## 📁 Maintenance & Logs

### Log Files
If the agent is running as a service, it does not show a console window. Logs are stored in a rotating file system to prevent disk space issues:
* **Path**: `C:\ProgramData\autologbook\logs\agent.log`
* **Max Size**: 10MB per file (keeps up to 10 backups).



### Service Control
You can manage the service via the Windows "Services" app (`services.msc`) or via command line:
* **Check Status**: `Get-Service autologbook-data-service`
* **Restart**: `.\agent.exe -service restart`
* **Uninstall**: `.\agent.exe -service uninstall`

---

## 🛠 Developer Notes (Compilation)

To compile the agent from source:

1.  Install **Go 1.21+**.
2.  Download dependencies:
    ```bash
    go mod tidy
    ```
3.  Build the production binary (hidden window, optimized size):
    ```bash
    go build -ldflags="-H windowsgui -s -w" -o agent.exe main.go
    ```

### Dockerized Development

The `data-service/docker-compose.yml` dev service enables `CGO_ENABLED=1` so the standard test command supports the Go race detector:

```bash
docker compose -f data-service/docker-compose.yml run --rm agent go test ./... -v -race
```

---

Does this documentation look complete enough for your laboratory's IT requirements, or should we add a section on how to troubleshoot common network errors?