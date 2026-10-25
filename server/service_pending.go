package main

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"net/http"
	"sync"
)

type Server struct {
	db          *sql.DB
	dummyHash   []byte
	testMode    bool
	historyID   string
	historyPath string
	highWater   int64
	writeMu     sync.Mutex
}

func opaque() (string, error) {
	var raw [32]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return hex.EncodeToString(raw[:]), nil
}
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	http.Error(w, "authentication unavailable", 401)
}
