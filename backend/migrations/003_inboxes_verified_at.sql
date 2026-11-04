-- Code inserts inboxes.verified_at but the column was never created (every inbox create returned 500).
ALTER TABLE inboxes ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
