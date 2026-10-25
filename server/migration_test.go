package main

import (
	"crypto/sha256"
	"database/sql"
	"path/filepath"
	"strings"
	"testing"
)

func TestSQLiteSettingsAndFTSAvailable(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "store.sqlite"))
	var mode string
	if err := s.db.QueryRow("PRAGMA journal_mode").Scan(&mode); err != nil || mode != "wal" {
		t.Fatal("WAL unavailable")
	}
	for key, want := range map[string]int{"synchronous": 2, "foreign_keys": 1, "busy_timeout": 5000} {
		var got int
		if err := s.db.QueryRow("PRAGMA " + key).Scan(&got); err != nil || got != want {
			t.Fatalf("wrong SQLite setting %s", key)
		}
	}
	// This temporary table checks driver capability. The application creates no FTS table.
	if _, err := s.db.Exec("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(body)"); err != nil {
		t.Fatal(err)
	}
}

func TestFailedMigrationRollsBackPartialChanges(t *testing.T) {
	path := filepath.Join(t.TempDir(), "earlier.sqlite")
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	initial, err := migrations.ReadFile("migrations/001_initial.sql")
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(string(initial) + `; CREATE TABLE schema_version(version INTEGER PRIMARY KEY); INSERT INTO schema_version VALUES(1); INSERT INTO owners VALUES('actor-001',X'00'); CREATE INDEX sessions_expiry ON sessions(expires_at);`)
	if err != nil {
		t.Fatal(err)
	}
	if err = db.Close(); err != nil {
		t.Fatal(err)
	}
	failed, err := Open(path, true)
	if err == nil {
		failed.Close()
		t.Fatal("migration accepted a conflicting index")
	}
	if !strings.Contains(err.Error(), "migration 2 failed") {
		t.Fatal("unexpected migration failure")
	}
	db, err = sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var version, partial, owners int
	if err = db.QueryRow("SELECT MAX(version) FROM schema_version").Scan(&version); err != nil {
		t.Fatal(err)
	}
	if err = db.QueryRow("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('events_owner_seq','messages_channel_seq')").Scan(&partial); err != nil {
		t.Fatal(err)
	}
	if err = db.QueryRow("SELECT COUNT(*) FROM owners WHERE owner_id='actor-001'").Scan(&owners); err != nil {
		t.Fatal(err)
	}
	if version != 1 || partial != 0 || owners != 1 {
		t.Fatal("failed migration left partial changes or damaged existing data")
	}
	if _, err = db.Exec("DROP INDEX sessions_expiry"); err != nil {
		t.Fatal(err)
	}
	if err = db.Close(); err != nil {
		t.Fatal(err)
	}
	recovered := openTest(t, path)
	if err = recovered.db.QueryRow("SELECT MAX(version) FROM schema_version").Scan(&version); err != nil {
		t.Fatal(err)
	}
	if version != 4 {
		t.Fatal("startup did not recover after removing the conflict")
	}
}

func TestLegacySessionsRequireFreshTestSignIn(t *testing.T) {
	path := filepath.Join(t.TempDir(), "legacy.sqlite")
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"migrations/001_initial.sql", "migrations/002_indexes.sql"} {
		migration, err := migrations.ReadFile(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err = db.Exec(string(migration)); err != nil {
			t.Fatal(err)
		}
	}
	if _, err = db.Exec("CREATE TABLE schema_version(version INTEGER PRIMARY KEY); INSERT INTO schema_version VALUES(1),(2); INSERT INTO owners VALUES('actor-001',X'00')"); err != nil {
		t.Fatal(err)
	}
	token := strings.Repeat("a", 64)
	digest := sha256.Sum256([]byte(token))
	if _, err = db.Exec("INSERT INTO sessions(session_id,owner_id,token_hash,device_id,created_at,expires_at) VALUES('session-001','actor-001',?,'device-001',0,9999999999)", digest[:]); err != nil {
		t.Fatal(err)
	}
	if err = db.Close(); err != nil {
		t.Fatal(err)
	}
	s := openTest(t, path)
	expect(t, request(t, s, "GET", "/api/channels", token, nil), 401)
	seed(t, s, "actor-001")
	fresh := signIn(t, s, "actor-001")
	expect(t, request(t, s, "GET", "/api/channels", fresh, nil), 200)
}
