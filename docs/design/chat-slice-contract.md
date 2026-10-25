# Chat slice contract

Status: draft for review. Refs #3, #4, #6, #7.
The owner accepted the stack: Go with SQLite for the server, and React with TypeScript for the shared web and Android client.
Capacitor packages the Android client.
This contract covers the first chat slice only.
It does not complete the architecture gates in #3, #4, or #5.

## Scope

In scope: local test sign-in, channels, durable messages, offline reads, drafts, an outbox, and recovery after reconnect.
Out of scope: calls, huddles, AI, apps, workflows, canvases, attachments, threads, search, and multiuser access.

## Ownership

- Each entity and session row has an `owner_id`. In this slice, one owner exists. The storewide `meta` table has no owner.
- The server derives `owner_id` from the session. The client never sends it.
- A query that does not match the session owner returns `404`, not `403`. This hides other owners' IDs.
- `owner_id` stays in the schema so that multiuser access can add members later without a data rewrite.

## Sessions and authentication

- Test sign-in uses a synthetic user, such as `actor-001`, with a password that the test seeds at startup. No real credential enters the repository.
- The server stores a password hash (argon2id or bcrypt) and a session table: `session_id`, `owner_id`, `device_id`, `created_at`, `expires_at`, `revoked_at`.
- The client receives an opaque random token. The server stores only a SHA-256 of the token.
- `expires_at` in storage and the sign-in response is an integer Unix timestamp in seconds since `1970-01-01T00:00:00Z`.
- Sign-out revokes the server session. The client then deletes its local database, drafts, outbox, and token.
- Sign-out never deletes remote history. A new sign-in downloads history again.
- Repeated or overlapping sign-in creates independent sessions. Sign-out of one session does not revoke another.
- An expired or revoked token returns `401`. The client keeps unsent outbox items, stops sync, and asks for sign-in. After sign-in as the same owner, the outbox resumes. After sign-in as a different owner, the client deletes the earlier local data first.
- Production bootstrap is a proposal only. See [Production bootstrap](#production-bootstrap-proposal).

## Identifiers

- The client creates each message ID before the first send. The format is a UUIDv7 string.
- The server accepts the client ID as the primary key. A repeat send with the same ID and the same body returns the stored message. A repeat with a different body returns `409`.
- Channel IDs use the same rule.

## Server storage

- SQLite in WAL mode, `synchronous=FULL`, `foreign_keys=ON`, `busy_timeout` set.
- `synchronous=FULL` improves SQLite durability when the storage system honors fsync, as the [SQLite documentation](https://www.sqlite.org/pragma.html#pragma_synchronous) describes. Data loss can still occur after a power cut. The high-water file does not replace database commit durability.
- Numbered SQL migrations run at startup in one transaction each. A `schema_version` table records them. The server refuses to start on a newer schema than it knows.
- FTS5 is available for later search. This slice creates no FTS tables.
- Tables: `owners`, `sessions`, `channels`, `messages`, `events`, `meta`.
- The first migration creates a random 64-character lowercase hexadecimal `history_id` in `meta`. Migration 4 adds it to existing stores.
- The live store has a private `<database>.history` sidecar with `history_id` and `high_water`. The high-water mark covers all owners in that database.
- Before an event transaction commits, the server reserves its sequence in the sidecar. It writes a mode-0600 temporary file, syncs it, renames it atomically, and syncs the directory. A sidecar write failure rolls back the event. A failed database commit can cause a conservative history rotation on restart.
- At startup, if `max(events.seq)` is below `high_water`, or the stored history IDs differ, the server rotates the database history ID and records the new state before serving requests. A missing sidecar also rotates the ID. A malformed or unreadable sidecar blocks startup. A normal restart keeps the ID.
- Startup removes regular `.history-*` temporary files from the database directory. It preserves the active database, WAL, SHM, valid high-water file, directories, and symlinks. Cleanup failure blocks startup. Use a separate private directory per database; `.history-*` is reserved for server temporary files.
- Run one server process per database. Stop it before a restore. Follow the [restore procedure](#restore-procedure).
- This is a sequence rollback check, not a detector for every restore. The limits below apply.

## Transaction, events, and cursors

- Each write runs in one transaction. The transaction changes the row and appends one row to `events`.
- `events.seq` is an `INTEGER PRIMARY KEY` that increases monotonically for each owner store. It is the sync cursor.
- An event has `seq`, `owner_id`, `kind` (`channel.created`, `message.created`), `entity_id`, and the JSON payload.
- `GET /api/sync?after=<seq>&limit=<n>&history=<id>` returns `history_id`, `events` in `seq` order, and `next_seq`. A supplied history ID that differs from the server's ID returns `410`, even when the cursor is no longer ahead. A nonzero cursor without `history` also returns `410`. Duplicate `history` parameters return `400`.
- An initial sync uses `after=0` and omits `history`. The client stores `history_id` and the cursor only after it applies the page in one local transaction.
- Successful channel and message write responses include a top-level `history_id`, including idempotent retries. The sign-in response also includes it. Event payloads remain entity data. Sign-out keeps its empty `204` response.
- Before applying a write acknowledgment, the client compares its history ID with the response. If they differ, it keeps the outbox, clears other cached data and cursor metadata, and syncs from zero. The client must not advance its stored history from a write acknowledgment alone.
- Message order in a channel is server `seq` order. Pending local messages show after acknowledged messages, in local creation order.
- `GET /api/events` is an optional server-sent event stream that only signals "new seq available". The client always reads data through `/api/sync`. A lost signal only delays sync.

## Client storage and outbox

- The client uses IndexedDB on web and in the Android WebView. Capacitor SQLite is a later option, not part of this slice.
- Local stores: `channels`, `messages`, `drafts` (one per channel), `outbox`, `meta` (cursor, history ID, owner, device ID).
- A send writes the message with state `pending` and an outbox item in one local transaction. The UI shows it at once.
- The outbox sends items in creation order, one at a time, with exponential backoff and jitter (1 s to 60 s).
- On `2xx` or an idempotent repeat, the item is removed and the message state becomes `acknowledged`.
- On `409` or another `4xx` except `401`, the message state becomes `failed`. The user can retry or discard it.
- Drafts save on each change after a short delay and survive process death.

## Recovery

- Triggers for sync: app start, sign-in, a network `online` event, the app returning to foreground, a stream signal, and a timer of 30 s while visible.
- After a server restart or laptop wake, the client retries with backoff. It then syncs from its stored cursor. Duplicate events are harmless because applies are keyed by entity ID.
- After process death, the client reloads local data, then runs the outbox and sync.
- If the history ID differs or the cursor is ahead of the server, the server returns `410`. The client keeps the outbox, deletes other local data and cursor/history metadata, and syncs from zero without `history`. This handles a database-only rollback with the live high-water file retained, even after a write reuses an old sequence. It does not handle an unannounced whole-directory rollback whose history ID still matches.

## Restore detection limits

- Detected: the database maximum sequence is below the retained live high-water mark. Startup rotates `history_id`. The old ID returns `410`, including after new writes catch up to the old cursor.
- Detected: the database and sidecar history IDs differ. Startup rotates the ID.
- Conservative reset: the sidecar is missing. Startup rotates the ID without proof that a restore occurred.
- Undetected: a consistent older whole-directory snapshot replaces the database, WAL, SHM, and high-water file together. The restored database and high-water file agree, so startup keeps their history ID.
- With that whole-directory restore, a newer client cursor returns `410` only while it is ahead of the server. If new writes reach the cursor before the client syncs, the request returns `200` with no events. If new writes pass the cursor, the request returns `200` with only later events. Replaced rows at or below the cursor remain stale on the client.
- Undetected: a replacement has the same history ID and an equal or higher maximum sequence than the retained mark.
- Blocked: an unreadable or malformed sidecar prevents startup. This is not a detected restore.

`TestWholeDirectoryRestoreLimits` copies all four files from a quiescent older snapshot.
It checks the ahead, equal, and passed cursor cases without changing server behavior.
A client-held history ID alone cannot distinguish the whole-directory case because the backup and client can retain the same ID.

## Restore procedure

Use a consistent backup. A clean shutdown checkpoints the main database.
A backup that still depends on WAL must keep its matching WAL and SHM files.
Do not combine database, WAL, or SHM files from different snapshots.
The regression test copies quiescent files. It does not validate copying an active writer's files.

For a checkpointed main-database backup:

1. Stop the server and wait for it to exit.
2. Keep the current live `<database>.history` unchanged.
3. Remove any leftover WAL and SHM files from the stopped live store.
4. Replace only the main database with the checkpointed backup.
5. Start the server. Clients keep their outbox and resync from zero after `410`.

For a consistent whole-directory backup:

1. Stop the server and wait for it to exit.
2. Replace the database, WAL, SHM, and high-water file together from the same snapshot.
3. Remove the restored `<database>.history` before startup. Its absence forces a fresh history ID.
4. Start the server. Clients keep their outbox and resync from zero after `410`.

Removing the restored sidecar is an explicit restore action. It does not mean that the server automatically detected the whole-directory rollback.
Restored authentication state is also old. These steps do not preserve later sign-outs or other changes absent from the backup.

## Proposal for independent restore state

This proposal is inactive. No flag or startup path implements it.
Add an optional path for the same durable high-water file outside the directory that backup tools replace.
Keep that file at mode 0600 and retain it during restores.
The existing startup comparison could then detect a lower-sequence whole-directory rollback before new writes hide it.
Normal restarts would keep their history ID and would not force a full client resync.
This needs owner approval of the state path and backup boundary.
It still cannot detect restoration of both the database and the independent file, or a replacement with the same history ID and an equal or higher maximum sequence.

## Network boundary

- The server listens on `127.0.0.1` by default. A flag can select another address. This slice does not change Tailscale or firewall settings.
- The Android emulator reaches the host through its loopback alias. A real device needs the owner to approve a Tailscale address later.

## Production bootstrap proposal

This section needs owner review. Nothing here is active.

1. The owner runs a one-time `pavilion bootstrap` command on the laptop.
2. The command creates the owner and prints a one-time enrollment code that expires in 10 minutes.
3. A device enters the code once and receives a device session.
4. The owner can list and revoke device sessions.
5. Passwords are optional. Tailscale identity headers are a later option.

## Acceptance tests

| Area | Test |
| --- | --- |
| Authentication | A request without a token, with a bad token, or with a revoked token returns `401`. |
| Isolation | `actor-002` cannot read or write `actor-001` channels or messages. |
| Sign-out | Sign-out clears local data and keeps server history. Sign-in restores history. |
| Overlap | Two sessions sign in and out in any order without effect on each other. |
| Idempotency | The same message ID sent twice creates one message. A different body returns `409`. |
| Pending | A message sent offline shows as pending, then becomes acknowledged after reconnect. |
| Restart | The server restarts during an outbox retry. No message is lost or duplicated. |
| Process death | The client restarts with a draft and an outbox item. Both survive. |
| Cursor | Sync from an old cursor returns missing events in order. With the live high-water file retained, a database-only restore followed by sequence reuse returns `410` for the old history ID. |
| Whole-directory restore | Restoring the database, WAL, SHM, and high-water file together is undetected. An ahead cursor returns `410`; after new writes reach or pass it, sync returns `200` without correcting replaced rows at or below it. |
| Migration | A database at an earlier schema version upgrades at startup. |
