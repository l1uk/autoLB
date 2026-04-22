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
		RegistrationSecret: "shared-secret",
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

	if loaded.ClientID != cfg.ClientID || loaded.SessionToken != cfg.SessionToken || loaded.RegistrationSecret != cfg.RegistrationSecret || loaded.CACertPath != cfg.CACertPath {
		t.Fatalf("round trip mismatch: %#v", loaded)
	}
}

func TestLoadAppliesRegistrationSecretAndCACertPathFromEnv(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "config.toml")
	if err := os.WriteFile(configPath, []byte("backend_url='https://backend'\nwatch_folder='/watch'\nregistration_secret='from-file'\nca_cert_path='/from/file.pem'\n"), 0o644); err != nil {
		t.Fatalf("write config: %v", err)
	}

	t.Setenv("REGISTRATION_SECRET", "from-env")
	t.Setenv("CA_CERT_PATH", "/from/env.pem")

	cfg, err := Load(configPath)
	if err != nil {
		t.Fatalf("load config: %v", err)
	}

	if cfg.RegistrationSecret != "from-env" {
		t.Fatalf("registration secret = %q, want from-env", cfg.RegistrationSecret)
	}
	if cfg.CACertPath != "/from/env.pem" {
		t.Fatalf("ca_cert_path = %q, want /from/env.pem", cfg.CACertPath)
	}
}
