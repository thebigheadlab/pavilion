# Pavilion execution rules

## Public repository boundary

Treat each tracked file, commit, issue, PR, attachment, and build artifact as public.
Use bot credentials for repository operations.
Verify the active account without printing credentials or personal account details.
If bot access is unavailable, stop.
Do not create credentials or change global configuration to continue.

Do not publish personal identities, email addresses, credentials, or private paths.
Do not publish host configuration, private messages, user content, or raw logs.
Keep private plans and transcripts out of the repository and its issues.
Use neutral synthetic IDs, such as `actor-001`, `channel-001`, and `message-001`.
Create scanner sentinels in memory.
Never use real secrets in tests.
Review media, screenshots, database copies, and benchmark captures as carefully as code.

## Write clear technical text

Use ASD-STE100 guidance where possible for documents, instructions, comments, issues, PR descriptions, and commit messages.
Write short, complete sentences in the active voice.
Give one instruction in each sentence.
Use one term for each meaning.
Use the technical terms in the [glossary](docs/glossary.md).
Define new project-specific technical terms in the glossary before you use them in instructions.
Keep identifiers, commands, API names, package names, and license text exact.
Preserve technical requirements when you simplify text.
Do not claim full ASD-STE100 compliance without a complete dictionary and rule check.
See the [writing reference](docs/glossary.md#writing-reference) for the verification limit and official sources.

## Before implementation

Read this file and the relevant repository documents.
Fetch the remote before an audit or status review.
Compare HEAD with `origin/main`.
If the baseline differs, ask which baseline to use.
Check existing issues and PRs before you create work.
Record dependencies.
Link implementation work to its issue.
Keep stack selection open until reviewers accept the equal-workload Rust, Go, and Bun spike.

## Before publication

Follow the [publication safety procedure](docs/publication-safety.md).
Run the sentinel tests.
Scan all tracked files and complete candidate files before you stage named files.
Scan the complete index and the staged diff.
Review every hunk and filename locally.
Complete the review record for that exact digest.
If you edit or stage content, repeat the checks.
Scan complete issue titles and bodies before you post them.
Then fetch the posted text and compare it with the reviewed text.
Do not put raw matches, paths, diffs, credentials, or logs in public reports.

Do not suppress a finding with a directory exclusion, an inline marker, a wildcard, or a broad allowlist.
Use only a reviewed, exact-line entropy exception in the allowlist.
A passing scan supports the review.
It does not guarantee privacy.

## Execution boundaries

Complete the Phase 0 decisions before Phase 1 implementation.
Build a personal-first, AI-native chat and workspace product.
Provide native Android parity and a small laptop footprint over Tailscale first.
Add multiuser support later.
Do not add calls or huddles.

Complete the architecture gates before you build the corresponding features.
These gates cover offline sync, sleep and wake, AI routes, and agent integrations.
They also cover composable apps, workflows, canvases, and T3Code MCP coding delegation.
See the [glossary](docs/glossary.md) for these terms.

Do not change repository protections or install global hooks or configuration without explicit authorization.
Do not create credentials, enable public endpoints, or widen permissions without explicit authorization.
Do not install external packages without explicit authorization.
Never copy host-specific instructions or settings into source files.
Keep reports and scratch files outside the checkout.
Wait for authorization before you push, open a PR, run benchmarks, or build features.
