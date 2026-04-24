package client

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path"
	"strings"
	"sync"
	"time"

	"autologbook/data-service/internal/config"
)

var errUnauthorized = errors.New("unauthorized")

// ErrPermanentFailure indicates that the request failed in a way that should not be retried.
var ErrPermanentFailure = errors.New("permanent failure: do not retry")

type Decision string

const (
	DecisionAccept Decision = "ACCEPT"
	DecisionIgnore Decision = "IGNORE"
)

type Task struct {
	ID        string         `json:"id"`
	TaskType  string         `json:"task_type"`
	Operation string         `json:"operation"`
	Params    map[string]any `json:"params"`
}

type registerRequest struct {
	Hostname           string `json:"hostname"`
	WatchFolder        string `json:"watch_folder"`
	OSInfo             string `json:"os_info"`
	AgentVersion       string `json:"agent_version"`
	RegistrationSecret string `json:"registration_secret"`
}

type registerResponse struct {
	ClientID string `json:"client_id"`
	APIKey   string `json:"api_key"`
}

type authRequest struct {
	ClientID string `json:"client_id"`
	APIKey   string `json:"api_key"`
}

type authResponse struct {
	SessionToken string    `json:"session_token"`
	ExpiresAt    time.Time `json:"expires_at"`
}

type heartbeatRequest struct {
	ClientID     string         `json:"client_id"`
	AgentVersion string         `json:"agent_version"`
	StatusInfo   map[string]any `json:"status_info"`
}

type heartbeatResponse struct {
	Tasks []Task `json:"tasks"`
}

type VersionInfo struct {
	CurrentVersion    string  `json:"current_version"`
	LatestVersion     string  `json:"latest_version"`
	AutoUpdateEnabled bool    `json:"auto_update_enabled"`
	DownloadURL       *string `json:"download_url"`
	Signature         *string `json:"signature"`
}

type fileNotifyRequest struct {
	RelativePath string `json:"relative_path"`
	Filename     string `json:"filename"`
	FileSize     int64  `json:"file_size"`
}

type fileNotifyResponse struct {
	Decision  Decision `json:"decision"`
	ContextID string   `json:"context_id"`
	Reason    string   `json:"reason"`
}

type taskAckRequest struct {
	TaskID       string `json:"task_id"`
	Status       string `json:"status"`
	ErrorMessage string `json:"error_message,omitempty"`
}

type Client struct {
	baseURL    string
	httpClient *http.Client
	clientID   string
	apiKey     string
	mu         sync.RWMutex
	session    string
}

func New(cfg config.Config) (*Client, error) {
	httpClient, err := buildHTTPClient(&cfg)
	if err != nil {
		return nil, err
	}

	return &Client{
		baseURL:    strings.TrimRight(cfg.BackendURL, "/"),
		httpClient: httpClient,
		clientID:   cfg.ClientID,
		apiKey:     cfg.APIKey,
		session:    cfg.SessionToken,
	}, nil
}

// buildHTTPClient constructs an HTTP client with proper TLS configuration.
// If cfg.CACertPath is set, it loads the CA certificate; otherwise uses OS trust store.
// InsecureSkipVerify is always false (SRS §8.1).
func buildHTTPClient(cfg *config.Config) (*http.Client, error) {
	tlsConfig := &tls.Config{
		MinVersion:         tls.VersionTLS12,
		InsecureSkipVerify: false, // SRS §8.1: MUST always be false — do not change
	}

	if cfg.CACertPath != "" {
		pemBytes, err := os.ReadFile(cfg.CACertPath)
		if err != nil {
			return nil, fmt.Errorf("failed to read CA certificate file: %w", err)
		}

		pool, err := x509.SystemCertPool()
		if err != nil || pool == nil {
			pool = x509.NewCertPool()
		}
		if !pool.AppendCertsFromPEM(pemBytes) {
			return nil, errors.New("failed to append CA certificate: no valid PEM certificates found")
		}
		tlsConfig.RootCAs = pool
	}

	return &http.Client{
		Timeout: 30 * time.Second,
		Transport: &http.Transport{
			TLSClientConfig: tlsConfig,
		},
	}, nil
}

func (c *Client) ClientID() string {
	return c.clientID
}

func (c *Client) SessionToken() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.session
}

func (c *Client) setSessionToken(token string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.session = token
}

func (c *Client) Register(ctx context.Context, hostname, watchFolder, osInfo, agentVersion, registrationSecret string) (string, string, error) {
	reqBody := registerRequest{
		Hostname:           hostname,
		WatchFolder:        watchFolder,
		OSInfo:             osInfo,
		AgentVersion:       agentVersion,
		RegistrationSecret: registrationSecret,
	}

	var resp registerResponse
	bodyBytes, err := json.Marshal(reqBody)
	if err != nil {
		return "", "", err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.url("/api/v1/data-service/register"), bytes.NewReader(bodyBytes))
	if err != nil {
		return "", "", err
	}
	req.Header.Set("Content-Type", "application/json")

	httpResp, err := c.httpClient.Do(req)
	if err != nil {
		return "", "", err
	}
	defer httpResp.Body.Close()

	// Handle 403 explicitly (do NOT retry on 403)
	if httpResp.StatusCode == http.StatusForbidden {
		return "", "", fmt.Errorf(
			"registration rejected (403): invalid registration_secret — "+
				"check config.toml registration_secret field",
		)
	}

	if err := decodeStatus(httpResp); err != nil {
		return "", "", err
	}

	if err := json.NewDecoder(httpResp.Body).Decode(&resp); err != nil {
		return "", "", err
	}

	c.clientID = resp.ClientID
	c.apiKey = resp.APIKey
	return resp.ClientID, resp.APIKey, nil
}

func (c *Client) Auth(ctx context.Context) (string, time.Time, error) {
	reqBody := authRequest{
		ClientID: c.clientID,
		APIKey:   c.apiKey,
	}

	var resp authResponse
	if err := c.doJSON(ctx, http.MethodPost, "/api/v1/data-service/auth", reqBody, &resp, ""); err != nil {
		return "", time.Time{}, err
	}

	c.setSessionToken(resp.SessionToken)
	return resp.SessionToken, resp.ExpiresAt, nil
}

func (c *Client) Heartbeat(ctx context.Context, clientID, agentVersion string, statusInfo map[string]any) ([]Task, error) {
	reqBody := heartbeatRequest{
		ClientID:     clientID,
		AgentVersion: agentVersion,
		StatusInfo:   statusInfo,
	}

	var resp heartbeatResponse
	err := c.withAuthRetry(ctx, func(token string) error {
		return c.doJSON(ctx, http.MethodPost, "/api/v1/data-service/heartbeat", reqBody, &resp, token)
	})
	if err != nil {
		return nil, err
	}
	return resp.Tasks, nil
}

func (c *Client) CheckVersion(ctx context.Context, agentVersion string) (*VersionInfo, error) {
	var resp VersionInfo

	err := c.withAuthRetry(ctx, func(token string) error {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.url("/api/v1/data-service/version"), nil)
		if err != nil {
			return err
		}
		if token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
		if agentVersion != "" {
			req.Header.Set("X-Agent-Version", agentVersion)
		}

		httpResp, err := c.httpClient.Do(req)
		if err != nil {
			return err
		}
		defer httpResp.Body.Close()

		if err := decodeStatus(httpResp); err != nil {
			return err
		}

		return json.NewDecoder(httpResp.Body).Decode(&resp)
	})
	if err != nil {
		return nil, err
	}

	return &resp, nil
}

func (c *Client) FileNotify(ctx context.Context, relativePath, filename string, fileSize int64) (Decision, string, error) {
	reqBody := fileNotifyRequest{
		RelativePath: relativePath,
		Filename:     filename,
		FileSize:     fileSize,
	}

	var resp fileNotifyResponse
	err := c.withAuthRetry(ctx, func(token string) error {
		return c.doJSON(ctx, http.MethodPost, "/api/v1/data-service/file-notify", reqBody, &resp, token)
	})
	if err != nil {
		return "", "", err
	}
	return resp.Decision, resp.ContextID, nil
}

func (c *Client) Upload(ctx context.Context, contextID, filename string, reader io.Reader) error {
	data, err := io.ReadAll(reader)
	if err != nil {
		return err
	}

	return c.withAuthRetry(ctx, func(token string) error {
		body := &bytes.Buffer{}
		writer := multipart.NewWriter(body)

		if err := writer.WriteField("context_id", contextID); err != nil {
			return err
		}
		if err := writer.WriteField("filename", filename); err != nil {
			return err
		}

		part, err := writer.CreateFormFile("file", filename)
		if err != nil {
			return err
		}
		if _, err := part.Write(data); err != nil {
			return err
		}
		if err := writer.Close(); err != nil {
			return err
		}

		req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.url("/api/v1/data-service/upload"), body)
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", writer.FormDataContentType())
		if token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}

		resp, err := c.httpClient.Do(req)
		if err != nil {
			return err
		}
		defer resp.Body.Close()

		// Handle permanent failures explicitly
		if resp.StatusCode == http.StatusBadRequest {
			respBody, _ := io.ReadAll(resp.Body)
			errorMsg := strings.TrimSpace(string(respBody))
			return fmt.Errorf("%w: HTTP 400 Bad Request: %s", ErrPermanentFailure, errorMsg)
		}
		if resp.StatusCode == http.StatusForbidden {
			return fmt.Errorf("%w: HTTP 403 Forbidden (client revoked)", ErrPermanentFailure)
		}

		return decodeStatus(resp)
	})
}

func (c *Client) TaskAck(ctx context.Context, taskID, statusText, errMessage string) error {
	reqBody := taskAckRequest{
		TaskID:       taskID,
		Status:       statusText,
		ErrorMessage: errMessage,
	}

	return c.withAuthRetry(ctx, func(token string) error {
		return c.doJSON(ctx, http.MethodPost, "/api/v1/data-service/task-ack", reqBody, nil, token)
	})
}

func (c *Client) withAuthRetry(ctx context.Context, fn func(token string) error) error {
	token := c.SessionToken()
	err := fn(token)
	if !errors.Is(err, errUnauthorized) {
		return err
	}

	if _, _, authErr := c.Auth(ctx); authErr != nil {
		return authErr
	}
	return fn(c.SessionToken())
}

func (c *Client) doJSON(ctx context.Context, method, endpoint string, requestBody any, responseBody any, bearerToken string, extraHeaders ...map[string]string) error {
	bodyBytes, err := json.Marshal(requestBody)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, method, c.url(endpoint), bytes.NewReader(bodyBytes))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if bearerToken != "" {
		req.Header.Set("Authorization", "Bearer "+bearerToken)
	}
	if len(extraHeaders) > 0 {
		for key, value := range extraHeaders[0] {
			if value != "" {
				req.Header.Set(key, value)
			}
		}
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if err := decodeStatus(resp); err != nil {
		return err
	}
	if responseBody == nil || resp.StatusCode == http.StatusNoContent {
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(responseBody)
}

func (c *Client) url(endpoint string) string {
	return c.baseURL + path.Clean("/"+endpoint)
}

func decodeStatus(resp *http.Response) error {
	if resp.StatusCode == http.StatusUnauthorized {
		return errUnauthorized
	}
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		return nil
	}
	// 429 is retryable (rate limit); let the caller handle retry logic
	if resp.StatusCode == http.StatusTooManyRequests {
		return fmt.Errorf("rate limited: HTTP 429")
	}
	body, _ := io.ReadAll(resp.Body)
	if len(body) == 0 {
		return fmt.Errorf("request failed with status %d", resp.StatusCode)
	}
	return fmt.Errorf("request failed with status %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
}
