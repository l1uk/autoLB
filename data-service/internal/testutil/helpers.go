package testutil

import (
	"os"
	"path/filepath"
	"testing"
)

func WriteTempFile(t *testing.T, dir, name string, data []byte) string {
	t.Helper()

	fullPath := filepath.Join(dir, name)
	if err := os.MkdirAll(filepath.Dir(fullPath), 0o755); err != nil {
		t.Fatalf("mkdir temp file dir: %v", err)
	}
	if err := os.WriteFile(fullPath, data, 0o644); err != nil {
		t.Fatalf("write temp file: %v", err)
	}
	return fullPath
}
