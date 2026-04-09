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
	"autologbook/data-service/internal/watcher"
)

const agentVersion = "0.1.0"

func main() {
	configPath := flag.String("config", "config.toml", "Path to TOML config file")
	flag.Parse()

	logger := log.New(os.Stdout, "agent: ", log.LstdFlags)
	cfg, err := config.Load(*configPath)
	if err != nil {
		logger.Fatalf("load config: %v", err)
	}

	apiClient, err := client.New(cfg)
	if err != nil {
		logger.Fatalf("create client: %v", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := bootstrap(ctx, *configPath, &cfg, apiClient); err != nil {
		logger.Fatalf("bootstrap: %v", err)
	}

	uploadQueue, err := queue.Open("", apiClient)
	if err != nil {
		logger.Fatalf("open queue: %v", err)
	}
	defer uploadQueue.Close()

	fileWatcher, err := watcher.New(cfg.WatchFolder, apiClient, uploadQueue, logger)
	if err != nil {
		logger.Fatalf("create watcher: %v", err)
	}
	defer fileWatcher.Close()

	go func() {
		if err := fileWatcher.Start(ctx); err != nil && !errors.Is(err, context.Canceled) {
			logger.Printf("watcher stopped: %v", err)
			stop()
		}
	}()

	go runQueueProcessor(ctx, logger, uploadQueue)
	runHeartbeatLoop(ctx, logger, apiClient, cfg)
}

func bootstrap(ctx context.Context, configPath string, cfg *config.Config, apiClient *client.Client) error {
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
