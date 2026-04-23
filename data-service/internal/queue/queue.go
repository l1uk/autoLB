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

	"autologbook/data-service/internal/client"

	_ "modernc.org/sqlite"
)

const (
	DefaultDBPath  = "./autologbook-queue.db"
	baseBackoff    = 500 * time.Millisecond
	maxBackoff     = 30 * time.Second
	defaultMaxTry  = 5
	statusPending  = "pending"
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

type QueueItem = Item

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
		statusPending,
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

	file, err := os.Open(item.LocalPath)
	if err != nil {
		return true, q.markRetryableFailure(ctx, item.ID, item.Attempts, err)
	}
	defer file.Close()

	uploadErr := q.uploader.Upload(ctx, item.ContextID, item.Filename, file)
	if uploadErr != nil {
		if errors.Is(uploadErr, client.ErrPermanentFailure) {
			if err := q.MarkFailed(ctx, item.ID, uploadErr.Error()); err != nil {
				return true, err
			}
			return true, uploadErr
		}
		return true, q.markRetryableFailure(ctx, item.ID, item.Attempts, uploadErr)
	}

	_, err = q.db.ExecContext(ctx, `DELETE FROM uploads WHERE id = ?`, item.ID)
	return true, err
}

func (q *Queue) initSchema() error {
	_, err := q.db.Exec(`
		CREATE TABLE IF NOT EXISTS uploads (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			context_id TEXT NOT NULL,
			local_path TEXT NOT NULL,
			filename TEXT NOT NULL,
			status TEXT NOT NULL DEFAULT 'pending',
			attempts INTEGER NOT NULL DEFAULT 0,
			last_attempt TEXT,
			error TEXT NOT NULL DEFAULT ''
		)
	`)
	if err != nil {
		return err
	}

	statusExists, err := q.columnExists("uploads", "status")
	if err != nil {
		return err
	}
	if !statusExists {
		if _, err := q.db.Exec(`ALTER TABLE uploads ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'`); err != nil {
			return err
		}
	}

	_, err = q.db.Exec(`
		UPDATE uploads
		SET status = 'pending'
		WHERE status IS NULL OR status NOT IN ('pending', 'failed')
	`)
	return err
}

func (q *Queue) nextEligible(ctx context.Context) (Item, error) {
	rows, err := q.db.QueryContext(
		ctx,
		`SELECT id, context_id, local_path, filename, status, attempts, last_attempt, error
		 FROM uploads
		 WHERE status = ?
		 ORDER BY id ASC`,
		statusPending,
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

func (q *Queue) markRetryableFailure(ctx context.Context, id int64, previousAttempts int, uploadErr error) error {
	now := q.now().UTC().Format(time.RFC3339Nano)
	attempts := previousAttempts + 1
	_, err := q.db.ExecContext(
		ctx,
		`UPDATE uploads SET attempts = ?, last_attempt = ?, status = ?, error = ? WHERE id = ?`,
		attempts,
		now,
		statusPending,
		uploadErr.Error(),
		id,
	)
	if err != nil {
		return fmt.Errorf("update failed upload: %w", err)
	}
	if attempts >= q.maxAttempts {
		if err := q.MarkFailed(ctx, id, uploadErr.Error()); err != nil {
			return err
		}
	}
	return uploadErr
}

func (q *Queue) MarkFailed(ctx context.Context, id int64, reason string) error {
	_, err := q.db.ExecContext(
		ctx,
		`UPDATE uploads SET status = ?, error = ?, last_attempt = ? WHERE id = ?`,
		statusFailed,
		reason,
		q.now().UTC().Format(time.RFC3339Nano),
		id,
	)
	return err
}

func (q *Queue) ListFailed(ctx context.Context) ([]QueueItem, error) {
	rows, err := q.db.QueryContext(
		ctx,
		`SELECT id, context_id, local_path, filename, status, attempts, last_attempt, error
		 FROM uploads
		 WHERE status = ?
		 ORDER BY id`,
		statusFailed,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	failed := make([]QueueItem, 0)
	for rows.Next() {
		var item QueueItem
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
		failed = append(failed, item)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}
	return failed, nil
}

func (q *Queue) columnExists(tableName, columnName string) (bool, error) {
	rows, err := q.db.Query(fmt.Sprintf(`PRAGMA table_info(%s)`, tableName))
	if err != nil {
		return false, err
	}
	defer rows.Close()

	for rows.Next() {
		var (
			cid        int
			name       string
			colType    string
			notNull    int
			defaultVal sql.NullString
			pk         int
		)
		if err := rows.Scan(&cid, &name, &colType, &notNull, &defaultVal, &pk); err != nil {
			return false, err
		}
		if name == columnName {
			return true, nil
		}
	}

	if err := rows.Err(); err != nil {
		return false, err
	}
	return false, nil
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
