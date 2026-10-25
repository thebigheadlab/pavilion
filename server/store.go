package main

import (
	"database/sql"
	"embed"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"regexp"

	"golang.org/x/crypto/bcrypt"
	_ "modernc.org/sqlite"
)

//go:embed migrations/*.sql
var migrations embed.FS

const schemaVersion = 4

func Open(path string, testMode bool) (*Server, error) {
	if path == "" {
		return nil, errors.New("database path is required")
	}
	// New database files contain session and password hashes. Restrict access at creation.
	f, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	if err = f.Close(); err != nil {
		return nil, err
	}
	if err = os.Chmod(path, 0600); err != nil {
		return nil, err
	}
	absolute, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	source := url.URL{Scheme: "file", Path: absolute}
	settings := url.Values{}
	for _, pragma := range []string{"foreign_keys(ON)", "busy_timeout(5000)", "journal_mode(WAL)", "synchronous(FULL)"} {
		settings.Add("_pragma", pragma)
	}
	source.RawQuery = settings.Encode()
	db, err := sql.Open("sqlite", source.String())
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	fail := func(err error) (*Server, error) { db.Close(); return nil, err }
	if err = migrate(db); err != nil {
		return fail(err)
	}
	for _, name := range []string{absolute, absolute + "-wal", absolute + "-shm"} {
		if err = os.Chmod(name, 0600); err != nil && !errors.Is(err, os.ErrNotExist) {
			return fail(err)
		}
	}
	historyPath := absolute + ".history"
	state, err := initializeHistory(db, historyPath)
	if err != nil {
		return fail(err)
	}
	dummy, err := bcrypt.GenerateFromPassword([]byte("synthetic-unused"), bcrypt.DefaultCost)
	if err != nil {
		return fail(err)
	}
	return &Server{db: db, dummyHash: dummy, testMode: testMode, historyPath: historyPath, historyID: state.HistoryID, highWater: state.HighWater}, nil
}
func migrate(db *sql.DB) error {
	if _, err := db.Exec("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"); err != nil {
		return err
	}
	var version int
	if err := db.QueryRow("SELECT COALESCE(MAX(version),0) FROM schema_version").Scan(&version); err != nil {
		return err
	}
	if version > schemaVersion {
		return errors.New("database schema is newer than this server")
	}
	names := []string{"migrations/001_initial.sql", "migrations/002_indexes.sql", "migrations/003_test_sessions.sql", "migrations/004_history.sql"}
	for version < schemaVersion {
		content, err := migrations.ReadFile(names[version])
		if err != nil {
			return err
		}
		tx, err := db.Begin()
		if err != nil {
			return err
		}
		if _, err = tx.Exec(string(content)); err == nil {
			_, err = tx.Exec("INSERT INTO schema_version(version) VALUES (?)", version+1)
		}
		if err != nil {
			tx.Rollback()
			return fmt.Errorf("migration %d failed: %w", version+1, err)
		}
		if err = tx.Commit(); err != nil {
			return err
		}
		version++
	}
	return nil
}

var syntheticActor = regexp.MustCompile(`^actor-[0-9]{3}$`)

// SeedTestOwner is used only by tests and the explicit test-mode startup path.
func (s *Server) SeedTestOwner(actor, password string) error {
	if !s.testMode || !syntheticActor.MatchString(actor) || len(password) < 12 || len(password) > 72 {
		return errors.New("invalid synthetic owner or test password length")
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return err
	}
	_, err = s.db.Exec("INSERT INTO owners(owner_id,password_hash) VALUES (?,?) ON CONFLICT(owner_id) DO UPDATE SET password_hash=excluded.password_hash", actor, hash)
	return err
}
func (s *Server) Close() error { return s.db.Close() }
