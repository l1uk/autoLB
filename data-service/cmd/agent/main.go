package main

import (
	"context"
	"errors"
	"flag"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"syscall"
	"time"

	"autologbook/data-service/internal/client"
	"autologbook/data-service/internal/config"
	"autologbook/data-service/internal/queue"
	"github.com/kardianos/service"
)

const agentVersion = "0.1.0"

func main() {
	configPath := flag.String("config", "config.toml", "Path to TOML config file")
	serviceAction := flag.String("service", "", "Service control action: install, uninstall, start, stop, restart")
	flag.Parse()

	interactive := service.Interactive()
	logger, err := newAgentLogger(interactive)
	if err != nil {
		log.Fatalf("create logger: %v", err)
	}

	resolvedConfigPath, err := normalizeConfigPath(*configPath, !interactive || *serviceAction != "")
	if err != nil {
		logger.Fatalf("resolve config path: %v", err)
	}
	logger.Printf("agent starting mode=%s config=%s", map[bool]string{true: "interactive", false: "service"}[interactive], resolvedConfigPath)

	cfg, err := config.Load(resolvedConfigPath)
	if err != nil {
		logger.Fatalf("load config: %v", err)
	}
	logger.Printf("config loaded backend=%s watch_folder=%s heartbeat_interval=%s", cfg.BackendURL, cfg.WatchFolder, cfg.HeartbeatInterval)

	apiClient, err := client.New(cfg)
	if err != nil {
		logger.Fatalf("create client: %v", err)
	}

	if *serviceAction != "" {
		svc, err := newAgentService(resolvedConfigPath, &cfg, apiClient, logger)
		if err != nil {
			logger.Fatalf("create service: %v", err)
		}

		if err := service.Control(svc, *serviceAction); err != nil {
			logger.Fatalf("service %s: %v", *serviceAction, err)
		}
		return
	}

	if interactive {
		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
		defer stop()

		runtime, err := newAgentRuntime(ctx, resolvedConfigPath, &cfg, apiClient, logger)
		if err != nil {
			logger.Fatalf("bootstrap: %v", err)
		}

		if err := runtime.run(ctx); err != nil && !errors.Is(err, context.Canceled) {
			logger.Fatalf("agent stopped: %v", err)
		}
		return
	}

	svc, err := newAgentService(resolvedConfigPath, &cfg, apiClient, logger)
	if err != nil {
		logger.Fatalf("create service: %v", err)
	}
	if err := svc.Run(); err != nil {
		logger.Fatalf("run service: %v", err)
	}
}

type registrationClient interface {
	Register(ctx context.Context, hostname, watchFolder, osInfo, agentVersion string) (string, string, error)
	Auth(ctx context.Context) (string, time.Time, error)
}

func bootstrap(ctx context.Context, configPath string, cfg *config.Config, apiClient registrationClient) error {
	if cfg.ClientID == "" {
		hostname, err := os.Hostname()
		if err != nil {
			return err
		}

		clientID, apiKey, err := apiClient.Register(ctx, hostname, cfg.WatchFolder, runtime.GOOS+"/"+runtime.GOARCH, agentVersion)
		if err != nil {
			return err
		}
		cfg.ClientID = clientID
		cfg.APIKey = apiKey
	}

	sessionToken, _, err := apiClient.Auth(ctx)
	if err != nil {
		return err
	}
	cfg.SessionToken = sessionToken
	return cfg.Save(configPath)
}

func runQueueProcessor(ctx context.Context, logger *log.Logger, uploadQueue *queue.Queue) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			processed, err := uploadQueue.ProcessNext(ctx)
			if err != nil {
				logger.Printf("queue process failed: %v", err)
				continue
			}
			if !processed {
				continue
			}
		}
	}
}

func runHeartbeatLoop(ctx context.Context, logger *log.Logger, apiClient *client.Client, cfg config.Config) {
	ticker := time.NewTicker(cfg.HeartbeatInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			tasks, err := apiClient.Heartbeat(ctx, cfg.ClientID, agentVersion, map[string]any{"watch_folder": cfg.WatchFolder})
			if err != nil {
				logger.Printf("heartbeat failed: %v", err)
				continue
			}

			// RF-24: Check for available version updates after successful heartbeat.
			// Errors are logged but do not crash the heartbeat loop.
			versionInfo, err := apiClient.CheckVersion(ctx, agentVersion)
			if err != nil {
				logger.Printf("version check failed: %v", err)
			} else {
				if versionInfo.LatestVersion != versionInfo.CurrentVersion {
					if versionInfo.AutoUpdateEnabled {
						logger.Printf("WARNING: new data-service version available: %s (running %s) — auto-update pending manual implementation", versionInfo.LatestVersion, versionInfo.CurrentVersion)
					} else {
						logger.Printf("INFO: new data-service version available: %s (running %s) — auto-update disabled", versionInfo.LatestVersion, versionInfo.CurrentVersion)
					}
				}
			}

			for _, task := range tasks {
				if err := executeTask(ctx, apiClient, cfg.WatchFolder, task); err != nil {
					logger.Printf("task %s failed: %v", task.ID, err)
				}
			}
		}
	}
}

func executeTask(ctx context.Context, apiClient *client.Client, watchFolder string, task client.Task) error {
	var taskErr error
	statusText := "SUCCESS"

	if (task.TaskType == "FILESYSTEM" && task.Operation == "CREATE_DIR") || task.TaskType == "CREATE_DIR" {
		targetPath, _ := task.Params["path"].(string)
		if targetPath == "" {
			taskErr = errors.New("task path missing")
		} else {
			taskErr = os.MkdirAll(filepath.Join(watchFolder, targetPath), 0o755)
		}
	} else {
		taskErr = errors.New("unsupported task")
	}

	errorMessage := ""
	if taskErr != nil {
		statusText = "ERROR"
		errorMessage = taskErr.Error()
	}

	ackErr := apiClient.TaskAck(ctx, task.ID, statusText, errorMessage)
	if ackErr != nil {
		return ackErr
	}
	return taskErr
}
