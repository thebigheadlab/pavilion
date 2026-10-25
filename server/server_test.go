package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"golang.org/x/crypto/bcrypt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
)

func request(t *testing.T, s http.Handler, method, path, token string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var b bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&b).Encode(body); err != nil {
			t.Fatal(err)
		}
	}
	r := httptest.NewRequest(method, path, &b)
	if token != "" {
		r.Header.Set("Authorization", "Bearer "+token)
	}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	return w
}

func expect(t *testing.T, w *httptest.ResponseRecorder, code int) {
	t.Helper()
	if w.Code != code {
		t.Fatalf("status %d, want %d; response %s", w.Code, code, w.Body.String())
	}
}

func openTest(t *testing.T, path string) *Server {
	t.Helper()
	s, err := Open(path, true)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

func seed(t *testing.T, s *Server, actor string) {
	t.Helper()
	if err := s.SeedTestOwner(actor, "synthetic-"+actor); err != nil {
		t.Fatal(err)
	}
}

func signIn(t *testing.T, s *Server, actor string) string {
	t.Helper()
	w := request(t, s, "POST", "/api/sign-in", "", map[string]string{"actor_id": actor, "password": string([]byte("synthetic-")) + actor, "device_id": "device-001"})
	expect(t, w, 200)
	var v struct {
		Token string `json:"token"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &v); err != nil {
		t.Fatal(err)
	}
	if v.Token == "" {
		t.Fatal("missing token")
	}
	return v.Token
}

func TestAuthenticationAndIndependentSessions(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "store.sqlite"))
	seed(t, s, "actor-001")
	for _, token := range []string{"", "invalid"} {
		expect(t, request(t, s, "GET", "/api/channels", token, nil), 401)
	}
	expect(t, request(t, s, "POST", "/api/sign-in", "", map[string]string{"actor_id": "actor-001", "password": string([]byte("incorrect")), "device_id": "device-001"}), 401)
	a, b := signIn(t, s, "actor-001"), signIn(t, s, "actor-001")
	expect(t, request(t, s, "POST", "/api/sign-out", a, nil), 204)
	expect(t, request(t, s, "GET", "/api/channels", a, nil), 401)
	expect(t, request(t, s, "GET", "/api/channels", b, nil), 200)
	c := signIn(t, s, "actor-001")
	expect(t, request(t, s, "POST", "/api/sign-out", b, nil), 204)
	expect(t, request(t, s, "GET", "/api/channels", c, nil), 200)
}

func TestExpiredSessionsAndStoredHashes(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "store.sqlite"))
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	var stored []byte
	var passwordHash []byte
	if err := s.db.QueryRow("SELECT token_hash FROM sessions").Scan(&stored); err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256([]byte(token))
	if !bytes.Equal(stored, digest[:]) {
		t.Fatal("session does not store the token digest")
	}
	if err := s.db.QueryRow("SELECT password_hash FROM owners").Scan(&passwordHash); err != nil {
		t.Fatal(err)
	}
	if err := bcrypt.CompareHashAndPassword(passwordHash, []byte("synthetic-actor-001")); err != nil {
		t.Fatal("password is not bcrypt hashed")
	}
	if _, err := s.db.Exec("UPDATE sessions SET expires_at=0"); err != nil {
		t.Fatal(err)
	}
	expect(t, request(t, s, "GET", "/api/channels", token, nil), 401)
	expect(t, request(t, s, "GET", "/api/channels", strings.Repeat("0", 64), nil), 401)
}

func TestAuthenticationDisabledWithoutTestMode(t *testing.T) {
	path := filepath.Join(t.TempDir(), "store.sqlite")
	enabled := openTest(t, path)
	seed(t, enabled, "actor-001")
	token := signIn(t, enabled, "actor-001")
	if err := enabled.Close(); err != nil {
		t.Fatal(err)
	}
	disabled, err := Open(path, false)
	if err != nil {
		t.Fatal(err)
	}
	defer disabled.Close()
	for _, candidate := range []string{"", "invalid", token} {
		expect(t, request(t, disabled, "GET", "/api/channels", candidate, nil), 401)
		expect(t, request(t, disabled, "POST", "/api/sign-out", candidate, nil), 401)
	}
	credentials := map[string]string{"actor_id": "actor-001", "device_id": "device-001"}
	credentials["password"] = "synthetic-actor-001"
	expect(t, request(t, disabled, "POST", "/api/sign-in", "", credentials), 401)
	if err := disabled.SeedTestOwner("actor-002", "synthetic-actor-002"); err == nil {
		t.Fatal("test seeding allowed without test mode")
	}
}

func TestTestModeRejectsNonSyntheticOwners(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "store.sqlite"))
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	// This neutral fixture represents an owner outside the permitted actor ID syntax.
	if _, err := s.db.Exec("INSERT INTO owners SELECT 'owner-001',password_hash FROM owners WHERE owner_id='actor-001'"); err != nil {
		t.Fatal(err)
	}
	if _, err := s.db.Exec("UPDATE sessions SET owner_id='owner-001'"); err != nil {
		t.Fatal(err)
	}
	expect(t, request(t, s, "GET", "/api/channels", token, nil), 401)
	credentials := map[string]string{"actor_id": "owner-001", "device_id": "device-001"}
	credentials["password"] = "synthetic-actor-001"
	expect(t, request(t, s, "POST", "/api/sign-in", "", credentials), 401)
}
