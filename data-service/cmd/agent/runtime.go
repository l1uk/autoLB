package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"runtime"
	"sync"

	"autologbook/data-service/internal/client"
	"autologbook/data-service/internal/config"
	"autologbook/data-service/internal/queue"
	"autologbook/data-service/internal/watcher"
	"github.com/kardianos/service"
	"gopkg.in/natefinch/lumberjack.v2"
)

const serviceName = "autologbook-data-service"

func normalizeConfigPath(configPath string, forceAbsolute bool) (string, error) {
	if !forceAbsolute || filepath.IsAbs(configPath) {
		return configPath, nil
	}

	resolved, err := filepath.Abs(configPath)
	if err != nil {
		return "", err
	}
	return resolved, nil
}

func newAgentLogger(interactive bool) (*log.Logger, error) {
	if interactive {
		return log.New(os.Stdout, "agent: ", log.LstdFlags|log.Lmicroseconds), nil
	}

	logPath, err := serviceLogPath()
	if err != nil {
		return nil, err
	}

	if err := os.MkdirAll(filepath.Dir(logPath), 0o755); err != nil {
		return nil, err
	}

	writer := &lumberjack.Logger{
		Filename:   logPath,
		MaxSize:    10,
		MaxBackups: 10,
		MaxAge:     30,
		Compress:   true,
	}
	return log.New(writer, "agent: ", log.LstdFlags|log.Lmicroseconds), nil
}

func serviceLogPath() (string, error) {
	programData := os.Getenv("ProgramData")
	if programData == "" {
		if runtime.GOOS == "windows" {
			programData = `C:\ProgramData`
		} else {
			programData = filepath.Join(os.TempDir(), "ProgramData")
		}
	}

	if programData == "" {
		return "", fmt.Errorf("program data directory is not configured")
	}

	return filepath.Join(programData, "autologbook", "logs", "agent.log"), nil
}

type agentRuntime struct {
	cfg         *config.Config
	apiClient   *client.Client
	logger      *log.Logger
	uploadQueue *queue.Queue
	fileWatcher *watcher.Watcher
}

func newAgentRuntime(ctx context.Context, configPath string, cfg *config.Config, apiClient *client.Client, logger *log.Logger) (*agentRuntime, error) {
	if err := bootstrap(ctx, configPath, cfg, apiClient); err != nil {
		return nil, err
	}

	uploadQueue, err := queue.Open("", apiClient)
	if err != nil {
		return nil, err
	}

	fileWatcher, err := watcher.New(cfg.WatchFolder, apiClient, uploadQueue, logger)
	if err != nil {
		_ = uploadQueue.Close()
		return nil, err
	}

	return &agentRuntime{
		cfg:         cfg,
		apiClient:   apiClient,
		logger:      logger,
		uploadQueue: uploadQueue,
		fileWatcher: fileWatcher,
	}, nil
}

func (r *agentRuntime) run(parentCtx context.Context) error {
	ctx, cancel := context.WithCancel(parentCtx)
	defer cancel()
	defer r.fileWatcher.Close()
	defer r.uploadQueue.Close()

	fatalErr := make(chan error, 1)
	var once sync.Once

	go func() {
		if err := r.fileWatcher.Start(ctx); err != nil && !errors.Is(err, context.Canceled) {
			once.Do(func() {
				fatalErr <- err
			})
			cancel()
		}
	}()

	go runQueueProcessor(ctx, r.logger, r.uploadQueue)
	runHeartbeatLoop(ctx, r.logger, r.apiClient, *r.cfg)

	select {
	case err := <-fatalErr:
		return err
	default:
		return nil
	}
}

type agentServiceProgram struct {
	configPath string
	cfg        *config.Config
	apiClient  *client.Client
	logger     *log.Logger

	cancel context.CancelFunc
	done   chan struct{}
}

func newAgentService(configPath string, cfg *config.Config, apiClient *client.Client, logger *log.Logger) (service.Service, error) {
	program := &agentServiceProgram{
		configPath: configPath,
		cfg:        cfg,
		apiClient:  apiClient,
		logger:     logger,
	}

	resolvedConfigPath := configPath
	if !filepath.IsAbs(resolvedConfigPath) {
		absPath, err := filepath.Abs(resolvedConfigPath)
		if err != nil {
			return nil, err
		}
		resolvedConfigPath = absPath
	}

	return service.New(program, &service.Config{
		Name:        serviceName,
		DisplayName: "Autologbook Data Service",
		Description: "Autologbook acquisition agent",
		Arguments:   []string{"-config", resolvedConfigPath},
	})
}

func (p *agentServiceProgram) Start(s service.Service) error {
	runtime, err := newAgentRuntime(context.Background(), p.configPath, p.cfg, p.apiClient, p.logger)
	if err != nil {
		return err
	}

	ctx, cancel := context.WithCancel(context.Background())
	p.cancel = cancel
	p.done = make(chan struct{})

	go func() {
		defer close(p.done)
		if err := runtime.run(ctx); err != nil && !errors.Is(err, context.Canceled) {
			p.logger.Printf("service stopped unexpectedly: %v", err)
			if stopErr := s.Stop(); stopErr != nil {
				p.logger.Printf("service stop request failed: %v", stopErr)
			}
		}
	}()

	return nil
}

func (p *agentServiceProgram) Stop(service.Service) error {
	if p.cancel != nil {
		p.cancel()
	}
	if p.done != nil {
		<-p.done
	}
	return nil
}
