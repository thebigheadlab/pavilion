# Agent workflow start template

Copy this section into the `AGENTS.md` file of a new or existing project.
Replace each value in angle brackets.
Keep the project privacy and approval rules.
Those rules take priority over this section.

```md
## Agent workflow

Use the agent workflow for nontrivial engineering work.
Pin: commit `<40-hex SHA>`, version `<version>`.
Source: `<repository and package path>`. In a public project with a private upstream, write instead:
`<PROJECT>_WORKFLOW_SOURCE` gives the path of a private file outside the repository.
The file holds the repository URL and the package path.
If the source is missing or the commit or version does not match, stop and report `missing source`.
Read the upstream files at that commit. Do not copy them into this repository.

At session start:

1. Locate the source. Read `skills/poteto-mode/SKILL.md` in full.
2. Match the task to one playbook in `skills/poteto-mode/playbooks/`. Read it in full.
3. Read the Opening a PR playbook if the work can end in a PR.
4. Read each principle or skill file before you apply it.
5. Copy the playbook steps verbatim into the todo list.

Give each child the commit, the source variable name, the playbook path, the steps it owns, and these rules.
Do not put local absolute paths in a child prompt.

Record one result for each playbook step: `done` with evidence,
`skip: <reason>`, or `n/a: <reason>`.
A step without evidence is not done.
Do not name a playbook, principle, or skill that you did not read.

The project rules override upstream defaults for approvals,
models, effort, and PR state.
If a named tool is not available, record the step as `skip: <reason>`.
A step that the playbook marks as mandatory with no skip cannot be skipped.
Use the playbook exception, or stop and report the blocked step.
```

Also add the PR checklist from [the Pavilion PR template](../../.github/pull_request_template.md).
Remove the items that do not apply to the project.
