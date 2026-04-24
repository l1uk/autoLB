package client

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"autologbook/data-service/internal/config"
)

func TestRegister(t *testing.T) {
	var registrationSecret string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/data-service/register" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		var req registerRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		registrationSecret = req.RegistrationSecret
		_ = json.NewEncoder(w).Encode(map[string]string{
			"client_id": "client-1",
			"api_key":   "secret",
		})
	}))
	defer server.Close()

	c, err := New(config.Config{BackendURL: server.URL, WatchFolder: "/watch"})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	clientID, apiKey, err := c.Register(context.Background(), "host", "/watch", "linux", "0.1.0", "registration-secret")
	if err != nil {
		t.Fatalf("register: %v", err)
	}
	if clientID != "client-1" || apiKey != "secret" {
		t.Fatalf("unexpected register response: %q %q", clientID, apiKey)
	}
	if registrationSecret != "registration-secret" {
		t.Fatalf("expected registration secret in body, got %q", registrationSecret)
	}
}

func TestRegisterHandlesServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer server.Close()

	c, err := New(config.Config{BackendURL: server.URL, WatchFolder: "/watch"})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	_, _, err = c.Register(context.Background(), "host", "/watch", "linux", "0.1.0", "registration-secret")
	if err == nil || !strings.Contains(err.Error(), "500") {
		t.Fatalf("expected 500 error, got %v", err)
	}
}

func TestRegisterRejectsInvalidSecret(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "invalid registration_secret", http.StatusForbidden)
	}))
	defer server.Close()

	c, err := New(config.Config{BackendURL: server.URL, WatchFolder: "/watch"})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	_, _, err = c.Register(context.Background(), "host", "/watch", "linux", "0.1.0", "wrong-secret")
	if err == nil || !strings.Contains(err.Error(), "403") {
		t.Fatalf("expected 403 error containing 'registration_secret', got %v", err)
	}
	if !strings.Contains(err.Error(), "registration_secret") {
		t.Fatalf("expected error to mention registration_secret, got %v", err)
	}
}

func TestAuth(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/data-service/auth" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(map[string]string{
			"session_token": "session-1",
			"expires_at":    "2026-04-09T12:00:00Z",
		})
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:  server.URL,
		WatchFolder: "/watch",
		ClientID:    "client-1",
		APIKey:      "secret",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	token, _, err := c.Auth(context.Background())
	if err != nil {
		t.Fatalf("auth: %v", err)
	}
	if token != "session-1" || c.SessionToken() != "session-1" {
		t.Fatalf("unexpected token: %q", token)
	}
}

func TestAuthHandlesUnauthorized(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "denied", http.StatusUnauthorized)
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:  server.URL,
		WatchFolder: "/watch",
		ClientID:    "client-1",
		APIKey:      "secret",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	_, _, err = c.Auth(context.Background())
	if !errors.Is(err, errUnauthorized) {
		t.Fatalf("expected unauthorized, got %v", err)
	}
}

func TestFileNotify(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer session-1" {
			t.Fatalf("missing bearer auth")
		}
		_ = json.NewEncoder(w).Encode(map[string]string{
			"decision":   "ACCEPT",
			"context_id": "ctx-1",
		})
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:   server.URL,
		WatchFolder:  "/watch",
		ClientID:     "client-1",
		APIKey:       "secret",
		SessionToken: "session-1",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	decision, contextID, err := c.FileNotify(context.Background(), "a/b", "file.txt", 12)
	if err != nil {
		t.Fatalf("file notify: %v", err)
	}
	if decision != DecisionAccept || contextID != "ctx-1" {
		t.Fatalf("unexpected notify response: %q %q", decision, contextID)
	}
}

func TestFileNotifyRetriesAfterUnauthorized(t *testing.T) {
	var notifyCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/data-service/auth":
			_ = json.NewEncoder(w).Encode(map[string]string{
				"session_token": "session-2",
				"expires_at":    "2026-04-09T12:00:00Z",
			})
		case "/api/v1/data-service/file-notify":
			notifyCalls++
			if notifyCalls == 1 {
				http.Error(w, "expired", http.StatusUnauthorized)
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]string{
				"decision":   "IGNORE",
				"context_id": "",
			})
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:   server.URL,
		WatchFolder:  "/watch",
		ClientID:     "client-1",
		APIKey:       "secret",
		SessionToken: "expired",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	decision, _, err := c.FileNotify(context.Background(), "", "file.txt", 10)
	if err != nil {
		t.Fatalf("file notify retry: %v", err)
	}
	if decision != DecisionIgnore {
		t.Fatalf("unexpected decision: %q", decision)
	}
	if c.SessionToken() != "session-2" {
		t.Fatalf("session token was not refreshed")
	}
}

func TestUpload(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/data-service/upload" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		file, _, err := r.FormFile("file")
		if err != nil {
			t.Fatalf("form file: %v", err)
		}
		defer file.Close()
		data, err := io.ReadAll(file)
		if err != nil {
			t.Fatalf("read upload: %v", err)
		}
		if string(data) != "payload" {
			t.Fatalf("unexpected upload payload: %q", string(data))
		}
		w.WriteHeader(http.StatusCreated)
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:   server.URL,
		WatchFolder:  "/watch",
		ClientID:     "client-1",
		APIKey:       "secret",
		SessionToken: "session-1",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	if err := c.Upload(context.Background(), "ctx-1", "file.txt", strings.NewReader("payload")); err != nil {
		t.Fatalf("upload: %v", err)
	}
}

func TestUploadHandlesServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusBadGateway)
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:   server.URL,
		WatchFolder:  "/watch",
		ClientID:     "client-1",
		APIKey:       "secret",
		SessionToken: "session-1",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	err = c.Upload(context.Background(), "ctx-1", "file.txt", strings.NewReader("payload"))
	if err == nil || !strings.Contains(err.Error(), "502") {
		t.Fatalf("expected 502 error, got %v", err)
	}
}

func TestUploadHandlesBadRequest(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "invalid context_id", http.StatusBadRequest)
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:   server.URL,
		WatchFolder:  "/watch",
		ClientID:     "client-1",
		APIKey:       "secret",
		SessionToken: "session-1",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	err = c.Upload(context.Background(), "ctx-1", "file.txt", strings.NewReader("payload"))
	if err == nil {
		t.Fatalf("expected error for 400 status")
	}
	if !errors.Is(err, ErrPermanentFailure) {
		t.Fatalf("expected ErrPermanentFailure, got %v", err)
	}
	if !strings.Contains(err.Error(), "invalid context_id") {
		t.Fatalf("expected error message to contain 'invalid context_id', got %v", err)
	}
}

func TestUploadHandlesForbidden(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "client revoked", http.StatusForbidden)
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:   server.URL,
		WatchFolder:  "/watch",
		ClientID:     "client-1",
		APIKey:       "secret",
		SessionToken: "session-1",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	err = c.Upload(context.Background(), "ctx-1", "file.txt", strings.NewReader("payload"))
	if err == nil {
		t.Fatalf("expected error for 403 status")
	}
	if !errors.Is(err, ErrPermanentFailure) {
		t.Fatalf("expected ErrPermanentFailure, got %v", err)
	}
	if !strings.Contains(err.Error(), "revoked") {
		t.Fatalf("expected error message to mention revoked, got %v", err)
	}
}

func TestUploadHandlesRateLimit(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "too many requests", http.StatusTooManyRequests)
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:   server.URL,
		WatchFolder:  "/watch",
		ClientID:     "client-1",
		APIKey:       "secret",
		SessionToken: "session-1",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	err = c.Upload(context.Background(), "ctx-1", "file.txt", strings.NewReader("payload"))
	if err == nil {
		t.Fatalf("expected error for 429 status")
	}
	// 429 should NOT be ErrPermanentFailure; it should be retryable
	if errors.Is(err, ErrPermanentFailure) {
		t.Fatalf("429 should not be treated as permanent failure")
	}
	if !strings.Contains(err.Error(), "429") {
		t.Fatalf("expected error message to contain '429', got %v", err)
	}
}

func TestNewBuildsTLSConfig(t *testing.T) {
	c, err := New(config.Config{BackendURL: "https://backend", WatchFolder: "/watch"})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	transport, ok := c.httpClient.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("unexpected transport type")
	}
	if transport.TLSClientConfig == nil || transport.TLSClientConfig.MinVersion != tls.VersionTLS12 {
		t.Fatalf("tls config not set")
	}
	if transport.TLSClientConfig.InsecureSkipVerify {
		t.Fatalf("insecure skip verify must be false")
	}
}

func TestBuildHTTPClientWithInvalidCAPath(t *testing.T) {
	cfg := &config.Config{
		BackendURL:  "https://backend",
		WatchFolder: "/watch",
		CACertPath:  "/nonexistent/ca.pem",
	}
	_, err := buildHTTPClient(cfg)
	if err == nil {
		t.Fatalf("expected error for nonexistent CA file")
	}
	if !strings.Contains(err.Error(), "failed to read") {
		t.Fatalf("expected error about reading file, got %v", err)
	}
}

func TestBuildHTTPClientAlwaysDisablesInsecureSkipVerify(t *testing.T) {
	cfg := &config.Config{
		BackendURL:  "https://backend",
		WatchFolder: "/watch",
		CACertPath:  "",
	}
	httpClient, err := buildHTTPClient(cfg)
	if err != nil {
		t.Fatalf("buildHTTPClient: %v", err)
	}

	transport, ok := httpClient.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("unexpected transport type")
	}
	if transport.TLSClientConfig.InsecureSkipVerify {
		t.Fatalf("InsecureSkipVerify must always be false per SRS §8.1")
	}
}

func TestCheckVersionParsesResponse(t *testing.T) {
	downloadURL := "https://example.test/agent.bin"
	signature := "base64-signature"

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/data-service/version" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer session-1" {
			t.Fatalf("missing bearer auth")
		}
		if got := r.Header.Get("X-Agent-Version"); got != "0.1.0" {
			t.Fatalf("expected X-Agent-Version header, got %q", got)
		}

		_ = json.NewEncoder(w).Encode(VersionInfo{
			CurrentVersion:    "0.1.0",
			LatestVersion:     "0.2.0",
			AutoUpdateEnabled: true,
			DownloadURL:       &downloadURL,
			Signature:         &signature,
		})
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:   server.URL,
		WatchFolder:  "/watch",
		ClientID:     "client-1",
		APIKey:       "secret",
		SessionToken: "session-1",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	versionInfo, err := c.CheckVersion(context.Background(), "0.1.0")
	if err != nil {
		t.Fatalf("check version: %v", err)
	}
	if versionInfo == nil {
		t.Fatalf("expected version info, got nil")
	}
	if versionInfo.CurrentVersion != "0.1.0" || versionInfo.LatestVersion != "0.2.0" || !versionInfo.AutoUpdateEnabled {
		t.Fatalf("unexpected version info: %+v", versionInfo)
	}
	if versionInfo.DownloadURL == nil || *versionInfo.DownloadURL != downloadURL {
		t.Fatalf("unexpected download url: %v", versionInfo.DownloadURL)
	}
	if versionInfo.Signature == nil || *versionInfo.Signature != signature {
		t.Fatalf("unexpected signature: %v", versionInfo.Signature)
	}
}

func TestCheckVersionHandlesServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer server.Close()

	c, err := New(config.Config{
		BackendURL:   server.URL,
		WatchFolder:  "/watch",
		ClientID:     "client-1",
		APIKey:       "secret",
		SessionToken: "session-1",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	versionInfo, err := c.CheckVersion(context.Background(), "0.1.0")
	if err == nil {
		t.Fatalf("expected error for 500 status")
	}
	if versionInfo != nil {
		t.Fatalf("expected nil version info on error, got %+v", versionInfo)
	}
}

func TestCheckVersionHandlesUnreachableServer(t *testing.T) {
	c, err := New(config.Config{
		BackendURL:   "http://127.0.0.1:1",
		WatchFolder:  "/watch",
		ClientID:     "client-1",
		APIKey:       "secret",
		SessionToken: "session-1",
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	c.httpClient.Timeout = 200 * time.Millisecond

	versionInfo, err := c.CheckVersion(context.Background(), "0.1.0")
	if err == nil {
		t.Fatalf("expected error for unreachable server")
	}
	if versionInfo != nil {
		t.Fatalf("expected nil version info on error, got %+v", versionInfo)
	}
}
