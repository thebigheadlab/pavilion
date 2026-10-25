#!/usr/bin/env python3
"""Check content before publication. Diagnostics omit matched content and paths."""

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys


MAX_BYTES = 2 * 1024 * 1024
POLICY = "scripts/privacy-allowlist.json"
MARKERS_ENV = "PAVILION_PRIVATE_MARKERS"
MARKER_RULE = "operational-marker"
EXCEPTION_RULES = {"high-entropy", MARKER_RULE}
NOREPLY = re.compile(rb"<(?:\d+\+[\w-]+@users\.noreply\.github\.com|noreply@github\.com)>")
RULES = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "private-path": re.compile(r"(?:/(?:home|Users|root)/[^\s\"'<>]+|[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\"'<>]+)"),
    "private-network": re.compile(r"\b(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+)\b|\b[\w.-]+\.ts\.net\b"),
    "private-link": re.compile(r"https?://[^\s]*(?:slack\.com/archives|notion\.so/|notion\.site/)", re.I),
    "secret-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,})\b"),
    "private-key": re.compile(r"-----BEGIN (?:[A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----"),
    "auth-header": re.compile(r"\b(?:Authorization\s*:\s*(?:Bearer|Basic)\s+\S+|https?://[^\s/@:]+:[^\s/@]+@)", re.I),
    "credential-assignment": re.compile(r"\b(?:password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret)\b[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_+/=-]{8,}", re.I),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "contact-number": re.compile(r"(?<![\w.])\+\d[\d ()-]{9,}\d(?!\w)"),
    "private-message-id": re.compile(r"\b[UCDG](?=[A-Z0-9]{0,9}[0-9])[A-Z0-9]{10}\b|\b\d{10}\.\d{6}\b"),
    "invisible-control": re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]"),
    "synthetic-sentinel": re.compile("PAVILION_" + "TEST_SECRET_[A-Z0-9_]+"),
}
OPAQUE_SUFFIXES = {".log", ".jsonl", ".har", ".pcap", ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".zip", ".gz", ".tar", ".7z", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".svg", ".svgz"}
PRIVATE_PARTS = {".env", ".ssh", ".aws", ".config", ".git", ".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials", ".gitconfig", ".docker", ".kube", ".gnupg", "logs", "captures", "dumps", "node_modules", "__pycache__"}
CHECKLIST = ["all_hunks_and_filenames_reviewed", "only_synthetic_data", "no_private_content_or_host_config", "publication_scope_confirmed"]


class GuardError(Exception):
    pass


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # The default argparse error prints untrusted arguments.
        raise GuardError("invalid command arguments")


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise GuardError("git operation failed; inspect locally without publishing raw output")
    return result.stdout


def entropy(value):
    counts = Counter(value)
    return -sum((n / len(value)) * math.log2(n / len(value)) for n in counts.values())


def load_markers_from(lines):
    markers = []
    for line in lines:
        marker = line.strip().lower()
        if marker and marker not in markers:
            if len(marker) < 3:
                raise GuardError("private marker too short")
            markers.append(marker)
    if not markers:
        raise GuardError("private marker file has no markers")
    return tuple(markers)


def load_markers(required, forbidden_roots=()):
    # The marker file is private. Report no value, path, or content.
    value = os.environ.get(MARKERS_ENV)
    if not value:
        if required:
            raise GuardError("private marker file required")
        return ()
    path = Path(value)
    if not path.is_file():
        raise GuardError("private marker file unreadable")
    resolved = path.resolve()
    if any(resolved.is_relative_to(root) for root in forbidden_roots):
        raise GuardError("private marker file must be outside the repository")
    if resolved.stat().st_size > MAX_BYTES:
        raise GuardError("private marker file too large")
    return load_markers_from(resolved.read_text(encoding="utf-8").splitlines())


def line_rules(line, markers=()):
    found = [name for name, pattern in RULES.items() if pattern.search(line)]
    lowered = line.lower()
    if any(marker in lowered for marker in markers):
        found.append(MARKER_RULE)
    for token in re.findall(r"[A-Za-z0-9_+/=-]{32,}", line):
        if not re.fullmatch(r"[0-9a-fA-F]+", token) and entropy(token) >= 4.5:
            found.append("high-entropy")
            break
    return found


def path_rules(name):
    parts = PurePosixPath(name.replace("\\", "/")).parts
    if any(p in PRIVATE_PARTS or p.startswith(".env.") for p in parts):
        return ["private-file"]
    if PurePosixPath(name).suffix.lower() in OPAQUE_SUFFIXES:
        return ["opaque-or-log-file"]
    return []


def load_policy(data, markers=()):
    try:
        entries = json.loads(data)
        if not isinstance(entries, list):
            raise ValueError()
        for entry in entries:
            if set(entry) != {"path", "rule", "line_sha256", "reason", "expires"}:
                raise ValueError()
            p = PurePosixPath(entry["path"])
            if p.is_absolute() or ".." in p.parts or any(c in entry["path"] for c in "*?[]\\\n\r"):
                raise ValueError()
            if entry["rule"] not in EXCEPTION_RULES or not re.fullmatch(r"[a-f0-9]{64}", entry["line_sha256"]):
                raise ValueError()
            days = (date.fromisoformat(entry["expires"]) - date.today()).days
            if not 0 <= days <= 90 or not isinstance(entry["reason"], str) or len(entry["reason"].strip()) < 20:
                raise ValueError()
            if line_rules(entry["reason"], markers):
                raise ValueError()
        if len({(e["path"], e["rule"], e["line_sha256"]) for e in entries}) != len(entries):
            raise ValueError()
        return entries
    except (ValueError, TypeError, KeyError):
        raise GuardError("invalid allowlist; exact line entries with reason and expiry required") from None


class Scanner:
    def __init__(self, entries=(), markers=()):
        self.entries = entries
        self.markers = markers
        self.used = set()
        self.findings = []
        self.count = 0

    def add(self, item, rule, line=0):
        # Report only item numbers and rule IDs.
        self.findings.append({"item": item, "line": line, "rule": rule})

    def scan(self, name, data, mode="100644", allow=True):
        self.count += 1
        item = self.count
        for rule in path_rules(name) + line_rules(name, self.markers):
            self.add(item, rule)
        if mode not in ("100644", "100755"):
            self.add(item, "symlink-or-submodule")
            return
        if len(data) > MAX_BYTES:
            self.add(item, "oversize")
            return
        try:
            content = data.decode("utf-8")
            if any(ord(c) < 32 and c not in "\t\n\r" for c in content):
                raise UnicodeError()
        except UnicodeError:
            self.add(item, "binary-or-encoding")
            return
        if re.search(r"<svg(?:\s|>)", content, re.I):
            self.add(item, "opaque-or-log-file")
            return
        for number, line in enumerate(content.splitlines(), 1):
            for rule in line_rules(line, self.markers):
                digest = hashlib.sha256(line.encode()).hexdigest()
                matches = [i for i, e in enumerate(self.entries) if allow and e["path"] == name and e["rule"] == rule and e["line_sha256"] == digest]
                if matches:
                    self.used.update(matches)
                else:
                    self.add(item, rule, number)

    def finish(self, require_used=False):
        # Marker entries cannot match while the marker file is absent.
        needed = {i for i, e in enumerate(self.entries) if e["rule"] != MARKER_RULE or self.markers}
        if require_used and not needed <= self.used:
            self.add(0, "stale-allowlist")
        print(json.dumps({"result": "FAIL" if self.findings else "PASS", "items": self.count, "finding_count": len(self.findings), "findings": self.findings[:100]}, sort_keys=True))
        return 1 if self.findings else 0


def index_entries(root):
    entries = []
    for record in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        meta, name = record.split(b"\t", 1)
        mode, oid, stage = meta.decode().split()
        if stage != "0":
            raise GuardError("unmerged index; resolve locally before review")
        entries.append((os.fsdecode(name), mode, oid))
    return entries


def has_symlink(path):
    # Before a file read, check lexical parents, including paths with '..'.
    return any(part.is_symlink() for part in [path, *path.absolute().parents])


def working_bytes(path):
    if has_symlink(path):
        return b"", "120000"
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        return b"", "120000"
    if st.st_size > MAX_BYTES:
        return b"x" * (MAX_BYTES + 1), "100644"
    return path.read_bytes(), "100755" if st.st_mode & stat.S_IXUSR else "100644"


def regular_bytes(path):
    data, mode = working_bytes(path)
    if mode not in ("100644", "100755"):
        raise GuardError("regular nonsymlink file required")
    return data


def staged_policy(root, entries, markers=()):
    for name, mode, oid in entries:
        if name == POLICY and mode == "100644":
            return load_policy(git(root, "cat-file", "blob", oid), markers)
    raise GuardError("stage the allowlist file before staged checks")


def staged_patch(root):
    return git(root, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--no-color", "--binary", "--no-renames", "--src-prefix=a/", "--dst-prefix=b/")


def staged_scan(root, markers=()):
    entries = index_entries(root)
    scanner = Scanner(staged_policy(root, entries, markers), markers)
    for name, mode, oid in entries:
        scanner.scan(name, git(root, "cat-file", "blob", oid) if mode in ("100644", "100755") else b"", mode)
    # Full index blobs cover added text. Also check the rest of the patch.
    # Removed lines, context, and metadata can expose private content.
    patch = staged_patch(root)
    if any(line == b"GIT binary patch" or line.startswith(b"Binary files ") for line in patch.splitlines()):
        scanner.add(0, "binary-diff")
    remainder = b"\n".join(line for line in patch.splitlines() if not (line.startswith(b"+") and not line.startswith(b"+++")))
    scanner.scan("staged-diff", remainder, allow=False)
    return scanner


def commit_identity_and_message(raw):
    # Parse a commit object. Return the author and committer lines and the message.
    # Skip tree, parent, signature, encoding, and mergetag fields.
    head, sep, body = raw.partition(b"\n\n")
    if not sep:
        raise GuardError("malformed commit object")
    identity, keep, started = [], False, False
    for line in head.split(b"\n"):
        if line.startswith(b" "):
            if not started:
                raise GuardError("malformed commit object")
            if keep:
                identity.append(line)
            continue
        started = True
        keep = line.startswith((b"author ", b"committer "))
        if keep:
            identity.append(line)
    if not any(l.startswith(b"author ") for l in identity) or not any(l.startswith(b"committer ") for l in identity):
        raise GuardError("malformed commit object")
    return identity, body


def commit_scan(root, rev_range, markers=()):
    # Scan the author and committer lines plus the message of each raw commit object.
    if not rev_range or rev_range.startswith("-"):
        raise GuardError("invalid revision range")
    scanner = Scanner(markers=markers)
    for oid in git(root, "rev-list", "--end-of-options", rev_range).split():
        identity, body = commit_identity_and_message(git(root, "cat-file", "commit", oid.decode()))
        # Bot metadata uses the public no-reply address form. Exempt only that form.
        lines = [NOREPLY.sub(b"<>", l) if l.startswith((b"author ", b"committer ")) else l for l in identity]
        scanner.scan("commit-metadata", b"\n".join(lines) + b"\n\n" + body, allow=False)
        # The exemption covers the email rule only. Scan the original metadata for the rest.
        for line in b"\n".join(identity).decode("utf-8", "replace").split("\n"):
            for rule in line_rules(line, markers):
                if rule != "email" and not any(f["item"] == scanner.count and f["rule"] == rule for f in scanner.findings):
                    scanner.add(scanner.count, rule)
    return scanner


def review_digest(root):
    digest = hashlib.sha256()
    for part in [git(root, "ls-files", "--stage", "-z"), staged_patch(root)]:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    # Include the running guard and staged policy in the review digest.
    digest.update(Path(__file__).read_bytes())
    return digest.hexdigest()


def main():
    parser = SafeParser(description=__doc__)
    parser.add_argument("--root", default=".")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tracked", action="store_true")
    group.add_argument("--staged", action="store_true")
    group.add_argument("--candidate", action="append", metavar="FILE")
    group.add_argument("--commit-messages", metavar="REV_RANGE")
    group.add_argument("--write-review", metavar="FILE")
    group.add_argument("--verify-review", metavar="FILE")
    parser.add_argument("--require-markers", action="store_true")
    args = parser.parse_args()
    root_input = Path(args.root)
    if has_symlink(root_input):
        raise GuardError("symlink repository root rejected")
    root = root_input.resolve()
    if args.candidate:
        scanner = Scanner(markers=load_markers(args.require_markers, [root]))
        for value in args.candidate:
            p = Path(value)
            data, mode = working_bytes(p)
            # Keep candidate source directories private. Check only the publication name.
            scanner.scan(p.name if p.is_absolute() else p.as_posix(), data, mode, allow=False)
        return scanner.finish()
    root = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip())
    markers = load_markers(args.require_markers, [root_input.resolve(), root.resolve()])
    if args.commit_messages:
        return commit_scan(root, args.commit_messages, markers).finish()
    if args.tracked:
        scanner = Scanner(load_policy(regular_bytes(root / POLICY), markers), markers)
        for name, mode, oid in index_entries(root):
            scanner.scan(name, git(root, "cat-file", "blob", oid) if mode in ("100644", "100755") else b"", mode)
            p = root / name
            if p.exists() or p.is_symlink():
                data, working_mode = working_bytes(p)
                scanner.scan(name, data, working_mode)
        return scanner.finish(require_used=True)
    scanner = staged_scan(root, markers)
    if scanner.finish(require_used=True):
        return 1
    if args.staged:
        return 0
    digest = review_digest(root)
    if args.write_review:
        target_input = Path(args.write_review)
        if has_symlink(target_input):
            raise GuardError("symlink review location rejected")
        target = target_input.resolve()
        if target.is_relative_to(root):
            raise GuardError("review records must be outside the repository")
        record = {"version": 1, "digest": digest, "checks": dict.fromkeys(CHECKLIST, False)}
        # Create a new file. Do not replace a review record or follow symlinks.
        with target.open("x", encoding="utf-8") as output:
            json.dump(record, output, indent=2)
            output.write("\n")
        print("Review template written. Inspect the complete staged diff locally before marking checks true.")
        return 0
    record = json.loads(regular_bytes(Path(args.verify_review)))
    if set(record) != {"version", "digest", "checks"} or record["version"] != 1 or record["digest"] != digest or not isinstance(record["checks"], dict) or set(record["checks"]) != set(CHECKLIST) or any(value is not True for value in record["checks"].values()):
        raise GuardError("review missing, incomplete, or stale; inspect and attest the exact staged content")
    print("PASS: exact staged review record verified; human judgment remains required")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt):
        # Report unexpected command input or parser errors without raw details.
        # Do not echo arguments or traceback paths.
        print("FAIL: check input, policy, repository state, or review record locally; raw diagnostic withheld", file=sys.stderr)
        sys.exit(2)
