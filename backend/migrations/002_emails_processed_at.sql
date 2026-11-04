-- Follow-up claim marker (code referenced this column but the schema never created it).
ALTER TABLE emails ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
