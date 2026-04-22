package main

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"autologbook/data-service/internal/config"
)

type bootstrapClientStub struct {
	registerCalls int
	authCalls     int
}

func (s *bootstrapClientStub) Register(ctx context.Context, hostname, watchFolder, osInfo, agentVersion string) (string, string, error) {
	s.registerCalls++
	return "client-1", "api-key", nil
}

func (s *bootstrapClientStub) Auth(ctx context.Context) (string, time.Time, error) {
	s.authCalls++
	return "session-1", time.Time{}, nil
}

func TestBootstrapUsesRegistrationSecretOnlyWhenRegistering(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "config.toml")
	cfg := config.Config{
		BackendURL:         "https://backend",
		WatchFolder:        "/watch",
		RegistrationSecret:  "shared-secret",
	}
	client := &bootstrapClientStub{}

	if err := bootstrap(context.Background(), configPath, &cfg, client); err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	if client.registerCalls != 1 {
		t.Fatalf("register calls = %d, want 1", client.registerCalls)
	}
	if client.authCalls != 1 {
		t.Fatalf("auth calls = %d, want 1", client.authCalls)
	}
	if cfg.ClientID != "client-1" || cfg.APIKey != "api-key" || cfg.SessionToken != "session-1" {
		t.Fatalf("unexpected cfg after bootstrap: %#v", cfg)
	}
	// Verify that RegistrationSecret is zeroed after successful registration (§11.2).
	if cfg.RegistrationSecret != "" {
		t.Fatalf("expected RegistrationSecret to be zeroed, got %q", cfg.RegistrationSecret)
	}

	client = &bootstrapClientStub{}
	cfg.ClientID = "existing-client"
	cfg.APIKey = "existing-api-key"
	cfg.SessionToken = "existing-session"
	cfg.RegistrationSecret = "should-not-be-used"

	if err := bootstrap(context.Background(), configPath, &cfg, client); err != nil {
		t.Fatalf("bootstrap with existing client: %v", err)
	}
	if client.registerCalls != 0 {
		t.Fatalf("register calls = %d, want 0", client.registerCalls)
	}
	if client.authCalls != 1 {
		t.Fatalf("auth calls = %d, want 1", client.authCalls)
	}
	// Verify that RegistrationSecret is still zeroed on subsequent bootstrap calls.
	if cfg.RegistrationSecret != "" {
		t.Fatalf("expected RegistrationSecret to remain zeroed, got %q", cfg.RegistrationSecret)
	}
}