package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "server failed:", err)
		os.Exit(1)
	}
}
func run() error {
	address := flag.String("listen", "127.0.0.1:8080", "HTTP listen address")
	path := flag.String("db", "", "SQLite database file outside the checkout (required)")
	testMode := flag.Bool("test-mode", false, "seed actor-001 from PAVILION_TEST_PASSWORD; local tests only")
	flag.Parse()
	if !*testMode {
		fmt.Fprintln(os.Stderr, "authentication disabled until production bootstrap is approved")
	}
	s, err := Open(*path, *testMode)
	if err != nil {
		return err
	}
	defer s.Close()
	if *testMode {
		if err = s.SeedTestOwner("actor-001", os.Getenv("PAVILION_TEST_PASSWORD")); err != nil {
			return err
		}
	}
	server := &http.Server{Addr: *address, Handler: s, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 30 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 16 << 10}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	exited := make(chan struct{})
	go func() {
		defer close(exited)
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdown)
	}()
	err = server.ListenAndServe()
	stop()
	<-exited
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}
