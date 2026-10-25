package main

import (
	"encoding/json"
	"testing"
)

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
