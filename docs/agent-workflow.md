# Agent workflow

Pavilion uses a pinned upstream agent workflow for nontrivial engineering work.
This file gives the pin and the rules for startup, children, and evidence.
It does not copy the upstream text.
Read the upstream files at the pin.

## Pin

| Item | Value |
| --- | --- |
| Source | Private. See [Locate the source](#locate-the-source). |
| Commit | `101b274dd991f694e1f7024be2157e5f3adf07de` |
| Version | `0.15.25` |
| Entry file | `skills/poteto-mode/SKILL.md` |
| Playbooks | `skills/poteto-mode/playbooks/` |

Paths are relative to the workflow package.

## Locate the source

The public files do not name the upstream repository.
A private bootstrap file names it. This file is a prerequisite.

1. Read the `PAVILION_WORKFLOW_SOURCE` environment variable.
   It holds the path of the private bootstrap file.
   The file must be outside the repository.
2. Read the file. It holds one repository URL and one package path.
3. Read the entry file from that repository at the pinned commit.
4. Confirm that the package version at that commit is the pinned version.

If the variable is not set, the file is missing, or the commit or version does not match, stop.
Report `missing source` and the step that failed.
Do not use a different copy, version, or memory of the workflow.
Do not claim that you followed the pinned files.
No tool enforces this rule. Each agent must follow it.

To change the pin, open a PR that updates this table.
Read the changed upstream files at the new commit before you update the table.

## Start a session

1. Locate the source. Then read the entry file at the pinned commit in full.
2. Match the task to one playbook. Read that playbook file in full.
3. Also read the Opening a PR playbook if the work can end in a PR.
4. Read the leaf `SKILL.md` of each principle or skill before you apply it.
5. Open a todo list. Copy the playbook steps into it verbatim before the task items.
6. Record the pin, the playbook name, and the files that you read.

Do not name a playbook, principle, or skill that you did not read in this session.

## Give work to children

Each child prompt must contain these items:

- The pin, the name `PAVILION_WORKFLOW_SOURCE`, and the package paths of the entry file and the matched playbook.
- The playbook steps that the child owns.
- A link to [AGENTS.md](../AGENTS.md) and to this file.
- The scope, the acceptance criteria, and the stop condition.
- An instruction to return evidence for each owned step.

Use package paths at the pin.
Do not put local absolute paths in a child prompt.
A child that cannot locate the source must report `missing source` and stop.

## Collect stage evidence

Stage evidence is a record that a playbook step occurred.
For each step, record one of these results:

| Result | Required content |
| --- | --- |
| `done` | The command, file, commit SHA, or review that shows the result. |
| `skip: <reason>` | The reason, such as a missing tool or a step outside the scope. |
| `n/a: <reason>` | The reason that the step does not apply to this task. |

Put the evidence in the [PR template](../.github/pull_request_template.md) or in the final report.
Keep each skipped and not-applicable step in the list.
A step without evidence is not done.
Do not mark a step done because a similar step occurred.
Do not mark a step done because a child said so. Check the evidence.

## Repository rules override upstream defaults

[AGENTS.md](../AGENTS.md) and [publication safety](publication-safety.md) take priority over upstream text.
These upstream defaults do not apply in Pavilion:

| Upstream default | Pavilion rule |
| --- | --- |
| Proceed without approval on reversible and external actions. | Get authorization before a push, a PR, a benchmark, or a feature build. |
| Default models and reasoning levels for each role. | Use the model roles, effort, and capacity in the agent policy. |
| Open every PR as ready, not as a draft. | Use the PR state that the owner authorized. |
| Put the local absolute path of the entry file in child prompts. | Use package paths at the pin. |

If a skill or tool that a step names is not available, record the step as `skip: <reason>`.
This rule does not apply to a step that the playbook marks as mandatory with no skip.
For such a step, use the exception that the playbook gives.
If that exception is also not available, stop and report the blocked step.
Do not replace the step with a different step without a record.
