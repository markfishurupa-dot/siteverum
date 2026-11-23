CREATE TABLE portal_sessions (
    digest text PRIMARY KEY,
    expires_at timestamptz NOT NULL
);
CREATE INDEX portal_sessions_expiry ON portal_sessions (expires_at);
