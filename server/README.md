# Chat server

Implements the [chat slice contract](../docs/design/chat-slice-contract.md).
Refs #3, #6, #7, #25.
The server uses Go 1.26.0 or newer, the standard library, modernc SQLite,
and x/crypto bcrypt. The other module requirements are transitive dependencies.

## Run

Set `PAVILION_DB` to a database file outside the checkout in a private directory.
Use a synthetic password of 12 to 72 bytes. Do not use a real credential.
Run these commands in Bash:

```sh
cd server
read -rs -p 'Synthetic test password: ' PAVILION_TEST_PASSWORD
export PAVILION_TEST_PASSWORD
go run . -db "$PAVILION_DB" -test-mode
```

Test mode seeds `actor-001`. It updates that owner's password hash at startup.
Without `-test-mode`, all sign-in and token requests return `401`, including tokens
from an earlier test-mode run. Startup logs that authentication is disabled until
production bootstrap is approved. Production enrollment is not implemented.
Test mode accepts only synthetic actor IDs. Sessions record their test-mode origin.
Migration 3 rejects legacy sessions with no origin record. Sign in again after upgrade.
The default address is `127.0.0.1:8080`. `-listen` selects another address.
No Tailscale or firewall setting changes. Stop with Ctrl+C.

## API

Send JSON request bodies. After sign-in, set the `Authorization` request header
to the `Bearer` scheme, a space, and the opaque token.
The token appears only in the sign-in response. Store it as private client data.

| Method and route | Request | Response |
| --- | --- | --- |
| `POST /api/sign-in` | `actor_id`, `password`, `device_id` | `200`: `token`, `owner_id`, `expires_at`, `history_id` |
| `POST /api/sign-out` | No body | `204` |
| `POST /api/channels` | `id`, `name` | `201`: channel; `200` on retry |
| `GET /api/channels` | None | `200`: `channels` array |
| `GET /api/channels/{id}` | None | `200`: channel |
| `POST /api/channels/{id}/messages` | `id`, `body` | `201`: message; `200` on retry |
| `GET /api/channels/{id}/messages` | None | `200`: `messages` array in server sequence order |
| `GET /api/sync?after=0&limit=100` | None | `200`: `history_id`, `events` array, `next_seq` |

A channel has `id`, `name`, `seq`. A message has `id`, `channel_id`, `body`, `seq`.
An event has `seq`, `owner_id`, `kind`, `entity_id`, `payload`.
Its payload is the complete channel or message, including `seq`.
IDs must be lowercase UUIDv7 strings. Channel names are at most 200 UTF-8 bytes.
Message bodies are at most 65,536 UTF-8 bytes. Whitespace-only values fail.
Retries must match the stored name or body and channel. A mismatch returns `409`.
Another owner's entity returns `404`. An invalid session returns `401`.
Known limit: create requests return `404` if another owner already uses the client
ID, and `201` if the ID is unused. This difference can reveal whether an ID exists.
This slice retains that behavior.

`expires_at` is an integer Unix timestamp in seconds.
Errors have an `error` string. Invalid input returns `400`.
The server rejects unknown JSON fields, including client-supplied ownership and sequence.

Sync defaults to cursor zero and 100 events. The limit is 1 to 500.
A cursor above the owner's latest sequence returns `410`.
Successful channel/message writes and retries add `history_id` at the top level.
Store it with the sync cursor. Send `history=<history_id>` on later sync requests.
A mismatch, or a nonzero cursor without `history`, returns `410`. Clear cached data
and cursor/history metadata, keep the outbox, then sync from zero without `history`.
Compare write acknowledgment history IDs before applying them.
An empty page keeps the input cursor. Sequence numbers can have gaps between owners.
Every SQLite connection uses `synchronous=FULL`. This improves SQLite durability
if storage honors fsync, as the [SQLite documentation](https://www.sqlite.org/pragma.html#pragma_synchronous) describes.
Data loss can still occur after a power cut.
Startup removes stray regular `.history-*` temporary files. Active database files,
WAL/SHM, the valid history marker, directories, and symlinks are retained.
Use a separate private directory per database; reserve `.history-*` for these temps.
The first migration creates the `history_id` entry in `meta`; migration 4 upgrades existing stores.
The private database sidecar named `<database>.history` records a high-water
mark before event commits. Its durability depends on storage honoring fsync. Startup rotates history after sequence rollback, a
history mismatch, or a missing sidecar. Normal restart preserves it. Invalid
sidecar state blocks startup. This does not detect every restore.

Restore limits:

- Database-only rollback below the retained live mark, or different database and
  sidecar IDs: detected; startup rotates history and the old ID gets `410`.
- Missing sidecar: conservative rotation. Invalid sidecar: startup blocked.
- Whole-directory rollback of DB, WAL, SHM, and high-water file: undetected when
  both IDs match. A newer cursor gets `410` only while it is ahead. New writes that
  reach it produce `200` with no events; writes past it return only later events.
  Replaced rows at or below the cursor stay stale on the client.
- Same history ID and a maximum sequence equal to or above the retained mark: undetected.

Use these restore steps:

1. Stop the server and wait for it to exit.
2. Choose a consistent backup. Never mix DB, WAL, or SHM from different snapshots.
3. For a checkpointed DB-only backup, keep the live `.history`, remove leftover
   live WAL/SHM, and replace only the DB.
4. For a whole-directory snapshot, restore its four files together, then remove
   the restored `.history` before startup to force a fresh ID. This is an explicit
   restore action, not automatic detection.
5. Start the server. Clients retain the outbox and resync from zero after `410`.

Restored authentication state is old too; later sign-outs are not preserved.
Proposal only: allow the high-water file outside the restored directory. If that
independent file is retained, the current comparison could detect a lower-sequence
whole-directory rollback before new writes hide it. No flag implements this.
A client-held history ID alone cannot distinguish a backup with the same ID.
See the [contract](../docs/design/chat-slice-contract.md#restore-procedure) for
backup conditions and the independent-state proposal's limits.

Entity writes and their events commit together. Retries append no event.
Session writes do not create chat events.
Use sync for recovery. The optional SSE stream is not implemented.
Channel and message list reads are not paged in this slice.
Channel updates and deletion are outside the create/list scope.

## Test

From `server/`:

```sh
go mod verify
go vet ./...
go test -race ./...
```

Tests cover authentication, owner isolation, independent sessions, history after
sign-out, retries, database reopen, cursor recovery, transaction rollback,
concurrent retries, schema upgrade, newer-schema rejection, and SQLite settings.
Client offline storage, drafts, outbox behavior, and local sign-out deletion belong
to the client lane. CI also runs the Python privacy guard tests and content scans.

## Security limits

Sessions expire after 30 days. Sign-out revokes only the current session.
The server stores SHA-256 token digests and bcrypt password hashes at cost 10.
Database files and their WAL and shared-memory sidecar files use mode 0600.
Startup also repairs existing sidecar permissions. Keep the directory private.
The server has request size and connection time limits. It has no login rate limit
or TLS endpoint. Keep test mode on loopback. Production enrollment, access policy,
and transport protection need owner review before remote use.
