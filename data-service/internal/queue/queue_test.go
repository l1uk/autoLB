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

func TestMarkFailed(t *testing.T) {
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

	// Get the enqueued item's ID
	row := q.db.QueryRow(`SELECT id FROM uploads LIMIT 1`)
	var itemID int64
	if err := row.Scan(&itemID); err != nil {
		t.Fatalf("scan item id: %v", err)
	}

	// Mark it as failed with a reason
	reason := "manual admin intervention"
	if err := q.MarkFailed(context.Background(), itemID, reason); err != nil {
		t.Fatalf("mark failed: %v", err)
	}

	// Verify status and error are updated
	row = q.db.QueryRow(`SELECT status, error FROM uploads WHERE id = ?`, itemID)
	var status, errorMsg string
	if err := row.Scan(&status, &errorMsg); err != nil {
		t.Fatalf("scan marked item: %v", err)
	}
	if status != statusFailed {
		t.Fatalf("expected status=%s, got %s", statusFailed, status)
	}
	if errorMsg != reason {
		t.Fatalf("expected error=%s, got %s", reason, errorMsg)
	}
}

func TestListFailed(t *testing.T) {
	uploader := &fakeUploader{}
	q, err := Open(":memory:", uploader)
	if err != nil {
		t.Fatalf("open queue: %v", err)
	}
	defer q.Close()

	dir := t.TempDir()

	// Enqueue 3 items
	for i := 1; i <= 3; i++ {
		filePath := testutil.WriteTempFile(t, dir, fmt.Sprintf("file%d.txt", i), []byte("payload"))
		if err := q.Enqueue(context.Background(), Item{
			ContextID: fmt.Sprintf("ctx-%d", i),
			LocalPath: filePath,
			Filename:  fmt.Sprintf("file%d.txt", i),
		}); err != nil {
			t.Fatalf("enqueue: %v", err)
		}
	}

	// Mark items 1 and 3 as failed
	row1 := q.db.QueryRow(`SELECT id FROM uploads WHERE context_id = 'ctx-1'`)
	var id1 int64
	row1.Scan(&id1)

	row3 := q.db.QueryRow(`SELECT id FROM uploads WHERE context_id = 'ctx-3'`)
	var id3 int64
	row3.Scan(&id3)

	if err := q.MarkFailed(context.Background(), id1, "reason 1"); err != nil {
		t.Fatalf("mark failed 1: %v", err)
	}
	if err := q.MarkFailed(context.Background(), id3, "reason 3"); err != nil {
		t.Fatalf("mark failed 3: %v", err)
	}

	// List failed items
	failed, err := q.ListFailed(context.Background())
	if err != nil {
		t.Fatalf("list failed: %v", err)
	}

	if len(failed) != 2 {
		t.Fatalf("expected 2 failed items, got %d", len(failed))
	}
	if failed[0].ContextID != "ctx-1" || failed[0].Error != "reason 1" {
		t.Fatalf("unexpected first failed item: %v", failed[0])
	}
	if failed[1].ContextID != "ctx-3" || failed[1].Error != "reason 3" {
		t.Fatalf("unexpected second failed item: %v", failed[1])
	}
}

func TestFailedItemsExcludedFromReplay(t *testing.T) {
	uploader := &fakeUploader{err: errors.New("upload failed")}
	q, err := Open(":memory:", uploader)
	if err != nil {
		t.Fatalf("open queue: %v", err)
	}
	defer q.Close()

	dir := t.TempDir()

	// Enqueue 2 items
	filePath1 := testutil.WriteTempFile(t, dir, "file1.txt", []byte("payload1"))
	filePath2 := testutil.WriteTempFile(t, dir, "file2.txt", []byte("payload2"))

	if err := q.Enqueue(context.Background(), Item{
		ContextID: "ctx-1",
		LocalPath: filePath1,
		Filename:  "file1.txt",
	}); err != nil {
		t.Fatalf("enqueue 1: %v", err)
	}
	if err := q.Enqueue(context.Background(), Item{
		ContextID: "ctx-2",
		LocalPath: filePath2,
		Filename:  "file2.txt",
	}); err != nil {
		t.Fatalf("enqueue 2: %v", err)
	}

	// Fetch the first item's ID
	row := q.db.QueryRow(`SELECT id FROM uploads WHERE context_id = 'ctx-1'`)
	var id1 int64
	row.Scan(&id1)

	// Mark first item as failed
	if err := q.MarkFailed(context.Background(), id1, "permanently failed"); err != nil {
		t.Fatalf("mark failed: %v", err)
	}

	// ProcessNext should skip the failed item and process the second one
	processed, err := q.ProcessNext(context.Background())
	if err == nil {
		t.Fatalf("expected error from upload failure")
	}
	if !processed {
		t.Fatalf("expected ProcessNext to process and attempt upload")
	}

	// Verify that we tried to upload file2.txt
	if uploader.calls != 1 {
		t.Fatalf("expected 1 uploader call, got %d", uploader.calls)
	}

	// Verify item 1 is still failed
	row = q.db.QueryRow(`SELECT status FROM uploads WHERE context_id = 'ctx-1'`)
	var status string
	row.Scan(&status)
	if status != statusFailed {
		t.Fatalf("expected item 1 to remain failed, got %s", status)
	}
}
