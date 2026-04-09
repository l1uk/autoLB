package queue

import (
	"context"
	"database/sql"
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	"autologbook/data-service/internal/testutil"
)

type fakeUploader struct {
	err   error
	calls int
}

func (f *fakeUploader) Upload(ctx context.Context, contextID, filename string, reader io.Reader) error {
	f.calls++
	_, _ = io.ReadAll(reader)
	return f.err
}

func TestEnqueueAndProcessNext(t *testing.T) {
	uploader := &fakeUploader{}
	q, err := Open(":memory:", uploader)
	if err != nil {
		t.Fatalf("open queue: %v", err)
	}
	defer q.Close()

	dir := t.TempDir()
	filePath := testutil.WriteTempFile(t, dir, "file.txt", []byte("payload"))
	if err := q.Enqueue(context.Background(), Item{
		ContextID: "ctx-1",
		LocalPath: filePath,
		Filename:  "file.txt",
	}); err != nil {
		t.Fatalf("enqueue: %v", err)
	}

	processed, err := q.ProcessNext(context.Background())
	if err != nil {
		t.Fatalf("process next: %v", err)
	}
	if !processed || uploader.calls != 1 {
		t.Fatalf("unexpected process result: processed=%v calls=%d", processed, uploader.calls)
	}
}

func TestProcessNextRetriesAndMarksFailed(t *testing.T) {
	uploader := &fakeUploader{err: errors.New("upload failed")}
	q, err := Open(":memory:", uploader)
	if err != nil {
		t.Fatalf("open queue: %v", err)
	}
	defer q.Close()

	dir := t.TempDir()
	filePath := testutil.WriteTempFile(t, dir, "file.txt", []byte("payload"))
	if err := q.Enqueue(context.Background(), Item{
		ContextID: "ctx-1",
		LocalPath: filePath,
		Filename:  "file.txt",
	}); err != nil {
		t.Fatalf("enqueue: %v", err)
	}

	fixedNow := time.Now().UTC()
	q.now = func() time.Time { return fixedNow }
	for i := 0; i < defaultMaxTry; i++ {
		_, _ = q.ProcessNext(context.Background())
		fixedNow = fixedNow.Add(maxBackoff)
	}

	row := q.db.QueryRow(`SELECT status, error FROM uploads LIMIT 1`)
	var statusText string
	var errText string
	if err := row.Scan(&statusText, &errText); err != nil {
		t.Fatalf("scan failed row: %v", err)
	}
	if statusText != statusFailed || !strings.Contains(errText, "upload failed") {
		t.Fatalf("unexpected failed row: %s %s", statusText, errText)
	}
}

func TestProcessNextHonorsBackoff(t *testing.T) {
	uploader := &fakeUploader{err: errors.New("upload failed")}
	q, err := Open(":memory:", uploader)
	if err != nil {
		t.Fatalf("open queue: %v", err)
	}
	defer q.Close()

	dir := t.TempDir()
	filePath := testutil.WriteTempFile(t, dir, "file.txt", []byte("payload"))
	if err := q.Enqueue(context.Background(), Item{
		ContextID: "ctx-1",
		LocalPath: filePath,
		Filename:  "file.txt",
	}); err != nil {
		t.Fatalf("enqueue: %v", err)
	}

	fixedNow := time.Now().UTC()
	q.now = func() time.Time { return fixedNow }
	processed, _ := q.ProcessNext(context.Background())
	if !processed {
		t.Fatalf("expected first process to run")
	}

	processed, err = q.ProcessNext(context.Background())
	if err != nil {
		t.Fatalf("process next: %v", err)
	}
	if processed {
		t.Fatalf("expected backoff to defer processing")
	}
}

func TestOpenInitializesSchema(t *testing.T) {
	q, err := Open(":memory:", &fakeUploader{})
	if err != nil {
		t.Fatalf("open queue: %v", err)
	}
	defer q.Close()

	row := q.db.QueryRow(`SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='uploads'`)
	var count int
	if err := row.Scan(&count); err != nil && !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("scan schema count: %v", err)
	}
	if count != 1 {
		t.Fatalf("uploads table missing")
	}
}
