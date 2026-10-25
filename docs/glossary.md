# Technical glossary

Use these definitions in Pavilion documents and instructions.
Use each term with the same meaning.
The [repository instructions](../AGENTS.md#write-clear-technical-text) define the writing rule.
The [publication safety procedure](publication-safety.md) defines the checks before publication.

## Publication terms

| Term | Meaning |
| --- | --- |
| Allowlist | A file of reviewed exceptions to the `high-entropy` and `operational-marker` rules. Each exception applies to one exact line and path. |
| Artifact | A file or other output that a tool creates for storage or publication. |
| Bot credentials | Existing authentication data for the repository automation account. |
| Candidate file | A complete file proposed for publication. An issue title or body can be a candidate file. |
| Commit metadata | A commit's author, committer, dates, and message. |
| Continuous integration, or CI | Automated checks that a repository service runs after a specified event. |
| Digest | A fixed-length value calculated from bytes. The guard uses SHA-256 to detect changes. |
| Entropy | A measure of character variation. High entropy can indicate a secret, but it does not prove one exists. |
| Fixture | Input data that a test uses. Pavilion fixtures must use neutral synthetic data. |
| Guard | The local script `scripts/publication_guard.py`. It checks content against privacy rules. |
| Hunk | A group of nearby changed lines and context lines in a Git diff. |
| Index | The Git staging area. It contains the file versions selected for the next commit. |
| Index manifest | The list of staged paths, file modes, and object IDs used to bind a review to the index. |
| Index blob | The complete bytes of one file version in the index. |
| Lexical parent | A directory component in a path before the filesystem resolves that path. |
| Marker file | A private local file outside the repository. It lists the operational markers, one per line. The guard reads it from the `PAVILION_PRIVATE_MARKERS` environment variable. |
| Operational marker | A case-insensitive literal text that the guard must not find in public content. The owner keeps the list private. |
| Opaque file | A file that the guard cannot validate as permitted text. Media, archives, and databases need separate review. |
| Publication | A transfer of content to a public repository, issue, PR, attachment, or build artifact. |
| Pull request, or PR | A request to review and merge a branch into another branch. |
| Review record | A local JSON file that records review decisions for one exact index, diff, and guard version. |
| Sentinel | A synthetic marker that a test expects the guard to reject. It is not a real secret. |
| Stage-zero index entry | A normal index entry without an unresolved merge conflict. |
| Staged diff | The difference between HEAD and the index. It includes removed lines, context, filenames, and other Git metadata. |
| Submodule | A Git entry that refers to a commit in another repository. |
| Symlink | A filesystem link to another path. The guard rejects symlinks and paths with symlink parents. |
| Synthetic data | Test data created without copying user content or real private values. |
| Traceback | The Python error report that lists function calls and source paths. |
| UTF-8 | The text encoding that the guard accepts. |
| Tracked file | A file that Git records in the index. |
| Working copy | The file bytes currently present in the checkout. They can differ from the index bytes. |

## Product terms

| Term | Meaning |
| --- | --- |
| Architecture gate | A required architecture decision and its acceptance before the corresponding feature implementation starts. |
| Agent integration | A contract that lets an AI agent receive context, take permitted actions, and return results. |
| AI-native | Designed to support AI chats and agents as core product functions. |
| AI route | A supported path to an AI service through an eligible subscription or API. |
| Canvas | A shared document that supports collaborative edits. |
| Composable app | A product extension that can use GitHub, a custom MCP service, or a chain of actions. |
| MCP | Model Context Protocol. A protocol for tool and context connections. |
| Native Android parity | The Android app supports the same product functions as the other supported clients. |
| Offline sync | The process that stores local changes without a connection and resolves them after reconnection. |
| Personal-first | The initial product serves one owner's workspace. Multiuser support comes later. |
| Spike | A bounded investigation that supplies evidence for an engineering decision. |
| Stack | The languages, runtimes, libraries, and storage components selected for the product. |
| T3Code MCP coding delegation | The use of a T3Code MCP connection to assign coding work to an agent. |
| Tailscale | The private network connection used for initial access between devices. |
| Workflow | A defined sequence of actions. Automation can run the sequence after a trigger. |

## Agent policy terms

| Term | Meaning |
| --- | --- |
| Admission | The check that accepts or rejects one agent request under the [agent policy](agent-policy.md). The result lists the reasons. |
| Author and reviewer separation | The rule that a reviewer has a different agent ID and a different model than the author. |
| Coordinator | An agent that assigns work and does not do the work. A Coordinator always uses low effort. |
| Executor | An opaque ID, such as `executor-primary`, for the place that runs an agent. A private Routing file maps each Executor to its allowed models. |
| Exact candidate | One commit, named by a 40-hex SHA, that a review covers. Evidence for another SHA is stale. |
| Lane | A group of agents under one Coordinator. A Lane holds at most 3 agents. |
| Reserved wait | A slot held for an agent that waits for a result. It counts toward the Lane and global caps. |
| Routing file | A private JSON file outside the repository. It lists the allowed models for each Executor. The public example `policy/routing.example.json` holds placeholders only. |
| Worker | An agent that does assigned work. A Worker uses medium effort unless the request gives evidence, scope, and a stop condition. |

## Writing reference

ASD-STE100 Simplified Technical English, or STE, is a controlled language for technical text.
Pavilion uses STE guidance where possible.
Technical names in this glossary support consistent project language.
They are not a claim that the official STE dictionary approves each word or meaning.

Use short sentences, direct instructions, and consistent terms.
Keep technical identifiers and license text unchanged.
A full compliance claim requires the complete standard, its dictionary, and a check of every applicable rule.
This foundation has not completed that check.

Official references are the [ASD-STE100 home page](https://www.asd-ste100.org/)
and [About STE](https://www.asd-ste100.org/about_STE.html).
Issue 9 is dated January 2025.
