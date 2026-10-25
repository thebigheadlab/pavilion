package main

import "database/sql"

type historyState struct {
	HistoryID string
	HighWater int64
}

func initializeHistory(db *sql.DB, path string) (historyState, error) {
	var state historyState
	if err := db.QueryRow("SELECT value FROM meta WHERE key='history_id'").Scan(&state.HistoryID); err != nil {
		return state, err
	}
	err := db.QueryRow("SELECT COALESCE(MAX(seq),0) FROM events").Scan(&state.HighWater)
	return state, err
}
func (s *Server) commitEvent(tx *sql.Tx, seq int64) error { return tx.Commit() }
