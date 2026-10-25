package main

import (
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
)

type historyState struct {
	HistoryID string `json:"history_id"`
	HighWater int64  `json:"high_water"`
}

func initializeHistory(db *sql.DB, path string) (historyState, error) {
	var state historyState
	if err := removeHistoryTemps(path); err != nil {
		return state, err
	}
	if err := db.QueryRow("SELECT value FROM meta WHERE key='history_id'").Scan(&state.HistoryID); err != nil {
		return state, err
	}
	if decoded, err := hex.DecodeString(state.HistoryID); err != nil || len(decoded) != 32 {
		return state, errors.New("invalid database history ID")
	}
	if err := db.QueryRow("SELECT COALESCE(MAX(seq),0) FROM events").Scan(&state.HighWater); err != nil {
		return state, err
	}
	data, err := os.ReadFile(path)
	missing := errors.Is(err, os.ErrNotExist)
	if err != nil && !missing {
		return state, err
	}
	var previous struct {
		HistoryID string `json:"history_id"`
		HighWater *int64 `json:"high_water"`
	}
	if !missing {
		if err = json.Unmarshal(data, &previous); err != nil {
			return state, errors.New("invalid history state file")
		}
		decoded, err := hex.DecodeString(previous.HistoryID)
		if err != nil || len(decoded) != 32 || previous.HighWater == nil || *previous.HighWater < 0 {
			return state, errors.New("invalid history state file")
		}
	}
	if missing || previous.HistoryID != state.HistoryID || state.HighWater < *previous.HighWater {
		state.HistoryID, err = opaque()
		if err != nil {
			return state, err
		}
		if _, err = db.Exec("UPDATE meta SET value=? WHERE key='history_id'", state.HistoryID); err != nil {
			return state, err
		}
	}
	if err = saveHistoryState(path, state); err != nil {
		return state, err
	}
	return state, nil
}

func saveHistoryState(path string, state historyState) error {
	file, err := os.CreateTemp(filepath.Dir(path), ".history-*")
	if err != nil {
		return err
	}
	defer os.Remove(file.Name())
	defer file.Close()
	if err = file.Chmod(0600); err != nil {
		return err
	}
	if err = json.NewEncoder(file).Encode(state); err != nil {
		return err
	}
	if err = file.Sync(); err != nil {
		return err
	}
	if err = file.Close(); err != nil {
		return err
	}
	if err = os.Rename(file.Name(), path); err != nil {
		return err
	}
	directory, err := os.Open(filepath.Dir(path))
	if err != nil {
		return err
	}
	defer directory.Close()
	return directory.Sync()
}

// Sync the high-water mark before committing an event a client can observe.
// SQLite FULL synchronization improves durability when storage honors fsync;
// data loss can still occur after a power cut.
// See https://www.sqlite.org/pragma.html#pragma_synchronous.
// A failed commit can cause a conservative history rotation at the next startup.
func (s *Server) commitEvent(tx *sql.Tx, seq int64) error {
	if seq > s.highWater {
		if err := saveHistoryState(s.historyPath, historyState{HistoryID: s.historyID, HighWater: seq}); err != nil {
			return err
		}
		s.highWater = seq
	}
	return tx.Commit()
}

func removeHistoryTemps(statePath string) error {
	directory := filepath.Dir(statePath)
	entries, err := os.ReadDir(directory)
	if err != nil {
		return err
	}
	database := strings.TrimSuffix(filepath.Base(statePath), ".history")
	protected := map[string]bool{database: true, database + "-wal": true, database + "-shm": true, filepath.Base(statePath): true}
	for _, entry := range entries {
		if !strings.HasPrefix(entry.Name(), ".history-") || !entry.Type().IsRegular() || protected[entry.Name()] {
			continue
		}
		if err = os.Remove(filepath.Join(directory, entry.Name())); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
	}
	return nil
}
