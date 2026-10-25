package main

import (
	"testing"
)

func openTest(t *testing.T, path string) *Server {
	t.Helper()
	s, err := Open(path, true)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}
