package client

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/json"
	"encoding/pem"
	"errors"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"autologbook/data-service/internal/config"
)

// generateTestCA generates a self-signed CA certificate for testing purposes.
// Returns PEM-encoded certificate bytes.
func generateTestCA(t *testing.T) []byte {
	// Generate a new RSA key
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate RSA key: %v", err)
	}

	// Create a certificate template
	notBefore := time.Now()
	notAfter := notBefore.Add(365 * 24 * time.Hour)

	serialNumber, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		t.Fatalf("generate serial number: %v", err)
	}

	template := x509.Certificate{
		SerialNumber: serialNumber,
		Subject: pkix.Name{
			Organization: []string{"Test CA"},
			Country:      []string{"US"},
		},
		NotBefore:             notBefore,
		NotAfter:              notAfter,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
		BasicConstraintsValid: true,
		IsCA:                  true,
	}

	// Self-sign the certificate
	certDER, err := x509.CreateCertificate(rand.Reader, &template, &template, &priv.PublicKey, priv)
	if err != nil {
		t.Fatalf("create certificate: %v", err)
	}

	// Encode to PEM
	certPEM := pem.EncodeToMemory(&pem.Block{
		Type:  "CERTIFICATE",
		Bytes: certDER,
	})

	return certPEM
}

func newTestCertFile(t *testing.T) string {
	tmpfile, err := os.CreateTemp("", "test-ca-*.pem")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	certPEM := generateTestCA(t)
	if _, err := tmpfile.Write(certPEM); err != nil {
		tmpfile.Close()
		os.Remove(tmpfile.Name())
		t.Fatalf("write cert: %v", err)
	}
	tmpfile.Close()
	t.Cleanup(func() { os.Remove(tmpfile.Name()) })
	return tmpfile.Name()
}

func TestBuildHTTPClientUsesOSTrustStore(t *testing.T) {
	cfg := config.Config{
		BackendURL:  "https://backend",
		WatchFolder: "/watch",
		CACertPath:  "", // No custom CA
	}

	client, err := buildHTTPClient(cfg)
	if err != nil {
		t.Fatalf("buildHTTPClient: %v", err)
	}

	if client == nil {
		t.Fatalf("expected non-nil client")
	}
	if client.Timeout != 30*time.Second {
		t.Fatalf("unexpected timeout: %v", client.Timeout)
	}

	transport, ok := client.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("expected *http.Transport, got %T", client.Transport)
	}

	if transport.TLSClientConfig == nil {
		t.Fatalf("TLSClientConfig is nil")
	}
	if transport.TLSClientConfig.MinVersion != tls.VersionTLS12 {
		t.Fatalf("MinVersion: want %d, got %d", tls.VersionTLS12, transport.TLSClientConfig.MinVersion)
	}
	if transport.TLSClientConfig.InsecureSkipVerify {
		t.Fatalf("InsecureSkipVerify must be false (SRS §8.1)")
	}
	// When no custom CA is provided, RootCAs should be nil (uses OS trust store)
	if transport.TLSClientConfig.RootCAs != nil {
		t.Fatalf("RootCAs should be nil when using OS trust store, got %v", transport.TLSClientConfig.RootCAs)
	}
}

func TestBuildHTTPClientWithCustomCA(t *testing.T) {
	certPath := newTestCertFile(t)

	cfg := config.Config{
		BackendURL:  "https://backend",
		WatchFolder: "/watch",
		CACertPath:  certPath,
	}

	client, err := buildHTTPClient(cfg)
	if err != nil {
		t.Fatalf("buildHTTPClient: %v", err)
	}

	if client == nil {
		t.Fatalf("expected non-nil client")
	}

	transport, ok := client.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("expected *http.Transport, got %T", client.Transport)
	}

	if transport.TLSClientConfig == nil {
		t.Fatalf("TLSClientConfig is nil")
	}
	if transport.TLSClientConfig.InsecureSkipVerify {
		t.Fatalf("InsecureSkipVerify must be false (SRS §8.1)")
	}
	// When custom CA is provided, RootCAs should be set
	if transport.TLSClientConfig.RootCAs == nil {
		t.Fatalf("RootCAs should not be nil when custom CA is configured")
	}
}

func TestBuildHTTPClientCAFileNotFound(t *testing.T) {
	cfg := config.Config{
		BackendURL:  "https://backend",
		WatchFolder: "/watch",
		CACertPath:  "/nonexistent/path/ca.pem",
	}

	_, err := buildHTTPClient(cfg)
	if err == nil {
		t.Fatalf("expected error for missing CA file")
	}
	if !strings.Contains(err.Error(), "failed to read CA certificate file") {
		t.Fatalf("unexpected error message: %v", err)
	}
}

func TestBuildHTTPClientInvalidPEM(t *testing.T) {
	tmpfile, err := os.CreateTemp("", "invalid-*.pem")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	defer os.Remove(tmpfile.Name())

	// Write invalid PEM content
	if _, err := tmpfile.WriteString("not a valid pem file"); err != nil {
		t.Fatalf("write invalid pem: %v", err)
	}
	tmpfile.Close()

	cfg := config.Config{
		BackendURL:  "https://backend",
		WatchFolder: "/watch",
		CACertPath:  tmpfile.Name(),
	}

	_, err = buildHTTPClient(cfg)
	if err == nil {
		t.Fatalf("expected error for invalid PEM")
	}
	if !strings.Contains(err.Error(), "failed to parse CA certificate") {
		t.Fatalf("unexpected error message: %v", err)
	}
}

func TestBuildTLSConfigInsecureSkipVerifyAlwaysFalse(t *testing.T) {
	// This test documents the security invariant: InsecureSkipVerify must always be false
	tlsConfig, err := buildTLSConfig("")
	if err != nil {
		t.Fatalf("buildTLSConfig: %v", err)
	}

	if tlsConfig.InsecureSkipVerify {
		t.Fatalf("InsecureSkipVerify must be false per SRS §8.1")
	}
}


func TestRegister(t *testing.T) {
	var registerPayload map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/data-service/register" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if err := json.NewDecoder(r.Body).Decode(&registerPayload); err != nil {
			t.Fatalf("decode register payload: %v", err)
		}
		_ = json.NewEncoder(w).Encode(map[string]string{
			"client_id": "client-1",
			"api_key":   "secret",
		})
	}))
	defer server.Close()

	c, err := New(config.Config{BackendURL: server.URL, WatchFolder: "/watch", RegistrationSecret: "registration-secret"})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	clientID, apiKey, err := c.Register(context.Background(), "host", "/watch", "linux", "0.1.0")
	if err != nil {
		t.Fatalf("register: %v", err)
	}
	if clientID != "client-1" || apiKey != "secret" {
		t.Fatalf("unexpected register response: %q %q", clientID, apiKey)
	}
	if registerPayload["registration_secret"] != "registration-secret" {
		t.Fatalf("expected registration_secret in payload, got %v", registerPayload["registration_secret"])
	}
}

func TestRegisterHandlesServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer server.Close()

	c, err := New(config.Config{BackendURL: server.URL, WatchFolder: "/watch", RegistrationSecret: "registration-secret"})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	_, _, err = c.Register(context.Background(), "host", "/watch", "linux", "0.1.0")
	if err == nil || !strings.Contains(err.Error(), "500") {
		t.Fatalf("expected 500 error, got %v", err)
	}
}

func TestRegisterHandlesForbiddenWithoutRetry(t *testing.T) {
	var registerCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/data-service/register" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		registerCalls++
		http.Error(w, "invalid registration_secret", http.StatusForbidden)
	}))
	defer server.Close()

	c, err := New(config.Config{BackendURL: server.URL, WatchFolder: "/watch", RegistrationSecret: "bad-secret"})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}

	_, _, err = c.Register(context.Background(), "host", "/watch", "linux", "0.1.0")
	if err == nil {
		t.Fatalf("expected forbidden error")
	}
	if err.Error() != "registration rejected: invalid registration_secret - check config" {
		t.Fatalf("unexpected error: %v", err)
	}
	if registerCalls != 1 {
		t.Fatalf("register calls = %d, want 1", registerCalls)
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

func TestCheckVersion(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Fatalf("expected GET, got %s", r.Method)
		}
		if r.URL.Path != "/api/v1/data-service/version" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer session-1" {
			t.Fatalf("missing bearer auth")
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"latest_version":        "1.2.0",
			"auto_update_enabled":   true,
			"min_supported_version": "1.0.0",
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

	versionInfo, err := c.CheckVersion(context.Background(), "1.0.0")
	if err != nil {
		t.Fatalf("check version: %v", err)
	}
	if versionInfo.CurrentVersion != "1.0.0" {
		t.Fatalf("unexpected current version: %q", versionInfo.CurrentVersion)
	}
	if versionInfo.LatestVersion != "1.2.0" {
		t.Fatalf("unexpected latest version: %q", versionInfo.LatestVersion)
	}
	if !versionInfo.AutoUpdateEnabled {
		t.Fatalf("auto update should be enabled")
	}
	if versionInfo.MinSupportedVersion != "1.0.0" {
		t.Fatalf("unexpected min supported version: %q", versionInfo.MinSupportedVersion)
	}
}

func TestCheckVersionAutoUpdateDisabled(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"latest_version":        "2.0.0",
			"auto_update_enabled":   false,
			"min_supported_version": "1.5.0",
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

	versionInfo, err := c.CheckVersion(context.Background(), "1.0.0")
	if err != nil {
		t.Fatalf("check version: %v", err)
	}
	if versionInfo.AutoUpdateEnabled {
		t.Fatalf("auto update should be disabled")
	}
	if versionInfo.LatestVersion != "2.0.0" {
		t.Fatalf("unexpected latest version: %q", versionInfo.LatestVersion)
	}
}

func TestCheckVersionHandlesUnauthorized(t *testing.T) {
	var calls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/data-service/version":
			calls++
			if calls == 1 {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"latest_version":      "1.5.0",
				"auto_update_enabled": true,
			})
		case "/api/v1/data-service/auth":
			_ = json.NewEncoder(w).Encode(map[string]string{
				"session_token": "session-2",
				"expires_at":    "2026-04-09T12:00:00Z",
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

	versionInfo, err := c.CheckVersion(context.Background(), "1.0.0")
	if err != nil {
		t.Fatalf("check version with auth retry: %v", err)
	}
	if versionInfo.LatestVersion != "1.5.0" {
		t.Fatalf("unexpected latest version: %q", versionInfo.LatestVersion)
	}
	if calls != 2 {
		t.Fatalf("expected 2 calls (1 unauthorized, 1 after auth), got %d", calls)
	}
}

func TestCheckVersionHandlesServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal server error", http.StatusInternalServerError)
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

	_, err = c.CheckVersion(context.Background(), "1.0.0")
	if err == nil || !strings.Contains(err.Error(), "500") {
		t.Fatalf("expected 500 error, got %v", err)
	}
}

