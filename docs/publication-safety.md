# Publication safety

Pavilion is public.
Before publication, review code, tests, issue text, filenames, and attachments.
The offline checks reduce mistakes.
They cannot guarantee complete prevention.
This foundation installs no hooks and changes no repository protections.

Follow the [repository instructions](../AGENTS.md).
Use the terms in the [glossary](glossary.md).

## Run the content checks

Run these commands from the repository root with Python 3.10 or newer and Git.
The guard and tests need no third-party dependencies or network calls.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/publication_guard.py --tracked
python3 scripts/publication_guard.py --candidate issue-title.txt --candidate issue-body.md
```

Also complete the [operational marker checks](#check-operational-markers) before publication.

`--candidate` reads each complete file, including unchanged text.
Repeat the argument for each file.
Candidate scans never use the allowlist.
Supply every proposed file, title, body, or attachment.
The guard does not walk directories.

For an absolute input path, the guard checks only the publication basename.
The guard keeps the source directory path private.
Review the destination paths separately.
For a relative candidate path, the guard also checks the directory names.
Keep issue drafts outside the checkout.

`--tracked` checks each stage-zero index blob and each existing working copy.
Ignore rules do not exclude tracked content.
If you delete a working copy, the guard still checks its index bytes.
Scan untracked files as candidates before you stage them.
The checks include the initial license and README without exclusions.

## Check operational markers

The `operational-marker` rule finds text that the owner keeps out of public content.
The owner keeps the list of markers private and outside the repository.
Never commit the marker file, quote its values, or put them in a test, issue, or PR.

The marker file holds one literal per line.
The match ignores case.
A marker must have at least 3 characters.
Blank lines are ignored.
The rule applies to file contents, filenames, candidate files, and commit metadata.

Complete these steps before you publish:

1. Set `PAVILION_PRIVATE_MARKERS` to the marker file.
   The file must be outside the repository.
2. Scan code and docs. Add `--require-markers` so that a missing file is an error:
   `python3 scripts/publication_guard.py --tracked --require-markers`
   and `python3 scripts/publication_guard.py --staged --require-markers`.
3. Save the PR title and body in files outside the repository.
   Scan them as candidate files:
   `python3 scripts/publication_guard.py --candidate pr-title.txt --candidate pr-body.md --require-markers`.
4. Scan each outgoing commit message and its author and committer lines:
   `python3 scripts/publication_guard.py --commit-messages origin/main..HEAD --require-markers`.
   Use the revision range of the commits that you will publish.

Without `PAVILION_PRIVATE_MARKERS`, the guard skips the rule.
With `--require-markers`, a missing, unreadable, empty, or in-repository marker file is an error with exit status 2.
A skipped rule is not a pass.
The diagnostics show only item numbers, line numbers, and rule IDs.

The commit message scan applies all rules.
It reads the raw commit object.
It accepts the public no-reply email form of the bot account in the author and committer lines only.
It reports any other email address.

A legitimate product reference can need an exception.
Add an exact `operational-marker` entry to `scripts/privacy-allowlist.json`.
Review it as carefully as code.
The `--staged` patch scan applies no exceptions to removed or context lines.
A change that removes marked text still shows that text in the diff.
Obtain owner direction before you publish such a change.

## Understand the rules and results

The guard detects common credential formats, authentication headers, private keys, and credential assignments.
It also detects contact syntax, private paths and networks, private planning links, message links and IDs, invisible controls, and suspicious entropy.
Paths for local configuration, logs, captures, and dumps fail the checks.
Known archive, database, media, and log extensions fail even when the content looks like text.
Non-UTF-8 files, control bytes, files over 2 MiB, symlinks, and submodules also fail.

Before you extend the policy for new media, obtain review of a validation process.
Never copy user media into a fixture.
The guard rejects credential configuration names such as `.netrc` and `.npmrc`, even with harmless content.
It rejects SVG files and recognizable inline SVG as media that needs separate validation.

Before a file read, the guard checks lexical parent directories for symlinks.
These checks cover candidates, working files, policies, and review records.
They do not prevent filesystem races.

Diagnostics contain item numbers, line numbers, rule IDs, and counts.
They omit filenames, matched values, raw exceptions, and Git output.
The exit status is 0 for a pass, 1 for findings, and 2 for an input, policy, or review failure.
Invalid command arguments and unexpected input errors return status 2.
The guard does not echo arguments or Python tracebacks for these errors.

To find an item locally, use the candidate order or Git index order.
Do not upload raw diagnostic output to an issue.

## Review the exact staged content

After the candidate and tracked checks pass, stage named files only.
Set `REVIEW_FILE` to a new file outside the repository.
Then run these commands:

```sh
python3 scripts/publication_guard.py --staged
git diff --cached --check
python3 scripts/publication_guard.py --write-review "$REVIEW_FILE"
git -c core.pager=cat diff --cached --no-ext-diff --no-textconv --no-color --binary --no-renames
python3 scripts/publication_guard.py --verify-review "$REVIEW_FILE"
```

Use the diff command only for private local review.
Never put its output in a public artifact.
Before the final command, complete the review record as described below.

`--staged` scans complete index blobs.
It also scans removed lines, context lines, and metadata in the patch.
The complete blobs already cover added text.
Binary diffs fail.
These checks cover partial staging and private text removed from a file.
Removed text can still appear in a public diff.

The staged allowlist must exist in the index.
The guard reads that version independently of its working copy.

The review writer creates a new JSON template.
It never overwrites an existing record.
A human reviewer must read every hunk and filename.
The reviewer then sets each named check to the JSON boolean `true`.
Do not automate setting these checks.

The verifier checks the complete index manifest, the exact diff, and the running guard's digest.
Changes to the index, policy, or guard invalidate the record.
False, absent, malformed, and stale records fail.
The record documents review decisions.
It does not prove that a human read the diff.
Repeat all checks immediately before publication.

Scan complete PR text, issue text, and other candidate artifacts separately.
Scan commit messages and commit author metadata with `--commit-messages`.
Obtain human review of those artifacts and commit author metadata.
Use bot commit metadata for an authorized commit.
The guard does not commit or publish code.

## Limit allowlist exceptions

`scripts/privacy-allowlist.json` holds only reviewed exact-line entries.
Only the `high-entropy` and `operational-marker` rules permit an exception.
Each entry must contain exactly these keys:

| Key | Requirement |
| --- | --- |
| `path` | Use an exact repository-relative path. Do not use parent traversal or wildcards. |
| `rule` | Use `high-entropy` or `operational-marker`. |
| `line_sha256` | Use the SHA-256 digest of the exact UTF-8 line without its newline. |
| `reason` | Use at least 20 characters to explain why the value is demonstrably public and contains no secret. |
| `expires` | Use an ISO date from today through the next 90 days. |

Do not store the matched value in the entry.
Review an exception as carefully as code.
Duplicate, expired, malformed, broad, and unused entries fail.
An `operational-marker` entry counts as unused only when the marker file is set.
The reason of an entry must not contain a marker.
A path or line change invalidates the exception.
All other rules still apply to that line.

The guard has no inline suppression markers, directory exclusions, or candidate exceptions.
The patch scan applies no exceptions to removed or context content.
An exception cannot make that content safe to publish.

<a id="proposed-ci-gate"></a>

## Proposed CI checks

No active workflow is part of this foundation.
A future CI workflow should run the sentinel tests, `--tracked`, `--staged`, and `git diff --cached --check` after checkout.
Use a read-only token.
On a clean checkout, `--staged` checks the complete index even when the patch is empty.
CI does not replace the local review record or review candidate issue bodies.

Use ordinary `pull_request` and `push` triggers.
Give the workflow only `contents: read` permission.
Do not supply secrets or upload logs or artifacts.
Do not use `pull_request_target` to run untrusted code.
Pin the checkout action to a reviewed immutable commit.
Disable persisted credentials.
Use installed Python instead of downloading scanner dependencies.
A change to require these checks needs separate authorization for repository protections.

CI must not print failed source or raw diffs.
A future check before a push should scan each outgoing commit's tree and candidate metadata.
Checking only the final tree is insufficient.
Before you publish initial or rewritten history, run an approved history scanner.
A clean final tree does not show that intermediate commits are safe.

## Understand the blind spots

The scanner uses heuristic rules.
It can miss names, identity context, unstructured private text, novel token formats, and short credentials.
It can also miss split or encoded secrets, hidden paths, Unicode tricks, and private meaning in ordinary prose.
False positives are possible.
A deliberately encoded payload can evade the patterns.
Review renamed or mislabeled files even when the checks pass.
Neutral IDs do not make copied user content synthetic.

The scanner inspects Git history only through `--commit-messages`, only for the range that you give, and only for commit messages and metadata, not past file contents.
It does not inspect ignored or unselected untracked files, remote branches, Git LFS objects, external URLs, dependencies, or GitHub attachments.
It cannot stop another process from changing the index during publication.
Stop concurrent writers during review and publication.

An editor or local process can forge a review record.
The record does not prove a trusted identity or cryptographic authorization.

## Handle a possible disclosure

If a finding can contain real private data, stop publication.
Keep the evidence private.
Report only the rule or category and the blocked work.
Rotate exposed credentials through the approved owner process.
Removing text from the current tree does not remove it from history or remote caches.
Obtain explicit owner direction for history repair or public disclosure.
Never use a real secret in a test.
