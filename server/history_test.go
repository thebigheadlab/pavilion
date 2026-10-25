package main

import (
	"encoding/json"
	"net/url"
	"os"
	"path/filepath"
	"testing"
)

func TestRestoredBackupRejectsOldHistoryAfterSequenceReuse(t *testing.T) {
	path := filepath.Join(t.TempDir(), "store.sqlite")
	s := openTest(t, path)
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	expect(t, createChannel(t, s, token, channelID), 201)
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	backup, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	expect(t, createMessage(t, s, token, channelID, "message-001"), 201)
	before := request(t, s, "GET", "/api/sync?after=0", token, nil)
	expect(t, before, 200)
	var old struct {
		HistoryID  string `json:"history_id"`
		NextCursor int64  `json:"next_seq"`
	}
	if err = json.Unmarshal(before.Body.Bytes(), &old); err != nil {
		t.Fatal(err)
	}
	if old.NextCursor != 2 {
		t.Fatal("client did not observe sequence 2")
	}
	if err = s.Close(); err != nil {
		t.Fatal(err)
	}
	// Restore only the checkpointed database. Keep the live high-water sidecar.
	if err = os.WriteFile(path, backup, 0600); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	write := createMessage(t, s, token, channelID, "message-002")
	expect(t, write, 201)
	expect(t, request(t, s, "GET", "/api/sync?after=2&history="+url.QueryEscape(old.HistoryID), token, nil), 410)
	recovered := request(t, s, "GET", "/api/sync?after=0", token, nil)
	expect(t, recovered, 200)
	var current struct {
		HistoryID  string  `json:"history_id"`
		NextCursor int64   `json:"next_seq"`
		Events     []Event `json:"events"`
	}
	if err = json.Unmarshal(recovered.Body.Bytes(), &current); err != nil {
		t.Fatal(err)
	}
	if current.HistoryID == "" || current.HistoryID == old.HistoryID || current.NextCursor != 2 || len(current.Events) != 2 {
		t.Fatal("restore did not establish a fresh history with reused sequences")
	}
	var ack struct {
		HistoryID string `json:"history_id"`
	}
	if err = json.Unmarshal(write.Body.Bytes(), &ack); err != nil {
		t.Fatal(err)
	}
	if ack.HistoryID != current.HistoryID {
		t.Fatal("write acknowledgment belongs to a different history")
	}
	var message Message
	if err = json.Unmarshal(current.Events[1].Payload, &message); err != nil {
		t.Fatal(err)
	}
	if message.Body != "message-002" {
		t.Fatal("recovery returned the replaced message")
	}
}

func responseHistory(t *testing.T, body []byte) string {
	t.Helper()
	var value struct {
		HistoryID string `json:"history_id"`
	}
	if err := json.Unmarshal(body, &value); err != nil {
		t.Fatal(err)
	}
	if len(value.HistoryID) != 64 {
		t.Fatal("response has no history ID")
	}
	return value.HistoryID
}

func TestHistoryResponsesAndNormalRestart(t *testing.T) {
	path := filepath.Join(t.TempDir(), "store.sqlite")
	s := openTest(t, path)
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	initial := request(t, s, "GET", "/api/sync?after=0", token, nil)
	expect(t, initial, 200)
	history := responseHistory(t, initial.Body.Bytes())
	for _, status := range []int{201, 200} {
		channel := createChannel(t, s, token, channelID)
		expect(t, channel, status)
		if responseHistory(t, channel.Body.Bytes()) != history {
			t.Fatal("channel acknowledgment changed history")
		}
		message := createMessage(t, s, token, channelID, "message-001")
		expect(t, message, status)
		if responseHistory(t, message.Body.Bytes()) != history {
			t.Fatal("message acknowledgment changed history")
		}
	}
	data, err := os.ReadFile(path + ".history")
	if err != nil {
		t.Fatal(err)
	}
	var state struct {
		HistoryID string `json:"history_id"`
		HighWater int64  `json:"high_water"`
	}
	if err = json.Unmarshal(data, &state); err != nil {
		t.Fatal(err)
	}
	if state.HistoryID != history || state.HighWater != 2 {
		t.Fatal("acknowledged events are absent from the high-water file")
	}
	info, err := os.Stat(path + ".history")
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0600 {
		t.Fatal("history sidecar is not private")
	}
	expect(t, request(t, s, "GET", "/api/sync?after=2", token, nil), 410)
	expect(t, request(t, s, "GET", "/api/sync?after=2&history="+history, token, nil), 200)
	expect(t, request(t, s, "GET", "/api/sync?after=0&history=unknown", token, nil), 410)
	expect(t, request(t, s, "GET", "/api/sync?after=0&history="+history+"&history="+history, token, nil), 400)
	if err = s.Close(); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	after := request(t, s, "GET", "/api/sync?after=2&history="+history, token, nil)
	expect(t, after, 200)
	if responseHistory(t, after.Body.Bytes()) != history {
		t.Fatal("normal restart rotated history")
	}
}

func TestMissingOrMalformedHistoryState(t *testing.T) {
	path := filepath.Join(t.TempDir(), "store.sqlite")
	s := openTest(t, path)
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	first := request(t, s, "GET", "/api/sync?after=0", token, nil)
	expect(t, first, 200)
	history := responseHistory(t, first.Body.Bytes())
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(path + ".history"); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	expect(t, request(t, s, "GET", "/api/sync?after=0&history="+history, token, nil), 410)
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path+".history", []byte("{"), 0600); err != nil {
		t.Fatal(err)
	}
	broken, err := Open(path, true)
	if err == nil {
		broken.Close()
		t.Fatal("malformed history state accepted")
	}
}

func TestFailedHistoryPersistenceRollsBackEvent(t *testing.T) {
	path := filepath.Join(t.TempDir(), "store.sqlite")
	s := openTest(t, path)
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	if err := os.Remove(path + ".history"); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(path+".history", 0700); err != nil {
		t.Fatal(err)
	}
	expect(t, createChannel(t, s, token, channelID), 500)
	expect(t, request(t, s, "GET", "/api/channels/"+channelID, token, nil), 404)
	page := request(t, s, "GET", "/api/sync?after=0", token, nil)
	expect(t, page, 200)
	var events struct {
		Events []Event `json:"events"`
	}
	if err := json.Unmarshal(page.Body.Bytes(), &events); err != nil {
		t.Fatal(err)
	}
	if len(events.Events) != 0 {
		t.Fatal("event committed without a durable history marker")
	}
	if err := os.Remove(path + ".history"); err != nil {
		t.Fatal(err)
	}
	expect(t, createChannel(t, s, token, channelID), 201)
}

func TestWholeDirectoryRestoreLimits(t *testing.T) {
	live := t.TempDir()
	backup := t.TempDir()
	path := filepath.Join(live, "store.sqlite")
	names := []string{"store.sqlite", "store.sqlite-wal", "store.sqlite-shm", "store.sqlite.history"}
	copyFiles := func(t *testing.T, from, to string) {
		t.Helper()
		for _, name := range names {
			data, err := os.ReadFile(filepath.Join(from, name))
			if err != nil {
				t.Fatal(err)
			}
			if len(data) == 0 {
				t.Fatal("snapshot file is empty")
			}
			if err = os.WriteFile(filepath.Join(to, name), data, 0600); err != nil {
				t.Fatal(err)
			}
		}
	}
	s := openTest(t, path)
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	expect(t, createChannel(t, s, token, channelID), 201)
	// All requests have finished. No writer runs while these four files are copied.
	// Keep WAL and SHM present so the fixture tests a whole-directory snapshot.
	copyFiles(t, live, backup)
	expect(t, createMessage(t, s, token, channelID, "message-001"), 201)
	observed := request(t, s, "GET", "/api/sync?after=0", token, nil)
	expect(t, observed, 200)
	var client SyncPage
	if err := json.Unmarshal(observed.Body.Bytes(), &client); err != nil {
		t.Fatal(err)
	}
	if client.NextCursor != 2 || len(client.Events) != 2 {
		t.Fatal("client did not observe the newer history")
	}
	history := responseHistory(t, observed.Body.Bytes())
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name          string
		writes        int
		status        int
		removeHistory bool
	}{
		{"cursor still ahead", 0, 410, false},
		{"writes reach client cursor", 1, 200, false},
		{"writes pass client cursor", 2, 200, false},
		{"explicit restore action removes old marker", 1, 410, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			// Replace every file, including the live high-water file, from the older snapshot.
			copyFiles(t, backup, live)
			if test.removeHistory {
				if err := os.Remove(path + ".history"); err != nil {
					t.Fatal(err)
				}
			}
			restored := openTest(t, path)
			defer restored.Close()
			initial := request(t, restored, "GET", "/api/sync?after=0", token, nil)
			expect(t, initial, 200)
			var old SyncPage
			if err := json.Unmarshal(initial.Body.Bytes(), &old); err != nil {
				t.Fatal(err)
			}
			if old.NextCursor != 1 || len(old.Events) != 1 {
				t.Fatal("whole-directory restore did not recover the older cursor")
			}
			if test.removeHistory {
				if old.HistoryID == history {
					t.Fatal("explicit restore action did not rotate history")
				}
			} else if old.HistoryID != history {
				t.Fatal("whole-directory restore unexpectedly rotated history")
			}
			if test.writes > 0 {
				expect(t, createMessage(t, restored, token, channelID, "message-002"), 201)
			}
			if test.writes > 1 {
				expect(t, request(t, restored, "POST", "/api/channels/"+channelID+"/messages", token, map[string]string{"id": "00000000-0000-7000-8000-000000000005", "body": "message-003"}), 201)
			}
			synced := request(t, restored, "GET", "/api/sync?after=2&history="+url.QueryEscape(history), token, nil)
			expect(t, synced, test.status)
			if test.status == 410 {
				if test.removeHistory {
					expect(t, request(t, restored, "GET", "/api/sync?after=2&history="+url.QueryEscape(old.HistoryID), token, nil), 200)
					return
				}
				// A matching history ID works at the restored cursor. Only cursor-ahead caused 410.
				expect(t, request(t, restored, "GET", "/api/sync?after=1&history="+url.QueryEscape(history), token, nil), 200)
				return
			}
			var page SyncPage
			if err := json.Unmarshal(synced.Body.Bytes(), &page); err != nil {
				t.Fatal(err)
			}
			if page.HistoryID != history || page.NextCursor != int64(1+test.writes) || len(page.Events) != test.writes-1 {
				t.Fatal("unexpected sync after undetected restore")
			}
			for _, event := range page.Events {
				if event.Seq <= client.NextCursor {
					t.Fatal("sync unexpectedly returned the replaced event")
				}
			}
			full := request(t, restored, "GET", "/api/sync?after=0", token, nil)
			expect(t, full, 200)
			var actual SyncPage
			if err := json.Unmarshal(full.Body.Bytes(), &actual); err != nil {
				t.Fatal(err)
			}
			var previous, replacement Message
			if err := json.Unmarshal(client.Events[1].Payload, &previous); err != nil {
				t.Fatal(err)
			}
			if err := json.Unmarshal(actual.Events[1].Payload, &replacement); err != nil {
				t.Fatal(err)
			}
			if previous.ID != replacement.ID || previous.Seq != replacement.Seq || previous.Body != "message-001" || replacement.Body != "message-002" {
				t.Fatal("fixture did not reproduce an unreported stale client row")
			}
		})
	}
}

func TestStartupRemovesStrayHistoryTemps(t *testing.T) {
	directory := t.TempDir()
	path := filepath.Join(directory, ".history-store.sqlite")
	s := openTest(t, path)
	seed(t, s, "actor-001")
	token := signIn(t, s, "actor-001")
	channel := createChannel(t, s, token, channelID)
	expect(t, channel, 201)
	history := responseHistory(t, channel.Body.Bytes())
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{".history-leftover-001", ".history-leftover-002", "keep-001"} {
		if err := os.WriteFile(filepath.Join(directory, name), []byte("synthetic-001"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	keepDirectory := filepath.Join(directory, ".history-directory-001")
	if err := os.Mkdir(keepDirectory, 0700); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	for _, name := range []string{".history-leftover-001", ".history-leftover-002"} {
		if _, err := os.Stat(filepath.Join(directory, name)); !os.IsNotExist(err) {
			t.Fatal("stray history temporary file remains")
		}
	}
	for _, name := range []string{"keep-001", ".history-directory-001", filepath.Base(path), filepath.Base(path) + "-wal", filepath.Base(path) + "-shm", filepath.Base(path) + ".history"} {
		if _, err := os.Stat(filepath.Join(directory, name)); err != nil {
			t.Fatal("startup cleanup removed a retained entry")
		}
	}
	expect(t, request(t, s, "GET", "/api/sync?after=1&history="+url.QueryEscape(history), token, nil), 200)
}
