package main

import (
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"unicode/utf8"
)

type Channel struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Seq  int64  `json:"seq"`
}
type Message struct {
	ID        string `json:"id"`
	ChannelID string `json:"channel_id"`
	Body      string `json:"body"`
	Seq       int64  `json:"seq"`
}
type Event struct {
	Seq      int64           `json:"seq"`
	OwnerID  string          `json:"owner_id"`
	Kind     string          `json:"kind"`
	EntityID string          `json:"entity_id"`
	Payload  json.RawMessage `json:"payload"`
}
type SyncPage struct {
	HistoryID  string  `json:"history_id"`
	Events     []Event `json:"events"`
	NextCursor int64   `json:"next_seq"`
}

var uuid7 = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

func (s *Server) data(w http.ResponseWriter, r *http.Request, owner string) {
	path := r.URL.Path
	switch {
	case path == "/api/sync" && r.Method == "GET":
		s.sync(w, r, owner)
	case path == "/api/channels" && r.Method == "POST":
		s.createChannel(w, r, owner)
	case path == "/api/channels" && r.Method == "GET":
		s.channels(w, r, owner)
	case strings.HasPrefix(path, "/api/channels/"):
		rest := strings.TrimPrefix(path, "/api/channels/")
		parts := strings.Split(rest, "/")
		if len(parts) == 1 && r.Method == "GET" {
			s.channel(w, r, owner, parts[0])
			return
		}
		if len(parts) == 2 && parts[1] == "messages" {
			if r.Method == "POST" {
				s.createMessage(w, r, owner, parts[0])
				return
			}
			if r.Method == "GET" {
				s.messages(w, r, owner, parts[0])
				return
			}
		}
		problem(w, 404)
	default:
		problem(w, 404)
	}
}
func (s *Server) channels(w http.ResponseWriter, r *http.Request, owner string) {
	rows, err := s.db.QueryContext(r.Context(), "SELECT id,name,seq FROM channels WHERE owner_id=? ORDER BY seq", owner)
	if err != nil {
		problem(w, 500)
		return
	}
	defer rows.Close()
	list := []Channel{}
	for rows.Next() {
		var c Channel
		if err = rows.Scan(&c.ID, &c.Name, &c.Seq); err != nil {
			problem(w, 500)
			return
		}
		list = append(list, c)
	}
	if rows.Err() != nil {
		problem(w, 500)
		return
	}
	reply(w, 200, map[string]any{"channels": list})
}
func (s *Server) channel(w http.ResponseWriter, r *http.Request, owner, id string) {
	var c Channel
	err := s.db.QueryRowContext(r.Context(), "SELECT id,name,seq FROM channels WHERE owner_id=? AND id=?", owner, id).Scan(&c.ID, &c.Name, &c.Seq)
	if errors.Is(err, sql.ErrNoRows) {
		problem(w, 404)
		return
	}
	if err != nil {
		problem(w, 500)
		return
	}
	reply(w, 200, c)
}
func (s *Server) createChannel(w http.ResponseWriter, r *http.Request, owner string) {
	var c Channel
	// A separate input prevents clients from assigning server sequence numbers.
	var input struct {
		ID   string `json:"id"`
		Name string `json:"name"`
	}
	if !decode(w, r, &input) {
		return
	}
	if !uuid7.MatchString(input.ID) || strings.TrimSpace(input.Name) == "" || len(input.Name) > 200 || !utf8.ValidString(input.Name) {
		problem(w, 400)
		return
	}
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	tx, err := s.db.BeginTx(r.Context(), nil)
	if err != nil {
		problem(w, 500)
		return
	}
	defer tx.Rollback()
	var existingOwner string
	err = tx.QueryRowContext(r.Context(), "SELECT owner_id,id,name,seq FROM channels WHERE id=?", input.ID).Scan(&existingOwner, &c.ID, &c.Name, &c.Seq)
	if err == nil {
		if existingOwner != owner {
			problem(w, 404)
		} else if c.Name != input.Name {
			problem(w, 409)
		} else {
			s.replyChannel(w, 200, c)
		}
		return
	}
	if !errors.Is(err, sql.ErrNoRows) {
		problem(w, 500)
		return
	}
	c = Channel{ID: input.ID, Name: input.Name}
	c.Seq, err = eventSequence(tx, owner, "channel.created", c.ID)
	if err != nil {
		problem(w, 500)
		return
	}
	if _, err = tx.ExecContext(r.Context(), "INSERT INTO channels(id,owner_id,name,seq) VALUES (?,?,?,?)", c.ID, owner, c.Name, c.Seq); err == nil {
		err = eventPayload(tx, c.Seq, c)
	}
	if err == nil {
		err = s.commitEvent(tx, c.Seq)
	}
	if err != nil {
		problem(w, 500)
		return
	}
	s.replyChannel(w, 201, c)
}
func (s *Server) createMessage(w http.ResponseWriter, r *http.Request, owner, channel string) {
	var input struct {
		ID   string `json:"id"`
		Body string `json:"body"`
	}
	if !decode(w, r, &input) {
		return
	}
	if !uuid7.MatchString(input.ID) || strings.TrimSpace(input.Body) == "" || len(input.Body) > 65536 || !utf8.ValidString(input.Body) {
		problem(w, 400)
		return
	}
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	tx, err := s.db.BeginTx(r.Context(), nil)
	if err != nil {
		problem(w, 500)
		return
	}
	defer tx.Rollback()
	var found string
	err = tx.QueryRowContext(r.Context(), "SELECT id FROM channels WHERE owner_id=? AND id=?", owner, channel).Scan(&found)
	if errors.Is(err, sql.ErrNoRows) {
		problem(w, 404)
		return
	}
	if err != nil {
		problem(w, 500)
		return
	}
	var m Message
	var existingOwner string
	err = tx.QueryRowContext(r.Context(), "SELECT owner_id,id,channel_id,body,seq FROM messages WHERE id=?", input.ID).Scan(&existingOwner, &m.ID, &m.ChannelID, &m.Body, &m.Seq)
	if err == nil {
		if existingOwner != owner {
			problem(w, 404)
		} else if m.Body != input.Body || m.ChannelID != channel {
			problem(w, 409)
		} else {
			s.replyMessage(w, 200, m)
		}
		return
	}
	if !errors.Is(err, sql.ErrNoRows) {
		problem(w, 500)
		return
	}
	m = Message{ID: input.ID, ChannelID: channel, Body: input.Body}
	m.Seq, err = eventSequence(tx, owner, "message.created", m.ID)
	if err != nil {
		problem(w, 500)
		return
	}
	if _, err = tx.ExecContext(r.Context(), "INSERT INTO messages(id,owner_id,channel_id,body,seq) VALUES (?,?,?,?,?)", m.ID, owner, m.ChannelID, m.Body, m.Seq); err == nil {
		err = eventPayload(tx, m.Seq, m)
	}
	if err == nil {
		err = s.commitEvent(tx, m.Seq)
	}
	if err != nil {
		problem(w, 500)
		return
	}
	s.replyMessage(w, 201, m)
}
func eventSequence(tx *sql.Tx, owner, kind, id string) (int64, error) {
	result, err := tx.Exec("INSERT INTO events(owner_id,kind,entity_id,payload) VALUES (?,?,?,'{}')", owner, kind, id)
	if err != nil {
		return 0, err
	}
	return result.LastInsertId()
}
func eventPayload(tx *sql.Tx, seq int64, entity any) error {
	payload, err := json.Marshal(entity)
	if err != nil {
		return err
	}
	_, err = tx.Exec("UPDATE events SET payload=? WHERE seq=?", string(payload), seq)
	return err
}
func (s *Server) messages(w http.ResponseWriter, r *http.Request, owner, channel string) {
	// The read transaction keeps the ownership check and list in the same snapshot.
	tx, err := s.db.BeginTx(r.Context(), nil)
	if err != nil {
		problem(w, 500)
		return
	}
	defer tx.Rollback()
	var found string
	err = tx.QueryRowContext(r.Context(), "SELECT id FROM channels WHERE owner_id=? AND id=?", owner, channel).Scan(&found)
	if errors.Is(err, sql.ErrNoRows) {
		problem(w, 404)
		return
	}
	if err != nil {
		problem(w, 500)
		return
	}
	rows, err := tx.QueryContext(r.Context(), "SELECT id,channel_id,body,seq FROM messages WHERE owner_id=? AND channel_id=? ORDER BY seq", owner, channel)
	if err != nil {
		problem(w, 500)
		return
	}
	defer rows.Close()
	list := []Message{}
	for rows.Next() {
		var m Message
		if err = rows.Scan(&m.ID, &m.ChannelID, &m.Body, &m.Seq); err != nil {
			problem(w, 500)
			return
		}
		list = append(list, m)
	}
	if rows.Err() != nil {
		problem(w, 500)
		return
	}
	reply(w, 200, map[string]any{"messages": list})
}
func (s *Server) sync(w http.ResponseWriter, r *http.Request, owner string) {
	after, limit := int64(0), int64(100)
	var err error
	if values, ok := r.URL.Query()["after"]; ok {
		if len(values) != 1 {
			problem(w, 400)
			return
		}
		after, err = strconv.ParseInt(values[0], 10, 64)
		if err != nil || after < 0 {
			problem(w, 400)
			return
		}
	}
	if values, ok := r.URL.Query()["limit"]; ok {
		if len(values) != 1 {
			problem(w, 400)
			return
		}
		limit, err = strconv.ParseInt(values[0], 10, 64)
		if err != nil || limit < 1 || limit > 500 {
			problem(w, 400)
			return
		}
	}
	histories, present := r.URL.Query()["history"]
	if present && len(histories) != 1 {
		problem(w, 400)
		return
	}
	if (present && histories[0] != s.historyID) || (!present && after > 0) {
		problem(w, 410)
		return
	}
	tx, err := s.db.BeginTx(r.Context(), nil)
	if err != nil {
		problem(w, 500)
		return
	}
	defer tx.Rollback()
	var maxSeq int64
	if err = tx.QueryRowContext(r.Context(), "SELECT COALESCE(MAX(seq),0) FROM events WHERE owner_id=?", owner).Scan(&maxSeq); err != nil {
		problem(w, 500)
		return
	}
	if after > maxSeq {
		problem(w, 410)
		return
	}
	rows, err := tx.QueryContext(r.Context(), "SELECT seq,owner_id,kind,entity_id,payload FROM events WHERE owner_id=? AND seq>? ORDER BY seq LIMIT ?", owner, after, limit)
	if err != nil {
		problem(w, 500)
		return
	}
	defer rows.Close()
	page := SyncPage{Events: []Event{}, NextCursor: after, HistoryID: s.historyID}
	for rows.Next() {
		var e Event
		var payload string
		if err = rows.Scan(&e.Seq, &e.OwnerID, &e.Kind, &e.EntityID, &payload); err != nil {
			problem(w, 500)
			return
		}
		e.Payload = json.RawMessage(payload)
		page.Events = append(page.Events, e)
		page.NextCursor = e.Seq
	}
	if rows.Err() != nil {
		problem(w, 500)
		return
	}
	reply(w, 200, page)
}

func (s *Server) replyChannel(w http.ResponseWriter, code int, c Channel) {
	reply(w, code, struct {
		Channel
		HistoryID string `json:"history_id"`
	}{Channel: c, HistoryID: s.historyID})
}
func (s *Server) replyMessage(w http.ResponseWriter, code int, m Message) {
	reply(w, code, struct {
		Message
		HistoryID string `json:"history_id"`
	}{Message: m, HistoryID: s.historyID})
}
