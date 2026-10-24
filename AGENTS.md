# Pavilion execution rules

## Public repository boundary

Treat every tracked file, commit, issue, PR, attachment, and build artifact as
public. Use bot credentials for repository operations. Verify the active account
without printing credentials or personal account details. Stop if bot access is
unavailable. Never create credentials or change global configuration to proceed.

Do not publish personal identities, email addresses, credentials, private paths,
host configuration, private messages, user content, or raw logs. Keep private
planning sources and transcripts out of this repository and its issues. Use
neutral synthetic IDs such as `actor-001`, `channel-001`, and `message-001`.
Generate scanner sentinels in memory; never use real secrets for tests. Media,
screenshots, database copies, and benchmark captures need the same review as code.

## Before implementation

Read this file and relevant repository docs. Fetch the remote and compare HEAD
with `origin/main` before audits or status reviews. If the baseline differs, ask
which baseline to use. Check existing issues and PRs before creating work.
Record dependencies and link implementation to its issue. Keep stack selection
open until the equal-workload Rust, Go, and Bun spike has been reviewed.

## Before publication

Follow `docs/publication-safety.md`. Run the sentinel tests, full tracked-file
scan, and full candidate scan before staging named files. Scan the complete index
and staged diff, review every hunk and filename locally, and complete the review
record tied to that exact digest. Any edit or staging change requires rechecking.
Scan complete issue titles and bodies before posting, then read the exact text.
Do not print raw matches, paths, diffs, credentials, or logs into public reports.

Never silence a finding with a directory exclusion, inline suppression, wildcard,
or broad allowlist. Only a reviewed, exact-line entropy exception may use the
allowlist. A passing scan is evidence for review, not a privacy guarantee.

## Execution boundaries

Phase 0 gates precede Phase 1 implementation. The product is personal-first,
AI-native chat and workspace, with native Android parity and a small laptop
footprint over Tailscale first. Multiuser comes later. Calls and huddles are out
of scope. Architecture gates must cover offline sync, sleep/wake, AI routes,
agent integrations, composable apps, workflows, canvases, and T3Code MCP coding
delegation before those features are built.

Do not change repository protections, install global hooks or config, create
credentials, enable public endpoints, widen permissions, or install external
packages without explicit authorization. Never copy host-specific instructions
or settings into source. Keep reports and scratch outside the checkout. Do not
push, open a PR, run benchmarks, or build features until authorized for that step.
