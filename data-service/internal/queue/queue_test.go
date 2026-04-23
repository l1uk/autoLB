package queue

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"io"
	"strings"
	"testing"
	"time"

	"autologbook/data-service/internal/client"
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

func TestMarkFailedExcludesFromDequeue(t *testing.T) {
	uploader := &fakeUploader{}
	q, err := Open(":memory:", uploader)
	if err != nil {
		t.Fatalf("open queue: %v", err)
	}
	defer q.Close()

	dir := t.TempDir()
	filePath := testutil.WriteTempFile(t, dir, "failed.txt", []byte("payload"))
	if err := q.Enqueue(context.Background(), Item{
		ContextID: "ctx-failed",
		LocalPath: filePath,
		Filename:  "failed.txt",
	}); err != nil {
		t.Fatalf("enqueue: %v", err)
	}

	var id int64
	if err := q.db.QueryRow(`SELECT id FROM uploads LIMIT 1`).Scan(&id); err != nil {
		t.Fatalf("read id: %v", err)
	}
	if err := q.MarkFailed(context.Background(), id, "manual permanent failure"); err != nil {
		t.Fatalf("mark failed: %v", err)
	}

	processed, err := q.ProcessNext(context.Background())
	if err != nil {
		t.Fatalf("process next: %v", err)
	}
	if processed {
		t.Fatalf("expected failed item to be excluded from dequeue")
	}
	if uploader.calls != 0 {
		t.Fatalf("unexpected upload attempts: %d", uploader.calls)
	}
}

func TestListFailedReturnsFailedItems(t *testing.T) {
	uploader := &fakeUploader{}
	q, err := Open(":memory:", uploader)
	if err != nil {
		t.Fatalf("open queue: %v", err)
	}
	defer q.Close()

	dir := t.TempDir()
	firstPath := testutil.WriteTempFile(t, dir, "first.txt", []byte("first"))
	secondPath := testutil.WriteTempFile(t, dir, "second.txt", []byte("second"))

	if err := q.Enqueue(context.Background(), Item{ContextID: "ctx-1", LocalPath: firstPath, Filename: "first.txt"}); err != nil {
		t.Fatalf("enqueue first: %v", err)
	}
	if err := q.Enqueue(context.Background(), Item{ContextID: "ctx-2", LocalPath: secondPath, Filename: "second.txt"}); err != nil {
		t.Fatalf("enqueue second: %v", err)
	}

	rows, err := q.db.Query(`SELECT id FROM uploads ORDER BY id ASC`)
	if err != nil {
		t.Fatalf("query ids: %v", err)
	}
	defer rows.Close()

	var ids []int64
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			t.Fatalf("scan id: %v", err)
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("iterate ids: %v", err)
	}
	if len(ids) != 2 {
		t.Fatalf("expected 2 ids, got %d", len(ids))
	}

	if err := q.MarkFailed(context.Background(), ids[0], "first failed"); err != nil {
		t.Fatalf("mark first failed: %v", err)
	}
	if err := q.MarkFailed(context.Background(), ids[1], "second failed"); err != nil {
		t.Fatalf("mark second failed: %v", err)
	}

	failedItems, err := q.ListFailed(context.Background())
	if err != nil {
		t.Fatalf("list failed: %v", err)
	}
	if len(failedItems) != 2 {
		t.Fatalf("expected 2 failed items, got %d", len(failedItems))
	}
	if failedItems[0].ID >= failedItems[1].ID {
		t.Fatalf("expected failed items ordered by id, got %d then %d", failedItems[0].ID, failedItems[1].ID)
	}
	if failedItems[0].Status != statusFailed || failedItems[1].Status != statusFailed {
		t.Fatalf("expected failed status, got %q and %q", failedItems[0].Status, failedItems[1].Status)
	}
}

func TestProcessNextPermanentFailureMarksFailedWithoutRetry(t *testing.T) {
	uploader := &fakeUploader{err: fmt.Errorf("%w: bad request", client.ErrPermanentFailure)}
	q, err := Open(":memory:", uploader)
	if err != nil {
		t.Fatalf("open queue: %v", err)
	}
	defer q.Close()

	dir := t.TempDir()
	filePath := testutil.WriteTempFile(t, dir, "file.txt", []byte("payload"))
	if err := q.Enqueue(context.Background(), Item{
		ContextID: "ctx-perm",
		LocalPath: filePath,
		Filename:  "file.txt",
	}); err != nil {
		t.Fatalf("enqueue: %v", err)
	}

	processed, err := q.ProcessNext(context.Background())
	if !processed {
		t.Fatalf("expected first process to attempt upload")
	}
	if err == nil || !errors.Is(err, client.ErrPermanentFailure) {
		t.Fatalf("expected permanent failure error, got %v", err)
	}

	var statusText string
	var attempts int
	if err := q.db.QueryRow(`SELECT status, attempts FROM uploads LIMIT 1`).Scan(&statusText, &attempts); err != nil {
		t.Fatalf("scan failed row: %v", err)
	}
	if statusText != statusFailed {
		t.Fatalf("expected status failed, got %s", statusText)
	}
	if attempts != 0 {
		t.Fatalf("expected attempts to remain 0 on permanent failure, got %d", attempts)
	}

	processed, err = q.ProcessNext(context.Background())
	if err != nil {
		t.Fatalf("process next after permanent failure: %v", err)
	}
	if processed {
		t.Fatalf("expected no pending items after permanent failure")
	}
	if uploader.calls != 1 {
		t.Fatalf("expected single upload call, got %d", uploader.calls)
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
