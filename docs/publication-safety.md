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

Scan complete commit messages, PR text, issue text, and other candidate artifacts separately.
Scan complete commit author metadata as a separate candidate artifact.
Obtain human review of those artifacts and commit author metadata.
Use bot commit metadata for an authorized commit.
The guard does not commit or publish code.

## Limit allowlist exceptions

`scripts/privacy-allowlist.json` starts empty.
Only the `high-entropy` rule permits an exception.
Each entry must contain exactly these keys:

| Key | Requirement |
| --- | --- |
| `path` | Use an exact repository-relative path. Do not use parent traversal or wildcards. |
| `rule` | Use `high-entropy` only. |
| `line_sha256` | Use the SHA-256 digest of the exact UTF-8 line without its newline. |
| `reason` | Use at least 20 characters to explain why the value is demonstrably public and contains no secret. |
| `expires` | Use an ISO date from today through the next 90 days. |

Do not store the matched value in the entry.
Review an exception as carefully as code.
Duplicate, expired, malformed, broad, and unused entries fail.
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

The scanner does not inspect Git history or commit metadata.
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
