package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"golang.org/x/crypto/bcrypt"
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

const channelID = "00000000-0000-7000-8000-000000000001"
const messageID = "00000000-0000-7000-8000-000000000002"
const otherChannelID = "00000000-0000-7000-8000-000000000003"

func createChannel(t *testing.T, s *Server, token, id string) *httptest.ResponseRecorder {
	t.Helper()
	return request(t, s, "POST", "/api/channels", token, map[string]string{"id": id, "name": "channel-001"})
}
func createMessage(t *testing.T, s *Server, token, channel, body string) *httptest.ResponseRecorder {
	t.Helper()
	return request(t, s, "POST", "/api/channels/"+channel+"/messages", token, map[string]string{"id": messageID, "body": body})
}
func TestChannelsMessagesIsolationAndRetries(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "store.sqlite"))
	seed(t, s, "actor-001")
	seed(t, s, "actor-002")
	a, b := signIn(t, s, "actor-001"), signIn(t, s, "actor-002")
	first := createChannel(t, s, a, channelID)
	expect(t, first, 201)
	retry := createChannel(t, s, a, channelID)
	expect(t, retry, 200)
	if first.Body.String() != retry.Body.String() {
		t.Fatal("channel retry changed response")
	}
	expect(t, request(t, s, "POST", "/api/channels", a, map[string]string{"id": channelID, "name": "channel-002"}), 409)
	expect(t, createChannel(t, s, b, channelID), 404)
	for _, suffix := range []string{"", "/messages"} {
		expect(t, request(t, s, "GET", "/api/channels/"+channelID+suffix, b, nil), 404)
	}
	expect(t, createMessage(t, s, b, channelID, "message-001"), 404)
	for _, path := range []string{"/api/channels", "/api/sync?after=0"} {
		w := request(t, s, "GET", path, b, nil)
		expect(t, w, 200)
		if bytes.Contains(w.Body.Bytes(), []byte(channelID)) {
			t.Fatal("other owner data disclosed")
		}
	}
	first = createMessage(t, s, a, channelID, "message-001")
	expect(t, first, 201)
	retry = createMessage(t, s, a, channelID, "message-001")
	expect(t, retry, 200)
	if first.Body.String() != retry.Body.String() {
		t.Fatal("message retry changed response")
	}
	expect(t, createMessage(t, s, a, channelID, "message-002"), 409)
	expect(t, createChannel(t, s, a, otherChannelID), 201)
	expect(t, createMessage(t, s, a, otherChannelID, "message-001"), 409)
	expect(t, createChannel(t, s, b, otherChannelID), 404)
	w := request(t, s, "GET", "/api/channels/"+channelID+"/messages", a, nil)
	expect(t, w, 200)
	var list struct {
		Messages []Message `json:"messages"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &list); err != nil {
		t.Fatal(err)
	}
	if len(list.Messages) != 1 || list.Messages[0].Body != "message-001" {
		t.Fatal("message lost or duplicated")
	}
	ownID := "00000000-0000-7000-8000-000000000004"
	expect(t, createChannel(t, s, b, ownID), 201)
	expect(t, createMessage(t, s, b, ownID, "message-001"), 404)
	expect(t, request(t, s, "POST", "/api/channels/"+ownID+"/messages", b, map[string]string{"id": "00000000-0000-7000-8000-000000000005", "body": "message-002"}), 201)
	expect(t, request(t, s, "GET", "/api/channels/"+ownID+"/messages", a, nil), 404)
	w = request(t, s, "GET", "/api/sync?after=0", a, nil)
	expect(t, w, 200)
	if bytes.Contains(w.Body.Bytes(), []byte(ownID)) {
		t.Fatal("sync disclosed another owner's event")
	}
}

func TestRestartRetryAndCursorRecovery(t *testing.T) {
	path := filepath.Join(t.TempDir(), "store.sqlite")
	s := openTest(t, path)
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	expect(t, createChannel(t, s, token, channelID), 201)
	saved := createMessage(t, s, token, channelID, "message-001")
	expect(t, saved, 201)
	history := responseHistory(t, saved.Body.Bytes())
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	retry := createMessage(t, s, token, channelID, "message-001")
	expect(t, retry, 200)
	if saved.Body.String() != retry.Body.String() {
		t.Fatal("retry after reopen changed message")
	}
	page := func(after string) SyncPage {
		t.Helper()
		w := request(t, s, "GET", "/api/sync?after="+after+"&limit=1&history="+history, token, nil)
		expect(t, w, 200)
		var p SyncPage
		if err := json.Unmarshal(w.Body.Bytes(), &p); err != nil {
			t.Fatal(err)
		}
		return p
	}
	p := page("0")
	if len(p.Events) != 1 || p.Events[0].Kind != "channel.created" || p.NextCursor != 1 {
		t.Fatal("first cursor page incorrect")
	}
	p = page("1")
	if len(p.Events) != 1 || p.Events[0].Kind != "message.created" || p.NextCursor != 2 {
		t.Fatal("missing ordered event")
	}
	p = page("2")
	if len(p.Events) != 0 || p.NextCursor != 2 {
		t.Fatal("retry appended duplicate event")
	}
	expect(t, request(t, s, "GET", "/api/sync?after=3&history="+history, token, nil), 410)
	for _, query := range []string{"after=-1", "after=bad", "limit=0", "limit=501", "limit=bad"} {
		expect(t, request(t, s, "GET", "/api/sync?"+query, token, nil), 400)
	}
	expect(t, request(t, s, "POST", "/api/sign-out", token, nil), 204)
	token = signIn(t, s, "actor-001")
	p = page("0")
	if len(p.Events) != 1 {
		t.Fatal("sign-out removed server history")
	}
	p = page("1")
	if len(p.Events) != 1 || p.Events[0].EntityID != messageID {
		t.Fatal("sign-in did not restore message history")
	}
	// Restoring a database before the channel existed invalidates the stored cursor.
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	restored := openTest(t, filepath.Join(t.TempDir(), "restored.sqlite"))
	seed(t, restored, "actor-001")
	fresh := signIn(t, restored, "actor-001")
	snapshot := request(t, restored, "GET", "/api/sync?after=0", fresh, nil)
	expect(t, snapshot, 200)
	restoredHistory := responseHistory(t, snapshot.Body.Bytes())
	expect(t, request(t, restored, "GET", "/api/sync?after=2&history="+restoredHistory, fresh, nil), 410)
	expect(t, request(t, restored, "GET", "/api/sync?after=0", fresh, nil), 200)
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

func TestValidationAndAtomicRollback(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "store.sqlite"))
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	expect(t, createChannel(t, s, token, "channel-001"), 400)
	expect(t, request(t, s, "POST", "/api/channels", token, map[string]string{"id": channelID, "name": "channel-001", "owner_id": "actor-002"}), 400)
	expect(t, request(t, s, "POST", "/api/channels", token, map[string]string{"id": "00000000-0000-4000-8000-000000000001", "name": "channel-001"}), 400)
	expect(t, createMessage(t, s, token, channelID, "message-001"), 404)
	// Simulate an event storage failure. No entity can escape its transaction.
	if _, err := s.db.Exec("CREATE TRIGGER reject_event BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"); err != nil {
		t.Fatal(err)
	}
	expect(t, createChannel(t, s, token, channelID), 500)
	expect(t, request(t, s, "GET", "/api/channels/"+channelID, token, nil), 404)
	w := request(t, s, "GET", "/api/sync?after=0", token, nil)
	expect(t, w, 200)
	var page SyncPage
	if err := json.Unmarshal(w.Body.Bytes(), &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Events) != 0 {
		t.Fatal("failed write appended an event")
	}
	if _, err := s.db.Exec("DROP TRIGGER reject_event"); err != nil {
		t.Fatal(err)
	}
	expect(t, createChannel(t, s, token, channelID), 201)
	if _, err := s.db.Exec("CREATE TRIGGER reject_event BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"); err != nil {
		t.Fatal(err)
	}
	expect(t, createMessage(t, s, token, channelID, "message-001"), 500)
	if _, err := s.db.Exec("DROP TRIGGER reject_event"); err != nil {
		t.Fatal(err)
	}
	expect(t, createMessage(t, s, token, channelID, "message-001"), 201)
	w = request(t, s, "GET", "/api/sync?after=0", token, nil)
	expect(t, w, 200)
	if err := json.Unmarshal(w.Body.Bytes(), &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Events) != 2 || page.Events[1].Seq != 2 {
		t.Fatal("rollback left partial rows or an event")
	}
}

func TestConcurrentRetriesCreateOneMessage(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "store.sqlite"))
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	channel := createChannel(t, s, token, channelID)
	expect(t, channel, 201)
	history := responseHistory(t, channel.Body.Bytes())
	results := make(chan int, 8)
	for i := 0; i < 8; i++ {
		go func() {
			r := httptest.NewRequest("POST", "/api/channels/"+channelID+"/messages", strings.NewReader(`{"id":"`+messageID+`","body":"message-001"}`))
			r.Header.Set("Authorization", "Bearer "+token)
			w := httptest.NewRecorder()
			s.ServeHTTP(w, r)
			results <- w.Code
		}()
	}
	created := 0
	for i := 0; i < 8; i++ {
		code := <-results
		if code == 201 {
			created++
		} else if code != 200 {
			t.Fatalf("concurrent retry status %d", code)
		}
	}
	if created != 1 {
		t.Fatalf("created %d messages, want one", created)
	}
	w := request(t, s, "GET", "/api/sync?after=1&history="+history, token, nil)
	expect(t, w, 200)
	var page SyncPage
	if err := json.Unmarshal(w.Body.Bytes(), &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Events) != 1 || page.Events[0].Kind != "message.created" {
		t.Fatal("concurrent retries duplicated events")
	}
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
