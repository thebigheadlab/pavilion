# Publication safety

Pavilion is public. Review code, tests, issue text, filenames, and attachments
before any publication. These offline checks reduce mistakes; they cannot
guarantee complete prevention. No hooks are installed and no repository
protections are changed by this foundation.

## What the guard checks

Run from the repository root with Python 3.10 or newer and Git. There are no
third-party dependencies or network calls in the guard or its tests.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/publication_guard.py --tracked
python3 scripts/publication_guard.py --candidate issue-title.txt --candidate issue-body.md
```

`--candidate` reads each complete file, including unchanged text. It accepts
repeated file arguments and never applies an allowlist. Pass every proposed
publication file, title, body, or attachment. It does not walk directories.
Absolute input locations stay private; only their publication basenames are
checked. Review the destination paths separately. Relative candidate names are
also subject to path hygiene. Do not put candidate issue drafts in the checkout.

`--tracked` checks every stage-zero index blob and every existing working copy
of those files. It does not trust ignore rules to exclude tracked content.
Deleted working copies still have their index bytes checked. Untracked files
need explicit candidate checks before staging. The initial repository license
and README are included without exclusions.

Rules detect common credential formats, authentication headers, private keys,
credential assignments, contact syntax, private filesystem paths and networks,
private planning/message links and IDs, invisible controls, and suspicious token
entropy. Paths associated with local configuration, logs, captures, and dumps
fail. Known archive, database, media, and log extensions fail even if their
content looks textual. Non-UTF-8 files, control bytes, files over 2 MiB,
symlinks, and submodules fail closed. New media needs a reviewed validation
process before extending this policy. Never use copied user media as a fixture.

Credential configuration files such as `.netrc` and `.npmrc` are prohibited by
name, even with harmless-looking content. SVG files and recognizable inline SVG
are rejected as media requiring separate validation. Symlink checks include
lexical parent directories before reading candidates, working files, policies,
and review records. This is a pre-read check, not a race-proof filesystem sandbox.

Diagnostics contain ordinal item IDs, line numbers, rule IDs, and counts. They
omit filenames, matched values, raw exceptions, and Git output. Exit status is
0 for pass, 1 for findings, and 2 for an input, policy, or review failure.
Invalid CLI arguments and unexpected input errors also return sanitized status
2 without argument echoes or Python tracebacks.
Resolve an item locally by following the supplied candidate order or Git index
order. Do not upload raw debugging output to an issue.

## Exact staged review

Stage named files only after candidate and tracked checks pass. Use these
commands, substituting a review file outside the repository:

```sh
python3 scripts/publication_guard.py --staged
git diff --cached --check
python3 scripts/publication_guard.py --write-review "$REVIEW_FILE"
git -c core.pager=cat diff --cached --no-ext-diff --no-textconv --no-color --binary --no-renames
python3 scripts/publication_guard.py --verify-review "$REVIEW_FILE"
```

The diff command is for private local inspection. Never paste its output into
a public artifact. `--staged` scans complete index blobs, then removed/context
lines and metadata in the patch. Added text is already covered by full blobs.
Binary diffs fail. This catches partial staging and removed sensitive text that
would otherwise appear in a public diff. A staged allowlist must exist and is
read from the index, independent of its working copy.

The review writer creates an exclusive JSON template. It never overwrites an
existing record. After reading every hunk and filename, a human reviewer sets
each named check to the JSON boolean `true`. The verifier checks the full index
manifest, exact diff, and executing guard digest. Index, policy, or guard edits
invalidate the record. False, absent, malformed, and stale records fail. This is
an auditable attestation, not proof that a human read the diff. Do not automate
setting its checkboxes. Repeat all checks immediately before publication.

Commit messages, author metadata, PR text, issue text, and other artifacts need
their own full candidate check and human review. Use bot commit metadata for
any later authorized commit. This foundation does not commit or publish code.

## Allowlist rules

`scripts/privacy-allowlist.json` starts empty. Only `high-entropy` may be
excepted. Each entry must contain exactly these keys:

| Key | Requirement |
| --- | --- |
| `path` | Exact repository-relative path, no parent traversal or wildcards |
| `rule` | `high-entropy` only |
| `line_sha256` | SHA-256 of the exact UTF-8 line without its newline |
| `reason` | At least 20 characters explaining a demonstrably public, nonsecret value |
| `expires` | ISO date from today through the next 90 days |

Do not store the matched value in the entry. Review additions as carefully as
code. Duplicate, expired, malformed, broad, and unused entries fail. A path or
line change invalidates the exception. All other rules still apply to that line.
There are no inline suppression markers, directory bypasses, or candidate
exceptions. A safe exception cannot make deleted/context content publishable;
the patch scan deliberately applies no exceptions to that content.

## Proposed CI gate

Future wiring should run the sentinel suite, `--tracked`, `--staged`, and
`git diff --cached --check` after checkout with a read-only token. On a clean
checkout, `--staged` checks the full index even when its patch is empty. CI does
not replace the local staged-review receipt or review candidate issue bodies.

Use ordinary `pull_request` and `push` triggers, minimal `contents: read`, no
secrets, no uploaded logs or artifacts, and no `pull_request_target` execution
of untrusted code. Pin any checkout action to a reviewed immutable commit and
disable persisted credentials. Use installed Python rather than downloading
scanner dependencies. Require the gate only through a separately authorized
repository-protection change. No active workflow is added in this change.

CI must not dump failed source or the raw diff. A future outgoing-commit check
should scan each commit's tree and candidate metadata, not only the final tree.
Run an approved history scanner before an initial or rewritten history publish.
Do not treat a clean final tree as evidence that intermediate commits are safe.

## Blind spots and incident handling

This scanner is heuristic. It can miss names, identity context, unstructured
private text, novel token formats, split or encoded secrets, short credentials,
obfuscated paths, Unicode tricks, and sensitive meaning in ordinary prose.
False positives remain possible. A deliberately encoded payload can evade
content patterns. A renamed or mislabeled file needs human review even when it
passes. Generic neutral IDs do not make copied user content synthetic.

The scanner does not inspect Git history, commit metadata, ignored/unselected
untracked files, remote branches, Git LFS objects, external URLs, dependency
contents, or GitHub attachments. It does not make publication atomic against
another process editing the index. Stop concurrent writers while reviewing and
publishing. An editor or local process can forge a review receipt; the receipt
does not establish trusted identity or cryptographic authorization.

If a finding may contain real private data, stop publication. Keep evidence
private and report only the rule/category and blocked scope. Rotate exposed
credentials through the approved owner process. Removing text from the current
tree does not remove it from history or remote caches. History remediation and
public disclosure need explicit owner direction. Never test with a real secret.
