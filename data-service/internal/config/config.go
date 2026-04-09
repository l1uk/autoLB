package config

import (
	"errors"
	"os"
	"time"

	"github.com/BurntSushi/toml"
)

const DefaultHeartbeatInterval = 30 * time.Second

type Config struct {
	BackendURL        string        `toml:"backend_url"`
	ClientID          string        `toml:"client_id"`
	APIKey            string        `toml:"api_key"`
	SessionToken      string        `toml:"session_token"`
	WatchFolder       string        `toml:"watch_folder"`
	HeartbeatInterval time.Duration `toml:"heartbeat_interval"`
	CACertPath        string        `toml:"ca_cert_path"`
}

func Load(path string) (Config, error) {
	var cfg Config
	if _, err := os.Stat(path); err != nil {
		return cfg, err
	}

	if _, err := toml.DecodeFile(path, &cfg); err != nil {
		return cfg, err
	}

	cfg.applyDefaults()
	if err := cfg.Validate(); err != nil {
		return cfg, err
	}

	return cfg, nil
}

func (c Config) Save(path string) error {
	file, err := os.Create(path)
	if err != nil {
		return err
	}
	defer file.Close()

	encoder := toml.NewEncoder(file)
	return encoder.Encode(c)
}

func (c *Config) applyDefaults() {
	if c.HeartbeatInterval == 0 {
		c.HeartbeatInterval = DefaultHeartbeatInterval
	}
}

func (c Config) Validate() error {
	if c.BackendURL == "" {
		return errors.New("backend_url is required")
	}
	if c.WatchFolder == "" {
		return errors.New("watch_folder is required")
	}
	return nil
}
