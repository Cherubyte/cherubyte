-- Signups for a hosted panel. Self-hosting is free and needs no account, so
-- this table only ever holds people who asked us to run one for them.
CREATE TABLE IF NOT EXISTS signups (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  email        TEXT    NOT NULL,
  -- Lower-cased email, so "A@b.com" and "a@b.com" cannot both sign up. Kept as
  -- its own column rather than a functional index: D1 is SQLite, and a UNIQUE
  -- constraint that a future query forgets to match case on would let one in.
  email_key    TEXT    NOT NULL UNIQUE,
  networks     TEXT,
  note         TEXT,
  source       TEXT,
  created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_signups_created ON signups (created_at DESC);
