package queue

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"time"

	_ "modernc.org/sqlite"
)

const (
	DefaultDBPath  = "./autologbook-queue.db"
	baseBackoff    = 500 * time.Millisecond
	maxBackoff     = 30 * time.Second
	defaultMaxTry  = 5
	statusQueued   = "queued"
	statusRetrying = "retrying"
	statusFailed   = "failed"
)

type Uploader interface {
	Upload(ctx context.Context, contextID, filename string, reader io.Reader) error
}

type Item struct {
	ID          int64
	ContextID   string
	LocalPath   string
	Filename    string
	Status      string
	Attempts    int
	LastAttempt *time.Time
	Error       string
}

type Queue struct {
	db          *sql.DB
	uploader    Uploader
	now         func() time.Time
	maxAttempts int
}

func Open(path string, uploader Uploader) (*Queue, error) {
	if path == "" {
		path = DefaultDBPath
	}

	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}

	queue := &Queue{
		db:          db,
		uploader:    uploader,
		now:         time.Now,
		maxAttempts: defaultMaxTry,
	}

	if err := queue.initSchema(); err != nil {
		_ = db.Close()
		return nil, err
	}
	return queue, nil
}

func (q *Queue) Close() error {
	return q.db.Close()
}

func (q *Queue) Enqueue(ctx context.Context, item Item) error {
	_, err := q.db.ExecContext(
		ctx,
		`INSERT INTO uploads (context_id, local_path, filename, status, attempts, last_attempt, error)
		 VALUES (?, ?, ?, ?, 0, NULL, '')`,
		item.ContextID,
		item.LocalPath,
		item.Filename,
		statusQueued,
	)
	return err
}

func (q *Queue) ProcessNext(ctx context.Context) (bool, error) {
	item, err := q.nextEligible(ctx)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return false, nil
		}
		return false, err
	}

	now := q.now().UTC()
	newAttempts := item.Attempts + 1
	_, err = q.db.ExecContext(
		ctx,
		`UPDATE uploads SET attempts = ?, last_attempt = ?, status = ?, error = '' WHERE id = ?`,
		newAttempts,
		now.Format(time.RFC3339Nano),
		statusRetrying,
		item.ID,
	)
	if err != nil {
		return true, err
	}

	file, err := os.Open(item.LocalPath)
	if err != nil {
		return true, q.markFailure(ctx, item.ID, newAttempts, err)
	}
	defer file.Close()

	if err := q.uploader.Upload(ctx, item.ContextID, item.Filename, file); err != nil {
		return true, q.markFailure(ctx, item.ID, newAttempts, err)
	}

	_, err = q.db.ExecContext(ctx, `DELETE FROM uploads WHERE id = ?`, item.ID)
	return true, err
}

// MarkFailed marks an item as permanently failed with the given reason.
// This prevents it from being replayed in the FIFO queue.
func (q *Queue) MarkFailed(ctx context.Context, id int64, reason string) error {
	_, err := q.db.ExecContext(
		ctx,
		`UPDATE uploads SET status = ?, error = ? WHERE id = ?`,
		statusFailed,
		reason,
		id,
	)
	return err
}

// ListFailed returns all permanently failed items.
// Used for observability and future admin tooling.
func (q *Queue) ListFailed(ctx context.Context) ([]Item, error) {
	rows, err := q.db.QueryContext(
		ctx,
		`SELECT id, context_id, local_path, filename, status, attempts, last_attempt, error
		 FROM uploads
		 WHERE status = ?
		 ORDER BY id ASC`,
		statusFailed,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var items []Item
	for rows.Next() {
		var item Item
		var lastAttempt sql.NullString
		if err := rows.Scan(
			&item.ID,
			&item.ContextID,
			&item.LocalPath,
			&item.Filename,
			&item.Status,
			&item.Attempts,
			&lastAttempt,
			&item.Error,
		); err != nil {
			return nil, err
		}

		if lastAttempt.Valid {
			parsed, err := time.Parse(time.RFC3339Nano, lastAttempt.String)
			if err != nil {
				return nil, err
			}
			item.LastAttempt = &parsed
		}

		items = append(items, item)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}
	return items, nil
}

func (q *Queue) initSchema() error {
	_, err := q.db.Exec(`
		CREATE TABLE IF NOT EXISTS uploads (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			context_id TEXT NOT NULL,
			local_path TEXT NOT NULL,
			filename TEXT NOT NULL,
			status TEXT NOT NULL,
			attempts INTEGER NOT NULL DEFAULT 0,
			last_attempt TEXT,
			error TEXT NOT NULL DEFAULT ''
		)
	`)
	return err
}

func (q *Queue) nextEligible(ctx context.Context) (Item, error) {
	rows, err := q.db.QueryContext(
		ctx,
		`SELECT id, context_id, local_path, filename, status, attempts, last_attempt, error
		 FROM uploads
		 WHERE status != ?
		 ORDER BY id ASC`,
		statusFailed,
	)
	if err != nil {
		return Item{}, err
	}
	defer rows.Close()

	now := q.now().UTC()
	for rows.Next() {
		var item Item
		var lastAttempt sql.NullString
		if err := rows.Scan(
			&item.ID,
			&item.ContextID,
			&item.LocalPath,
			&item.Filename,
			&item.Status,
			&item.Attempts,
			&lastAttempt,
			&item.Error,
		); err != nil {
			return Item{}, err
		}

		if lastAttempt.Valid {
			parsed, err := time.Parse(time.RFC3339Nano, lastAttempt.String)
			if err != nil {
				return Item{}, err
			}
			item.LastAttempt = &parsed
			if parsed.Add(backoffForAttempt(item.Attempts)).After(now) {
				continue
			}
		}

		return item, nil
	}

	if err := rows.Err(); err != nil {
		return Item{}, err
	}
	return Item{}, sql.ErrNoRows
}

func (q *Queue) markFailure(ctx context.Context, id int64, attempts int, uploadErr error) error {
	nextStatus := statusRetrying
	if attempts >= q.maxAttempts {
		nextStatus = statusFailed
	}

	_, err := q.db.ExecContext(
		ctx,
		`UPDATE uploads SET status = ?, error = ? WHERE id = ?`,
		nextStatus,
		uploadErr.Error(),
		id,
	)
	if err != nil {
		return fmt.Errorf("update failed upload: %w", err)
	}
	return uploadErr
}

func backoffForAttempt(attempts int) time.Duration {
	if attempts <= 0 {
		return 0
	}

	backoff := float64(baseBackoff) * math.Pow(2, float64(attempts-1))
	if time.Duration(backoff) > maxBackoff {
		return maxBackoff
	}
	return time.Duration(backoff)
}
