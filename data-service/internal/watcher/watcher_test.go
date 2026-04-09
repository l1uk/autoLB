package watcher

import (
	"context"
	"io"
	"log"
	"testing"

	"autologbook/data-service/internal/client"
	"autologbook/data-service/internal/queue"
	"autologbook/data-service/internal/testutil"
)

type fakeNotifier struct {
	decision  client.Decision
	contextID string
	err       error
}

func (f *fakeNotifier) FileNotify(ctx context.Context, relativePath, filename string, fileSize int64) (client.Decision, string, error) {
	return f.decision, f.contextID, f.err
}

type fakeQueue struct {
	items []queue.Item
}

func (f *fakeQueue) Enqueue(ctx context.Context, item queue.Item) error {
	f.items = append(f.items, item)
	return nil
}

func TestHandleCreateAcceptsAndEnqueues(t *testing.T) {
	root := t.TempDir()
	fullPath := testutil.WriteTempFile(t, root, "nested/file.txt", []byte("payload"))
	notifier := &fakeNotifier{decision: client.DecisionAccept, contextID: "ctx-1"}
	enqueuer := &fakeQueue{}

	w, err := New(root, notifier, enqueuer, log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatalf("new watcher: %v", err)
	}
	defer w.Close()

	if err := w.handleCreate(context.Background(), fullPath, int64(len("payload"))); err != nil {
		t.Fatalf("handle create: %v", err)
	}
	if len(enqueuer.items) != 1 {
		t.Fatalf("expected one queued item, got %d", len(enqueuer.items))
	}
	if enqueuer.items[0].ContextID != "ctx-1" {
		t.Fatalf("unexpected context id: %q", enqueuer.items[0].ContextID)
	}
}

func TestHandleCreateIgnoresDiscardedFiles(t *testing.T) {
	root := t.TempDir()
	fullPath := testutil.WriteTempFile(t, root, "file.txt", []byte("payload"))
	notifier := &fakeNotifier{decision: client.DecisionIgnore}
	enqueuer := &fakeQueue{}

	w, err := New(root, notifier, enqueuer, log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatalf("new watcher: %v", err)
	}
	defer w.Close()

	if err := w.handleCreate(context.Background(), fullPath, int64(len("payload"))); err != nil {
		t.Fatalf("handle create: %v", err)
	}
	if len(enqueuer.items) != 0 {
		t.Fatalf("expected no queued items")
	}
}

func TestAddRecursiveAddsNestedDirectories(t *testing.T) {
	root := t.TempDir()
	_ = testutil.WriteTempFile(t, root, "nested/deeper/file.txt", []byte("payload"))
	w, err := New(root, &fakeNotifier{}, &fakeQueue{}, log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatalf("new watcher: %v", err)
	}
	defer w.Close()

	if err := w.addRecursive(root); err != nil {
		t.Fatalf("add recursive: %v", err)
	}
}
