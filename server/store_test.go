package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestEveryConnectionUsesSQLiteSettings(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "store?#.sqlite"))
	s.db.SetMaxOpenConns(4)
	s.db.SetMaxIdleConns(4)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	for i := 0; i < 4; i++ {
		conn, err := s.db.Conn(ctx)
		if err != nil {
			t.Fatal(err)
		}
		defer conn.Close()
		for pragma, want := range map[string]int{"foreign_keys": 1, "busy_timeout": 5000, "synchronous": 2} {
			var got int
			if err := conn.QueryRowContext(ctx, "PRAGMA "+pragma).Scan(&got); err != nil {
				t.Fatal(err)
			}
			if got != want {
				t.Fatalf("connection %d: %s=%d, want %d", i, pragma, got, want)
			}
		}
		var mode string
		if err := conn.QueryRowContext(ctx, "PRAGMA journal_mode").Scan(&mode); err != nil {
			t.Fatal(err)
		}
		if mode != "wal" {
			t.Fatalf("connection %d: WAL is disabled", i)
		}
	}
}

func TestSQLiteFilesArePrivateAfterOpen(t *testing.T) {
	path := filepath.Join(t.TempDir(), "store.sqlite")
	first := openTest(t, path)
	for _, name := range []string{path, path + "-wal", path + "-shm"} {
		info, err := os.Stat(name)
		if err != nil {
			t.Fatal(err)
		}
		if info.Mode().Perm() != 0600 {
			t.Fatalf("new SQLite file has mode %o", info.Mode().Perm())
		}
		// Simulate an existing store whose permissions need repair.
		if err := os.Chmod(name, 0644); err != nil {
			t.Fatal(err)
		}
	}
	second := openTest(t, path)
	defer first.Close()
	defer second.Close()
	for _, name := range []string{path, path + "-wal", path + "-shm"} {
		info, err := os.Stat(name)
		if err != nil {
			t.Fatal(err)
		}
		if info.Mode().Perm() != 0600 {
			t.Fatalf("reopened SQLite file has mode %o", info.Mode().Perm())
		}
	}
}
