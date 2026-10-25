# Agent policy

This policy routes agent work. The file `policy/agent-policy.json` holds the rules.
The script `scripts/agent_policy.py` applies them.
Use the terms in the [glossary](glossary.md#agent-policy-terms).

We did not import the earlier cloud patch.
We built this policy again from the stated rules.
It does not claim to preserve that patch.

## Roles

| Provider | Model | Purpose | Note |
| --- | --- | --- | --- |
| claude | claude-sonnet-5-5 | Break down tasks. Implement. | Not a default reviewer. |
| codex | gpt-6.1-sol | Build, debug, test, review. | |
| codex | gpt-6-luna | Small checks, extraction, docs. | |
| claude | claude-opus-5-5 | Bounded design, security challenge, review, UI/UX. | Worker. |
| cursor | grok-4.7 | Bounded file, code, test, review. | Validated for text, file, read, write, test, failure, repair, review, handoff, and cancel. Untested for git, worktree isolation, large tasks, network, MCP, and provider errors. |
| cursor | grok-4.6 | Same purposes as grok-4.7. | Untested. |
| codex | gpt-6-astra | Important unresolved technical questions. | Optional. |
| claude | claude-fable-5-1 | UI/UX design, alternative analysis. | Optional. |

An optional role needs `optional_approved` set to `true` in the request.
The Cursor allowlist is `grok-4.7` and `grok-4.6`.
The policy denies the Cursor models composer, claude, gemini, and auto.

## Rules

- A Worker uses medium effort by default. Low Worker effort needs no evidence.
- A Coordinator always uses low effort.
- Worker effort above medium needs the fields `evidence`, `scope`, and `stop_condition`.
- Use T3Code first. Use Codex Cloud only when the request sets `t3code_online` to `false`. A missing value means T3Code is online.
- Do not use paid upgrades.
- A Lane holds at most 3 agents.
- All Lanes together hold at most 10 agents. This count includes nested children and Reserved waits.
- Every request needs `agent_id` and `lane`.
- The checker trims and lowercases provider, model, and agent IDs before it compares them.
- A Coordinator request passes the same provider, model, and purpose checks as a Worker request.
- Author and reviewer must be different. They need different agent IDs and different models.
- A reviewer role must include review. Sonnet fails this check by default.
- Review evidence must name an Exact candidate. The checker rejects a stale SHA. The candidate SHA and the head SHA must be strings of 40 lowercase hex characters.
- A raised effort needs `evidence`, `scope`, and `stop_condition`. Each must be a non-empty string.

## Run the check

```sh
python3 scripts/agent_policy.py request.json ledger.json
```

The request file holds one JSON object.
The ledger file holds a JSON list of active or reserved agents. Each entry has `agent_id`, `lane`, and `state`. `agent_id` and `lane` must be non-empty strings. `state`, if present, must be a non-empty string.
The exit status is 0 for admitted, 1 for rejected, and 2 for an input error.
A wrong data type, such as a request that is not an object, is an input error.
Use synthetic IDs such as `actor-001` in requests and ledgers.

## pstack mapping

pstack is a set of agent skills from the upstream project `cursor/plugins`.
This repository records upstream commit `9580c23696ac8d7abed0c166f2f9918800afb819` (v0.15.32).
No upstream text is copied here. This section attributes the source only.
The upstream license is MIT. The file `THIRD_PARTY_NOTICES.md` holds the attribution and the MIT license text.

| pstack duty | Policy treatment |
| --- | --- |
| Coordinate | Coordinator, low effort. |
| Plan and split work | `break_down` purpose. |
| Write code | `implement`, `build`, `code`, `file` purposes. |
| Challenge a design | `design`, `security_challenge` purposes. |
| Review | `review` purpose with author/reviewer separation. |

Local authorization restrictions override upstream autonomy defaults.
The `AGENTS.md` rules on pushes, PRs, packages, credentials, and benchmarks stay in force.
