package main

import (
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"golang.org/x/crypto/bcrypt"
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

func reply(w http.ResponseWriter, code int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	if value != nil {
		_ = json.NewEncoder(w).Encode(value)
	}
}
func problem(w http.ResponseWriter, code int) {
	reply(w, code, map[string]string{"error": http.StatusText(code)})
}
func decode(w http.ResponseWriter, r *http.Request, value any) bool {
	d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	d.DisallowUnknownFields()
	if err := d.Decode(value); err != nil {
		problem(w, 400)
		return false
	}
	if err := d.Decode(new(any)); err != io.EOF {
		problem(w, 400)
		return false
	}
	return true
}
func opaque() (string, error) {
	var raw [32]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return hex.EncodeToString(raw[:]), nil
}
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	if !s.testMode {
		problem(w, http.StatusUnauthorized)
		return
	}
	if r.URL.Path == "/api/sign-in" && r.Method == "POST" {
		s.signIn(w, r)
		return
	}
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") || len(auth) != len("Bearer ")+64 {
		problem(w, 401)
		return
	}
	hash := sha256.Sum256([]byte(strings.TrimPrefix(auth, "Bearer ")))
	var owner, session string
	err := s.db.QueryRowContext(r.Context(), "SELECT owner_id,session_id FROM sessions WHERE token_hash=? AND test_mode=1 AND revoked_at IS NULL AND expires_at>?", hash[:], time.Now().Unix()).Scan(&owner, &session)
	if errors.Is(err, sql.ErrNoRows) || (err == nil && !syntheticActor.MatchString(owner)) {
		problem(w, 401)
		return
	}
	if err != nil {
		problem(w, 500)
		return
	}
	if r.URL.Path == "/api/sign-out" && r.Method == "POST" {
		if _, err = s.db.ExecContext(r.Context(), "UPDATE sessions SET revoked_at=? WHERE session_id=?", time.Now().Unix(), session); err != nil {
			problem(w, 500)
			return
		}
		w.WriteHeader(204)
		return
	}
	s.data(w, r, owner)
}
func (s *Server) signIn(w http.ResponseWriter, r *http.Request) {
	var input struct {
		ActorID  string `json:"actor_id"`
		Password string `json:"password"`
		DeviceID string `json:"device_id"`
	}
	if !decode(w, r, &input) {
		return
	}
	if !syntheticActor.MatchString(input.ActorID) {
		problem(w, http.StatusUnauthorized)
		return
	}
	if input.DeviceID == "" || len(input.DeviceID) > 128 || len(input.Password) > 72 {
		problem(w, 400)
		return
	}
	var hash []byte
	err := s.db.QueryRowContext(r.Context(), "SELECT password_hash FROM owners WHERE owner_id=?", input.ActorID).Scan(&hash)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		problem(w, 500)
		return
	}
	exists := err == nil
	if !exists {
		hash = s.dummyHash
	}
	valid := bcrypt.CompareHashAndPassword(hash, []byte(input.Password)) == nil
	if !exists || !valid {
		problem(w, 401)
		return
	}
	token, err := opaque()
	if err != nil {
		problem(w, 500)
		return
	}
	session, err := opaque()
	if err != nil {
		problem(w, 500)
		return
	}
	digest := sha256.Sum256([]byte(token))
	now := time.Now().Unix()
	expires := now + 30*24*60*60
	_, err = s.db.ExecContext(r.Context(), "INSERT INTO sessions(session_id,owner_id,token_hash,device_id,created_at,expires_at,test_mode) VALUES (?,?,?,?,?,?,1)", session, input.ActorID, digest[:], input.DeviceID, now, expires)
	if err != nil {
		problem(w, 500)
		return
	}
	reply(w, 200, map[string]any{"token": token, "owner_id": input.ActorID, "expires_at": expires, "history_id": s.historyID})
}
