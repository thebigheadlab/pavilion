package main

import "net/http"

func (s *Server) data(w http.ResponseWriter, r *http.Request, owner string) {
	if r.Method == "GET" && r.URL.Path == "/api/channels" {
		reply(w, 200, map[string]any{"channels": []any{}})
		return
	}
	problem(w, 404)
}
