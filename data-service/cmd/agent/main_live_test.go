package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"autologbook/data-service/internal/client"
	"autologbook/data-service/internal/config"
)

func TestLiveRegisterAuthHeartbeat(t *testing.T) {
	backendURL := os.Getenv("DATA_SERVICE_LIVE_BACKEND_URL")
	if backendURL == "" {
		t.Skip("DATA_SERVICE_LIVE_BACKEND_URL not set")
	}

	configDir := t.TempDir()
	watchDir := filepath.Join(configDir, "watch")
	if err := os.MkdirAll(watchDir, 0o755); err != nil {
		t.Fatalf("mkdir watch dir: %v", err)
	}

	configPath := filepath.Join(configDir, "config.toml")
	cfg := config.Config{
		BackendURL:         backendURL,
		WatchFolder:        watchDir,
		HeartbeatInterval:  time.Second,
		RegistrationSecret: os.Getenv("DATA_SERVICE_LIVE_REGISTRATION_SECRET"),
	}
	if err := cfg.Save(configPath); err != nil {
		t.Fatalf("save config: %v", err)
	}

	apiClient, err := client.New(cfg)
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := bootstrap(ctx, configPath, &cfg, apiClient); err != nil {
		t.Fatalf("bootstrap: %v", err)
	}

	if cfg.ClientID == "" || cfg.APIKey == "" || cfg.SessionToken == "" {
		t.Fatalf("bootstrap did not persist credentials: %#v", cfg)
	}

	tasks, err := apiClient.Heartbeat(ctx, cfg.ClientID, agentVersion, map[string]any{"live_test": true})
	if err != nil {
		t.Fatalf("heartbeat: %v", err)
	}
	if tasks == nil {
		t.Fatalf("heartbeat returned nil tasks slice")
	}

	reloaded, err := config.Load(configPath)
	if err != nil {
		t.Fatalf("reload config: %v", err)
	}
	if reloaded.ClientID == "" || reloaded.APIKey == "" || reloaded.SessionToken == "" {
		t.Fatalf("config not persisted after bootstrap: %#v", reloaded)
	}
}
