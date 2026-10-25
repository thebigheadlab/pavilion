"""Check rejection with synthetic data. Use no real private data or credentials."""

from datetime import date, timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publication_guard.py"
SPEC = importlib.util.spec_from_file_location("guard", SCRIPT)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
SENTINEL = "PAVILION_" + "TEST_SECRET_001"
SCRATCH = Path.home() / ".cache" / "agent-scratch"
# Synthetic operational markers. Real markers load only from a private local file.
MARKER = "marker-tool-001"
MARKER_FILE_TEXT = MARKER + "\nMarker Tool 002\n"


class ContentTests(unittest.TestCase):
    def check_rule(self, rule, text, name="fixture.txt", mode="100644"):
        scanner = guard.Scanner()
        scanner.scan(name, text.encode() if isinstance(text, str) else text, mode)
        self.assertIn(rule, [f["rule"] for f in scanner.findings])

    def test_neutral_fixture_passes(self):
        scanner = guard.Scanner()
        scanner.scan("fixture.txt", b"actor-001 channel-001 message-001\n")
        self.assertEqual([], scanner.findings)

    def test_synthetic_secret(self):
        self.check_rule("synthetic-sentinel", SENTINEL)

    def test_constructed_contact_syntax(self):
        self.check_rule("email", "actor-001" + "@" + "invalid.test")

    def test_constructed_private_paths(self):
        for value in ["/" + "home/actor-001/file", "/" + "Users/actor-001/file", "C:" + "\\Users\\actor-001\\file"]:
            self.check_rule("private-path", value)

    def test_constructed_auth_and_key(self):
        self.check_rule("auth-header", "Authorization" + ": Bearer " + SENTINEL)
        self.check_rule("private-key", "-----BEGIN " + "PRIVATE KEY-----")

    def test_constructed_token_shapes(self):
        for prefix, suffix in [("gh" + "p_", "0" * 36), ("AK" + "IA", "0" * 16), ("s" + "k-", "0" * 24)]:
            self.check_rule("secret-token", prefix + suffix)

    def test_assignment_and_jwt(self):
        self.check_rule("credential-assignment", "api_key" + " = " + "unit_00000001")
        self.check_rule("jwt", "ey" + "J" + "0" * 10 + "." + "0" * 12 + "." + "0" * 12)

    def test_contact_number(self):
        self.check_rule("contact-number", "+" + "0" * 12)

    def test_private_network(self):
        self.check_rule("private-network", "100." + "64.0.1")
        self.check_rule("private-network", "node-001" + ".ts.net")

    def test_private_link_and_message(self):
        self.check_rule("private-link", "https://unit-001." + "slack.com/archives/channel-001")
        self.check_rule("private-message-id", "U" + "0" * 10)

    def test_binary_large_and_control(self):
        self.check_rule("binary-or-encoding", b"\x00payload")
        self.check_rule("oversize", b"x" * (guard.MAX_BYTES + 1))
        self.check_rule("invisible-control", "actor" + chr(0x202E) + "001")

    def test_private_credential_configs_and_svg(self):
        for name in [".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials", ".gitconfig", ".docker/config.json", ".kube/config"]:
            self.check_rule("private-file", "actor-001", name)
        for name in ["fixture.svg", "fixture.svgz"]:
            self.check_rule("opaque-or-log-file", "actor-001", name)
        self.check_rule("opaque-or-log-file", "<" + "svg xmlns='unit-001'>actor-001</" + "svg>", "fixture.txt")

    def test_paths_and_modes(self):
        for name in ["logs/capture.txt", "capture.log", ".env.local", "state.sqlite", "capture.zip", ".config/settings.txt"]:
            expected = "private-file" if name.split("/")[0] in guard.PRIVATE_PARTS or name.startswith(".env.") else "opaque-or-log-file"
            self.check_rule(expected, "actor-001", name)
        for mode in ["120000", "160000"]:
            self.check_rule("symlink-or-submodule", "", mode=mode)

    def test_marker_rule_matches_lines_and_names_case_insensitively(self):
        markers = guard.load_markers_from(["Marker-Tool-001", " marker tool 002 "])
        for name, text in [("fixture.txt", "We use MARKER-tool-001 here"), ("fixture.txt", "a marker TOOL 002 b"), ("marker-tool-001.txt", "actor-001")]:
            scanner = guard.Scanner(markers=markers)
            scanner.scan(name, text.encode())
            self.assertEqual(["operational-marker"], [f["rule"] for f in scanner.findings])
        scanner = guard.Scanner(markers=markers)
        scanner.scan("fixture.txt", b"actor-001 marker-tool-003\n")
        self.assertEqual([], scanner.findings)

    def test_marker_rule_is_skipped_without_markers(self):
        scanner = guard.Scanner()
        scanner.scan("fixture.txt", MARKER.encode())
        self.assertEqual([], scanner.findings)

    def test_marker_exception_is_exact_and_needs_a_clean_reason(self):
        line = "We use " + MARKER + " here"
        markers = (MARKER,)
        entry = {**self.entry(line), "rule": "operational-marker"}
        entries = guard.load_policy(json.dumps([entry]), markers)
        scanner = guard.Scanner(entries, markers)
        scanner.scan("fixture.txt", line.encode())
        self.assertEqual([], scanner.findings)
        scanner.scan("fixture.txt", (line + " changed").encode())
        scanner.scan("other.txt", line.encode())
        self.assertEqual(2, len(scanner.findings))
        with self.assertRaises(guard.GuardError):
            guard.load_policy(json.dumps([{**entry, "reason": "Product reference to " + MARKER + " only."}]), markers)

    def entry(self, line):
        return {"path": "fixture.txt", "rule": "high-entropy", "line_sha256": hashlib.sha256(line.encode()).hexdigest(), "reason": "Synthetic alphabet for scanner verification only.", "expires": (date.today() + timedelta(days=7)).isoformat()}

    def test_exact_entropy_exception(self):
        line = "".join(chr(n) for n in range(65, 91)) + "".join(chr(n) for n in range(97, 123))
        entries = guard.load_policy(json.dumps([self.entry(line)]))
        scanner = guard.Scanner(entries)
        scanner.scan("fixture.txt", line.encode())
        self.assertEqual([], scanner.findings)
        self.assertEqual({0}, scanner.used)
        scanner.scan("other.txt", line.encode())
        self.assertTrue(scanner.findings)
        scanner.scan("fixture.txt", (line + "changed").encode())
        self.assertEqual(2, len(scanner.findings))

    def test_unsafe_expired_and_duplicate_allowlists(self):
        entry = self.entry("unit-001")
        for change in [{"path": "*.txt"}, {"path": "../fixture.txt"}, {"rule": "synthetic-sentinel"}, {"reason": "short"}, {"expires": (date.today() - timedelta(days=1)).isoformat()}, {"expires": (date.today() + timedelta(days=91)).isoformat()}]:
            with self.assertRaises(guard.GuardError):
                guard.load_policy(json.dumps([{**entry, **change}]))
        with self.assertRaises(guard.GuardError):
            guard.load_policy(json.dumps([entry, entry]))


class GitTests(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="pavilion-guard-", dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.git("init", "--quiet")
        self.write(guard.POLICY, "[]\n")
        self.write("fixture.txt", "actor-001\n")
        self.git("add", "scripts/privacy-allowlist.json", "fixture.txt")

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        self.assertEqual(0, result.returncode, "isolated git operation failed")
        return result.stdout

    def write(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def run_guard(self, *args, code=0, markers=None):
        # Drop any marker file of the caller so the tests stay deterministic.
        env = {k: v for k, v in os.environ.items() if k != guard.MARKERS_ENV}
        if markers is not None:
            env[guard.MARKERS_ENV] = str(markers)
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *map(str, args)], capture_output=True, text=True, env=env)
        self.assertEqual(code, result.returncode, "guard returned unexpected status: " + result.stdout + result.stderr)
        self.assertNotIn(SENTINEL, result.stdout + result.stderr)
        self.assertNotIn(MARKER, (result.stdout + result.stderr).lower())
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        return result

    def test_clean_index_and_tracked(self):
        self.run_guard("--staged")
        self.run_guard("--tracked")

    def test_guard_source_is_not_a_binary_diff_marker(self):
        self.write("scripts/publication_guard.py", SCRIPT.read_text())
        self.git("add", "scripts/publication_guard.py")
        self.run_guard("--staged")

    def test_real_binary_diff_fails(self):
        p = self.root / "fixture.bin"
        p.write_bytes(bytes([0, 1, 2, 255]))
        self.git("add", "fixture.bin")
        result = self.run_guard("--staged", code=1)
        self.assertIn('"binary-diff"', result.stdout)

    def test_partial_staging_uses_index_bytes(self):
        self.write("fixture.txt", SENTINEL)
        self.git("add", "fixture.txt")
        self.write("fixture.txt", "actor-001\n")
        self.run_guard("--staged", code=1)
        self.run_guard("--tracked", code=1)

    def test_unstaged_tracked_secret(self):
        self.write("fixture.txt", SENTINEL)
        self.run_guard("--tracked", code=1)
        self.run_guard("--staged")

    def test_full_blob_not_only_changed_hunk(self):
        self.write("fixture.txt", SENTINEL + "\n" + "actor-001\n" * 100)
        self.git("add", "fixture.txt")
        self.git("update-ref", "HEAD", self.git("-c", "user.name=actor-001", "-c", "user.email=actor-001", "-c", "commit.gpgsign=false", "commit-tree", self.git("write-tree").decode().strip(), "-m", "Synthetic base").decode().strip())
        self.write("fixture.txt", SENTINEL + "\n" + "actor-001\n" * 99 + "actor-002\n")
        self.git("add", "fixture.txt")
        self.assertNotIn(SENTINEL.encode(), guard.staged_patch(self.root))
        self.run_guard("--staged", code=1)

    def test_removed_content_is_checked(self):
        self.write("fixture.txt", SENTINEL)
        self.git("add", "fixture.txt")
        tree = self.git("write-tree").decode().strip()
        oid = self.git("-c", "user.name=actor-001", "-c", "user.email=actor-001", "-c", "commit.gpgsign=false", "commit-tree", tree, "-m", "Synthetic base").decode().strip()
        self.git("update-ref", "HEAD", oid)
        self.write("fixture.txt", "actor-001\n")
        self.git("add", "fixture.txt")
        self.run_guard("--staged", code=1)

    def test_candidate_full_content_and_no_allowlisting(self):
        p = self.write("issue.md", "actor-001\n" * 100 + SENTINEL)
        self.run_guard("--candidate", p, code=1)

    def test_symlink_and_missing_candidate_fail(self):
        p = self.root / "link.txt"
        p.symlink_to(self.root / "fixture.txt")
        self.run_guard("--candidate", p, code=1)
        self.run_guard("--candidate", self.root / "absent.txt", code=2)

    def test_symlinked_candidate_parent_fails(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "fixture.txt").write_text("actor-001")
        link = self.root / "linked"
        link.symlink_to(outside, target_is_directory=True)
        self.run_guard("--candidate", link / "fixture.txt", code=1)
        self.run_guard("--candidate", link / ".." / "repo" / "fixture.txt", code=1)

    def test_symlink_policy_and_review_parent_fail(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "policy.json").write_text("[]")
        policy = self.root / guard.POLICY
        policy.unlink()
        policy.symlink_to(outside / "policy.json")
        self.run_guard("--tracked", code=2)
        link = Path(self.temp.name) / "linked"
        link.symlink_to(outside, target_is_directory=True)
        self.run_guard("--write-review", link / "review.json", code=2)

    def test_cli_argument_error_never_echoes_arguments(self):
        result = self.run_guard("--unknown-option", SENTINEL, code=2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("--unknown-option", result.stderr)

    def test_deep_json_never_emits_traceback(self):
        p = self.write("review.json", "[" * 2000 + "]" * 2000)
        result = self.run_guard("--verify-review", p, code=2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("publication_guard.py", result.stderr)

    def test_candidate_config_and_svg_cli_fail(self):
        for name in [".netrc", ".npmrc", "fixture.svg"]:
            p = self.write(name, "actor-001")
            self.run_guard("--candidate", p, code=1)

    def test_unsafe_filename_is_not_echoed(self):
        name = SENTINEL + ".txt"
        self.write(name, "actor-001")
        self.git("add", "--", name)
        self.run_guard("--staged", code=1)

    def test_index_policy_cannot_be_replaced_by_working_policy(self):
        self.write(guard.POLICY, '{}')
        self.git("add", guard.POLICY)
        self.write(guard.POLICY, '[]')
        self.run_guard("--staged", code=2)

    def test_stale_allowlist(self):
        entry = ContentTests().entry("unit-001")
        self.write(guard.POLICY, json.dumps([entry]))
        self.git("add", guard.POLICY)
        self.run_guard("--staged", code=1)

    def test_exact_exception_works_in_index_and_added_patch(self):
        line = "".join(chr(n) for n in range(65, 91)) + "".join(chr(n) for n in range(97, 123))
        entry = ContentTests().entry(line)
        self.write("fixture.txt", line)
        self.write(guard.POLICY, json.dumps([entry]))
        self.git("add", "fixture.txt", guard.POLICY)
        self.run_guard("--staged")
        self.run_guard("--tracked")

    def test_relative_candidate_path_hygiene(self):
        p = self.write("logs/capture.txt", "actor-001")
        self.run_guard("--candidate", p, code=0)
        # An absolute draft path keeps its source directory names private.
        # Check the complete relative publication path.
        result = subprocess.run([sys.executable, str(SCRIPT), "--candidate", "logs/capture.txt"], cwd=self.root, capture_output=True)
        self.assertEqual(1, result.returncode)

    def test_ignored_tracked_file_still_checked(self):
        self.write(".gitignore", "fixture.txt\n")
        self.write("fixture.txt", SENTINEL)
        self.run_guard("--tracked", code=1)

    def test_candidate_utf8_error_is_sanitized(self):
        p = self.root / "fixture.bin"
        p.write_bytes(bytes([255, 254]))
        self.run_guard("--candidate", p, code=1)

    def test_review_rejects_numeric_checkboxes(self):
        receipt = Path(self.temp.name) / "review.json"
        self.run_guard("--write-review", receipt)
        record = json.loads(receipt.read_text())
        record["checks"] = dict.fromkeys(guard.CHECKLIST, 1)
        receipt.write_text(json.dumps(record))
        self.run_guard("--verify-review", receipt, code=2)

    def test_review_missing_incomplete_complete_stale(self):
        receipt = Path(self.temp.name) / "review.json"
        self.run_guard("--verify-review", receipt, code=2)
        self.run_guard("--write-review", receipt)
        self.run_guard("--verify-review", receipt, code=2)
        record = json.loads(receipt.read_text())
        record["checks"] = dict.fromkeys(guard.CHECKLIST, True)
        receipt.write_text(json.dumps(record))
        self.run_guard("--verify-review", receipt)
        self.write("fixture.txt", "actor-002\n")
        self.git("add", "fixture.txt")
        self.run_guard("--verify-review", receipt, code=2)

    def marker_file(self, text=MARKER_FILE_TEXT, name="markers.txt"):
        path = Path(self.temp.name) / name
        path.write_text(text)
        return path

    def commit(self, message, parent=None, name="actor-001", email="actor-001"):
        args = ["-c", "user.name=" + name, "-c", "user.email=" + email, "-c", "commit.gpgsign=false", "commit-tree", self.git("write-tree").decode().strip(), "-m", message]
        if parent:
            args += ["-p", parent]
        return self.git(*args).decode().strip()

    def test_markers_are_skipped_when_unset(self):
        self.write("fixture.txt", "uses " + MARKER + "\n")
        self.git("add", "fixture.txt")
        self.run_guard("--tracked")
        self.run_guard("--staged")

    def test_markers_found_in_tracked_staged_and_candidate(self):
        markers = self.marker_file()
        self.write("fixture.txt", "uses " + MARKER.upper() + "\n")
        self.git("add", "fixture.txt")
        for mode in ("--tracked", "--staged"):
            result = self.run_guard(mode, code=1, markers=markers)
            self.assertIn('"operational-marker"', result.stdout)
        draft = Path(self.temp.name) / "pr-text.md"
        draft.write_text("Mentions marker tool 002 once.\n")
        self.run_guard("--candidate", draft, code=1, markers=markers)
        self.run_guard("--candidate", draft)
        clean = Path(self.temp.name) / "clean.md"
        clean.write_text("actor-001\n")
        self.run_guard("--candidate", clean, markers=markers)

    def test_marker_in_filename_is_found(self):
        self.write(MARKER + ".txt", "actor-001")
        self.git("add", "--", MARKER + ".txt")
        self.run_guard("--staged", code=1, markers=self.marker_file())

    def test_require_markers(self):
        self.run_guard("--tracked", "--require-markers", code=2)
        self.run_guard("--staged", "--require-markers", code=2)
        self.run_guard("--commit-messages", "HEAD", "--require-markers", code=2)
        clean = self.write("clean.md", "actor-001\n")
        self.run_guard("--candidate", clean, "--require-markers", code=2)
        self.run_guard("--tracked", "--require-markers", markers=self.marker_file())

    def test_bad_marker_files_fail_with_status_two(self):
        self.run_guard("--tracked", code=2, markers=Path(self.temp.name) / "absent.txt")
        self.run_guard("--tracked", code=2, markers=self.marker_file("\n  \n", "empty.txt"))
        self.run_guard("--tracked", code=2, markers=self.marker_file("ab\n", "short.txt"))
        inside = self.root / "markers.txt"
        inside.write_text(MARKER + "\n")
        self.run_guard("--tracked", code=2, markers=inside)

    def test_marker_exception_in_index_and_stale_handling(self):
        line = "uses " + MARKER
        entry = {**ContentTests().entry(line), "rule": "operational-marker"}
        self.write("fixture.txt", line)
        self.write(guard.POLICY, json.dumps([entry]))
        self.git("add", "fixture.txt", guard.POLICY)
        markers = self.marker_file()
        self.run_guard("--staged", markers=markers)
        self.run_guard("--tracked", markers=markers)
        # Without the marker file the entry cannot match and is not stale.
        self.run_guard("--staged")
        self.run_guard("--tracked")
        self.write("fixture.txt", line + " changed")
        self.git("add", "fixture.txt")
        self.run_guard("--staged", code=1, markers=markers)
        # An exception for one line does not cover a candidate scan.
        self.write("fixture.txt", line)
        self.run_guard("--candidate", self.root / "fixture.txt", code=1, markers=markers)

    def test_commit_messages_scan_message_and_metadata(self):
        markers = self.marker_file()
        base = self.commit("Synthetic base")
        clean = self.commit("Synthetic change", base)
        self.run_guard("--commit-messages", base + ".." + clean, markers=markers)
        self.run_guard("--commit-messages", base + ".." + clean)
        for kwargs in [
            {"message": "Uses " + MARKER},
            {"message": "Synthetic change\n\nbody mentions Marker Tool 002"},
            {"message": "Synthetic change", "name": MARKER},
            {"message": "Synthetic change", "email": MARKER},
        ]:
            bad = self.commit(parent=base, **kwargs)
            result = self.run_guard("--commit-messages", base + ".." + bad, code=1, markers=markers)
            self.assertIn('"operational-marker"', result.stdout)
            self.run_guard("--commit-messages", base + ".." + bad)

    def test_commit_messages_apply_all_rules(self):
        base = self.commit("Synthetic base")
        for kwargs in [
            {"message": "Token " + SENTINEL},
            {"message": "Synthetic change", "name": SENTINEL},
            {"message": "Contact actor-001" + "@" + "invalid.test"},
            {"message": "Synthetic change", "email": "actor-001" + "@" + "invalid.test"},
        ]:
            bad = self.commit(parent=base, **kwargs)
            self.run_guard("--commit-messages", base + ".." + bad, code=1)

    def test_commit_messages_accept_public_noreply_metadata_only(self):
        base = self.commit("Synthetic base")
        noreply = "1234+actor-001" + "@" + "users.noreply.github.com"
        ok = self.commit("Synthetic change", base, email=noreply)
        self.run_guard("--commit-messages", base + ".." + ok)
        bad = self.commit("Synthetic change", base, email=noreply + ".invalid.test")
        self.run_guard("--commit-messages", base + ".." + bad, code=1)
        body = self.commit("Co-author " + noreply, base)
        self.run_guard("--commit-messages", base + ".." + body, code=1)

    def test_noreply_exemption_covers_email_rule_only(self):
        markers = self.marker_file()
        base = self.commit("Synthetic base")
        hidden = "1234+" + MARKER + "@" + "users.noreply.github.com"
        bad = self.commit("Synthetic change", base, email=hidden)
        result = self.run_guard("--commit-messages", base + ".." + bad, code=1, markers=markers)
        self.assertIn('"operational-marker"', result.stdout)
        self.assertNotIn('"email"', result.stdout)
        self.run_guard("--commit-messages", base + ".." + bad)

    def test_commit_messages_reject_bad_ranges(self):
        self.commit("Synthetic base")
        self.run_guard("--commit-messages", "--all", code=2)
        self.run_guard("--commit-messages", "absent-revision", code=2)
        self.run_guard("--commit-messages", "", code=2)

    def test_review_cannot_be_written_into_checkout(self):
        self.run_guard("--write-review", self.root / "review.json", code=2)


if __name__ == "__main__":
    unittest.main()
