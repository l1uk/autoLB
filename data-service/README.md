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

# Registration (first-time only, then can be empty)
RegistrationSecret = "YOUR_SHARED_SECRET_HERE"
# Where to get it: Contact the Autologbook administrator.
# The registration secret is placed in the installer and distributed out-of-band.
# After successful first registration, this field is zeroed in memory and
# can be removed from the config file.

# Local Settings
WatchFolder = "C:\\MicroscopeData\\Acquisitions"
HeartbeatInterval = "30s"

# TLS Configuration (optional)
CACertPath = ""
# When to use: If the backend uses a self-signed certificate or internal CA,
# provide the path to a PEM-encoded CA certificate file.
# Example: CACertPath = "C:\\Program Files\\Autologbook\\ca-cert.pem"
# If empty, the system default CA trust store is used (recommended for most deployments).

# Registration & Auth (auto-filled by agent after first registration)
ClientID = ""
APIKey = ""
SessionToken = ""
```

**Important Security Notes:**
* The `APIKey` is stored in the OS keystore (DPAPI on Windows, Secret Service on Linux/macOS), not in the config file.
* The `RegistrationSecret` is only used once during bootstrap. After that, the agent generates a JWT session token.
* If you need to re-register the agent, set `ClientID = ""` and provide the `RegistrationSecret` again.

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

### Version Management

The agent version is defined as a constant in [cmd/agent/main.go](cmd/agent/main.go):

```go
const agentVersion = "0.1.0"
```

**For Release Builds:**
* Update `agentVersion` in `cmd/agent/main.go` to match the release tag (e.g., `"0.2.0"`).
* This version is sent during registration and heartbeats to the backend.
* The backend uses this to notify the agent of available updates via the `CheckVersion()` endpoint.
* Do NOT use `-ldflags` to override the version at build time; update the constant directly.