CREATE TABLE owners (
 owner_id TEXT PRIMARY KEY,
 password_hash BLOB NOT NULL
);
CREATE TABLE sessions (
 session_id TEXT PRIMARY KEY,
 owner_id TEXT NOT NULL REFERENCES owners(owner_id),
 token_hash BLOB NOT NULL UNIQUE,
 device_id TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 revoked_at INTEGER
);
CREATE TABLE channels (
 id TEXT PRIMARY KEY,
 owner_id TEXT NOT NULL REFERENCES owners(owner_id),
 name TEXT NOT NULL,
 seq INTEGER NOT NULL,
 UNIQUE(owner_id, id)
);
CREATE TABLE messages (
 id TEXT PRIMARY KEY,
 owner_id TEXT NOT NULL REFERENCES owners(owner_id),
 channel_id TEXT NOT NULL,
 body TEXT NOT NULL,
 seq INTEGER NOT NULL,
 FOREIGN KEY(owner_id, channel_id) REFERENCES channels(owner_id, id)
);
CREATE TABLE events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT,
 owner_id TEXT NOT NULL REFERENCES owners(owner_id),
 kind TEXT NOT NULL CHECK(kind IN ('channel.created', 'message.created')),
 entity_id TEXT NOT NULL,
 payload TEXT NOT NULL
);
CREATE TABLE meta (
 key TEXT PRIMARY KEY,
 value TEXT NOT NULL
);
INSERT INTO meta(key,value) VALUES('history_id',lower(hex(randomblob(32))));
