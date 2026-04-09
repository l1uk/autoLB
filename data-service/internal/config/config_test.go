package config

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLoadAppliesDefaults(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "config.toml")
	if err := os.WriteFile(configPath, []byte("backend_url='https://backend'\nwatch_folder='/watch'\n"), 0o644); err != nil {
		t.Fatalf("write config: %v", err)
	}

	cfg, err := Load(configPath)
	if err != nil {
		t.Fatalf("load config: %v", err)
	}

	if cfg.HeartbeatInterval != DefaultHeartbeatInterval {
		t.Fatalf("heartbeat interval = %v, want %v", cfg.HeartbeatInterval, DefaultHeartbeatInterval)
	}
}

func TestSaveRoundTrip(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "config.toml")
	cfg := Config{
		BackendURL:        "https://backend",
		ClientID:          "client-1",
		APIKey:            "api-key",
		SessionToken:      "session",
		WatchFolder:       "/watch",
		HeartbeatInterval: 10 * time.Second,
		CACertPath:        "/cert.pem",
	}

	if err := cfg.Save(configPath); err != nil {
		t.Fatalf("save config: %v", err)
	}

	loaded, err := Load(configPath)
	if err != nil {
		t.Fatalf("reload config: %v", err)
	}

	if loaded.ClientID != cfg.ClientID || loaded.SessionToken != cfg.SessionToken {
		t.Fatalf("round trip mismatch: %#v", loaded)
	}
}
