package watcher

import (
	"context"
	"log"
	"os"
	"path/filepath"

	"autologbook/data-service/internal/client"
	"autologbook/data-service/internal/queue"
	"github.com/fsnotify/fsnotify"
)

type Notifier interface {
	FileNotify(ctx context.Context, relativePath, filename string, fileSize int64) (client.Decision, string, error)
}

type Enqueuer interface {
	Enqueue(ctx context.Context, item queue.Item) error
}

type Watcher struct {
	root     string
	notifier Notifier
	queue    Enqueuer
	logger   *log.Logger
	fs       *fsnotify.Watcher
}

func New(root string, notifier Notifier, queue Enqueuer, logger *log.Logger) (*Watcher, error) {
	fsWatcher, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, err
	}
	if logger == nil {
		logger = log.New(os.Stdout, "watcher: ", log.LstdFlags)
	}

	return &Watcher{
		root:     root,
		notifier: notifier,
		queue:    queue,
		logger:   logger,
		fs:       fsWatcher,
	}, nil
}

func (w *Watcher) Close() error {
	return w.fs.Close()
}

func (w *Watcher) Start(ctx context.Context) error {
	if err := w.addRecursive(w.root); err != nil {
		return err
	}

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case err := <-w.fs.Errors:
			if err != nil {
				return err
			}
		case event := <-w.fs.Events:
			if event.Op&fsnotify.Create == 0 {
				continue
			}

			info, err := os.Stat(event.Name)
			if err != nil {
				continue
			}

			if info.IsDir() {
				if err := w.addRecursive(event.Name); err != nil {
					return err
				}
				continue
			}

			if err := w.handleCreate(ctx, event.Name, info.Size()); err != nil {
				w.logger.Printf("create handling failed: %v", err)
			}
		}
	}
}

func (w *Watcher) addRecursive(root string) error {
	return filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !d.IsDir() {
			return nil
		}
		return w.fs.Add(path)
	})
}

func (w *Watcher) handleCreate(ctx context.Context, fullPath string, fileSize int64) error {
	relativeFile, err := filepath.Rel(w.root, fullPath)
	if err != nil {
		return err
	}

	filename := filepath.Base(relativeFile)
	relativePath := filepath.Dir(relativeFile)
	if relativePath == "." {
		relativePath = ""
	}

	decision, contextID, err := w.notifier.FileNotify(ctx, relativePath, filename, fileSize)
	if err != nil {
		return err
	}

	if decision == client.DecisionIgnore {
		w.logger.Printf("ignored file %s", fullPath)
		return nil
	}

	if err := w.queue.Enqueue(ctx, queue.Item{
		ContextID: contextID,
		LocalPath: fullPath,
		Filename:  filename,
	}); err != nil {
		return err
	}

	w.logger.Printf("enqueued file path=%s context_id=%s", fullPath, contextID)
	return nil
}
