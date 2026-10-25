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

## Agent policy

These rules are instructions that guide agents.
No runtime tool enforces them.
Each agent must follow them.
Use the terms in the [glossary](docs/glossary.md#agent-policy-terms).

Use the roles in this table.
A model must have a role.

| Model | Purpose | Note |
| --- | --- | --- |
| claude-sonnet-5-5 | Break down tasks. Implement. | Not a default reviewer. |
| gpt-6.1-sol | Build, debug, test, review. | |
| gpt-6-luna | Small checks, extraction, docs. | |
| claude-opus-5-5 | Bounded design, security challenge, review, UI/UX. | Worker. |
| grok-4.7 | Bounded file, code, test, review. | Validated for text, file, read, write, test, failure, repair, review, handoff, and cancel. Untested for git, worktree isolation, large tasks, network, MCP, and execution errors. |
| grok-4.6 | Same purposes as grok-4.7. | Untested. |
| gpt-6-astra | Important unresolved technical questions. | Optional. |
| claude-fable-5-1 | UI/UX design, alternative analysis. | Optional. |

Do not assign an untested capability to a model. Test it first in a bounded task.
Use an optional model only when the Coordinator approves it within the approved task scope.

Effort:

- A Worker uses medium effort by default.
- A Coordinator always uses low effort.
- Raise Worker effort only with evidence, a bounded scope, and a stop condition.

Capacity:

- A Lane holds at most 3 agents.
- All Lanes together hold at most 10 agents.
- Count nested children and Reserved waits in both limits.

Execution environment:

- Use the primary execution environment.
- Use the fallback only when the primary is unavailable.
- Do not use paid upgrades.

Review:

- The author and the reviewer must be different agents on different models.
- A reviewer role must include review. Sonnet is not a default reviewer.
- Review evidence must name the exact 40-hex commit SHA under review.
- Review evidence is stale for any other SHA.
