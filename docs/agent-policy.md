# Agent policy

This policy routes agent work. The file `policy/agent-policy.json` holds the public rules.
The script `scripts/agent_policy.py` applies them.
Use the terms in the [glossary](glossary.md#agent-policy-terms).

The public policy names models, purposes, effort levels, and review rules.
It does not name the tools, services, or accounts that run the models.
A request names an Executor by an opaque ID.
A private Routing file maps each Executor to the models that it can run.

## Roles

| Model | Purpose | Note |
| --- | --- | --- |
| claude-sonnet-5-5 | Break down tasks. Implement. | Not a default reviewer. |
| gpt-6.1-sol | Build, debug, test, review. | |
| gpt-6-luna | Small checks, extraction, docs. | |
| claude-opus-5-5 | Bounded design, security challenge, review, UI/UX. | Worker. |
| grok-4.7 | Bounded file, code, test, review. | Validated for text, file, read, write, test, failure, repair, review, handoff, and cancel. Untested for git, worktree isolation, large tasks, network, MCP, and executor errors. |
| grok-4.6 | Same purposes as grok-4.7. | Untested. |
| gpt-6-astra | Important unresolved technical questions. | Optional. |
| claude-fable-5-1 | UI/UX design, alternative analysis. | Optional. |

An optional role needs `optional_approved` set to `true` in the request.
A model must have a role and must be on the allowlist of the requested Executor.
The checker rejects any other model.

## Executors and the Routing file

The policy has two Executors: `executor-primary` and `executor-fallback`.
A request names its Executor in the `executor` field. The default is `executor-primary`.
Use `executor-fallback` only when the request sets `primary_available` to `false`.
A missing value, or any value other than the JSON boolean `false`, means the primary Executor is available.

The Routing file lists the allowed models for each Executor.
The real file stays private. Never commit it, quote it, or put its values in an issue or PR.
The public example `policy/routing.example.json` holds placeholders only.
With the example, every real model fails the allowlist check. This is the safe default.

The checker finds the Routing file in this order:

1. The `--routing` argument.
2. The environment variable `PAVILION_ROUTING_FILE`.
3. The public example.

The Routing file is a JSON object with exactly these keys:

| Key | Requirement |
| --- | --- |
| `version` | The number `1`. |
| `executors` | An object with exactly the keys `executor-primary` and `executor-fallback`. |
| `executors.<id>.models` | A non-empty list of non-empty model strings. This is the only key of an Executor entry. |

Any other shape is an input error with exit status 2.
The error text never shows the path or the file content.
The checker trims and lowercases each model before it compares it with the allowlist.

## Rules

- A Worker uses medium effort by default. Low Worker effort needs no evidence.
- A Coordinator always uses low effort.
- Worker effort above medium needs an `escalation` object with the fields `evidence`, `scope`, and `stop_condition`.
- Use `executor-primary` first. Use `executor-fallback` only when the request sets `primary_available` to `false`.
- Do not use paid upgrades.
- A Lane holds at most 3 agents.
- All Lanes together hold at most 10 agents. This count includes nested children and Reserved waits.
- Every request needs `agent_id` and `lane`.
- The checker trims and lowercases model and agent IDs before it compares them.
- A Coordinator request passes the same Executor, model, and purpose checks as a Worker request.
- Author and reviewer must be different. They need different agent IDs and different models.
- A reviewer role must include review. Sonnet fails this check by default.
- Review evidence must name an Exact candidate. The checker rejects a stale SHA. The candidate SHA and the head SHA must be strings of 40 lowercase hex characters. The checker does not trim whitespace.
- A raised effort needs an `escalation` object. Its fields `evidence`, `scope`, and `stop_condition` must be non-empty strings. The `escalation` field is separate from the review `evidence` object. A value that is not an object is an input error.

## Run the check

```sh
export PAVILION_ROUTING_FILE="$ROUTING_FILE"
python3 scripts/agent_policy.py request.json ledger.json
python3 scripts/agent_policy.py request.json ledger.json --routing "$ROUTING_FILE"
```

Keep the Routing file outside the checkout.
The request file holds one JSON object.
The ledger file holds a JSON list of active or reserved agents. Each entry has `agent_id`, `lane`, and `state`. `agent_id` and `lane` must be non-empty strings. `state`, if present, must be a non-empty string.
The exit status is 0 for admitted, 1 for rejected, and 2 for an input error.
A wrong data type, such as a request that is not an object, is an input error.
A missing or invalid Routing file is also an input error.
Use synthetic IDs such as `actor-001` in requests and ledgers.

Local authorization restrictions apply to every agent.
The `AGENTS.md` rules on pushes, PRs, packages, credentials, and benchmarks stay in force.
