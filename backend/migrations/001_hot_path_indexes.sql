-- Indexes for the most common per-user queries.
CREATE INDEX IF NOT EXISTS idx_leads_user_created ON leads(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_emails_status_sched ON emails(status, scheduled_for);
