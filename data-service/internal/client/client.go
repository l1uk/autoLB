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
	baseURL            string
	httpClient         *http.Client
	clientID           string
	apiKey             string
	registrationSecret string
	mu                 sync.RWMutex
	session            string
}

func New(cfg config.Config) (*Client, error) {
	tlsConfig, err := buildTLSConfig(cfg.CACertPath)
	if err != nil {
		return nil, err
	}

	return &Client{
		baseURL: strings.TrimRight(cfg.BackendURL, "/"),
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
			Transport: &http.Transport{
				TLSClientConfig: tlsConfig,
			},
		},
		clientID: cfg.ClientID,
		apiKey:   cfg.APIKey,
		registrationSecret: cfg.RegistrationSecret,
		session:  cfg.SessionToken,
	}, nil
}

func ensureSecureTLSConfig(tlsConfig *tls.Config) {
	if tlsConfig.InsecureSkipVerify {
		panic("insecure TLS configuration: InsecureSkipVerify must remain false")
	}
}

func buildTLSConfig(caCertPath string) (*tls.Config, error) {
	tlsConfig := &tls.Config{
		MinVersion:         tls.VersionTLS12,
		InsecureSkipVerify: false,
	}
	ensureSecureTLSConfig(tlsConfig)
	if caCertPath == "" {
		return tlsConfig, nil
	}

	pemBytes, err := os.ReadFile(caCertPath)
	if err != nil {
		return nil, err
	}

	pool, err := x509.SystemCertPool()
	if err != nil || pool == nil {
		pool = x509.NewCertPool()
	}
	if !pool.AppendCertsFromPEM(pemBytes) {
		return nil, errors.New("failed to append CA certificate")
	}

	tlsConfig.RootCAs = pool
	ensureSecureTLSConfig(tlsConfig)
	return tlsConfig, nil
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

func (c *Client) Register(ctx context.Context, hostname, watchFolder, osInfo, agentVersion string) (string, string, error) {
	reqBody := registerRequest{
		Hostname:           hostname,
		WatchFolder:        watchFolder,
		OSInfo:             osInfo,
		AgentVersion:       agentVersion,
		RegistrationSecret: c.registrationSecret,
	}

	var resp registerResponse
	if err := c.doJSON(ctx, http.MethodPost, "/api/v1/data-service/register", reqBody, &resp, ""); err != nil {
		var statusErr *httpStatusError
		if errors.As(err, &statusErr) && statusErr.statusCode == http.StatusForbidden {
			return "", "", errors.New("registration rejected: invalid registration_secret - check config")
		}
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
	body, _ := io.ReadAll(resp.Body)
	return &httpStatusError{
		statusCode: resp.StatusCode,
		body:       strings.TrimSpace(string(body)),
	}
}

type httpStatusError struct {
	statusCode int
	body       string
}

func (e *httpStatusError) Error() string {
	if e.body == "" {
		return fmt.Sprintf("request failed with status %d", e.statusCode)
	}
	return fmt.Sprintf("request failed with status %d: %s", e.statusCode, e.body)
}
