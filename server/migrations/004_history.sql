CREATE TABLE IF NOT EXISTS meta (
 key TEXT PRIMARY KEY,
 value TEXT NOT NULL
);
INSERT OR IGNORE INTO meta(key,value) VALUES('history_id',lower(hex(randomblob(32))));
