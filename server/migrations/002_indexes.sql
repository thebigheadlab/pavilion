CREATE INDEX events_owner_seq ON events(owner_id, seq);
CREATE INDEX messages_channel_seq ON messages(owner_id, channel_id, seq);
CREATE INDEX sessions_expiry ON sessions(expires_at);
