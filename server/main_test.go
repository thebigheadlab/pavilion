package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestStartupReportsRealErrorWithoutCredentials(t *testing.T) {
	if os.Getenv("PAVILION_STARTUP_HELPER") == "1" {
		os.Args = []string{"server", "-test-mode", "-db", os.Getenv("PAVILION_STARTUP_DB")}
		main()
		return
	}
	for _, test := range []struct{ name, path, want string }{
		{"missing database", "", "database path is required"},
		{"invalid test credential", filepath.Join(t.TempDir(), "store.sqlite"), "invalid synthetic owner or test password length"},
	} {
		t.Run(test.name, func(t *testing.T) {
			sentinel := strings.Repeat("s", 73)
			cmd := exec.Command(os.Args[0], "-test.run=^TestStartupReportsRealErrorWithoutCredentials$")
			cmd.Env = append(os.Environ(), "PAVILION_STARTUP_HELPER=1", "PAVILION_STARTUP_DB="+test.path, "PAVILION_TEST_PASSWORD="+sentinel)
			output, err := cmd.CombinedOutput()
			exit, ok := err.(*exec.ExitError)
			if !ok || exit.ExitCode() != 1 {
				t.Fatal("startup did not fail with exit status 1")
			}
			if !strings.Contains(string(output), test.want) {
				t.Fatal("startup omitted the real error")
			}
			if strings.Contains(string(output), sentinel) {
				t.Fatal("startup printed the synthetic credential sentinel")
			}
		})
	}
}
