-- OutreachPilot schema (PostgreSQL). Applied automatically on backend startup.

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS settings (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  daily_target INT NOT NULL DEFAULT 100,
  auto_enabled BOOLEAN NOT NULL DEFAULT true,
  regions TEXT[] NOT NULL DEFAULT ARRAY['Dubai, UAE','USA','San Francisco','New York'],
  industries TEXT[] NOT NULL DEFAULT ARRAY['SaaS','Fintech','E-commerce','IT Services'],
  offer TEXT NOT NULL DEFAULT 'Custom AI-powered software & full-stack development services',
  sender_name TEXT NOT NULL DEFAULT 'Alex',
  tone TEXT NOT NULL DEFAULT 'confident and concise',
  skills TEXT[] NOT NULL DEFAULT ARRAY['Python','Django','FastAPI','React','Node.js','Generative AI'],
  headline TEXT NOT NULL DEFAULT 'Full-stack & GenAI engineer building custom software for growing companies',
  experience TEXT NOT NULL DEFAULT '5+ years shipping full-stack and AI products for startups and enterprises',
  last_run TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS leads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  company TEXT NOT NULL DEFAULT '',
  contact_name TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  industry TEXT NOT NULL DEFAULT '',
  website TEXT NOT NULL DEFAULT '',
  pain_point TEXT NOT NULL DEFAULT '',
  project_idea TEXT NOT NULL DEFAULT '',
  estimated_value TEXT NOT NULL DEFAULT '',
  whatsapp_link TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source TEXT NOT NULL DEFAULT 'manual',
  lead_source TEXT NOT NULL DEFAULT 'ai',
  replied BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_leads_user ON leads(user_id);

CREATE TABLE IF NOT EXISTS emails (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
  company TEXT NOT NULL DEFAULT '',
  contact_name TEXT NOT NULL DEFAULT '',
  to_email TEXT NOT NULL DEFAULT '',
  subject TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  channel TEXT NOT NULL DEFAULT 'email',
  step INT NOT NULL DEFAULT 1,
  type TEXT NOT NULL DEFAULT 'initial',
  status TEXT NOT NULL DEFAULT 'draft',
  simulated BOOLEAN NOT NULL DEFAULT false,
  error TEXT,
  whatsapp_link TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at TIMESTAMPTZ,
  scheduled_for TIMESTAMPTZ,
  deliverable BOOLEAN NOT NULL DEFAULT false,
  lead_source TEXT
);
CREATE INDEX IF NOT EXISTS idx_emails_user ON emails(user_id);
CREATE INDEX IF NOT EXISTS idx_emails_lead ON emails(lead_id);
CREATE INDEX IF NOT EXISTS idx_emails_followup_due ON emails(type, status, scheduled_for);

CREATE TABLE IF NOT EXISTS activity (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_activity_user ON activity(user_id);

-- Suppression list: unsubscribes / manual opt-outs. Checked before every send.
CREATE TABLE IF NOT EXISTS suppressions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT 'unsubscribed',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, email)
);
CREATE INDEX IF NOT EXISTS idx_suppressions_user ON suppressions(user_id);

-- Sending inboxes: per-user SMTP/Resend accounts used for rotation + warm-up + daily caps.
CREATE TABLE IF NOT EXISTS inboxes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  label TEXT NOT NULL DEFAULT 'Inbox',
  provider TEXT NOT NULL DEFAULT 'smtp',
  smtp_host TEXT NOT NULL DEFAULT '',
  smtp_port INT NOT NULL DEFAULT 587,
  smtp_user TEXT NOT NULL DEFAULT '',
  smtp_password TEXT NOT NULL DEFAULT '',
  resend_api_key TEXT NOT NULL DEFAULT '',
  from_email TEXT NOT NULL DEFAULT '',
  daily_cap INT NOT NULL DEFAULT 30,
  warmup_enabled BOOLEAN NOT NULL DEFAULT true,
  sent_today INT NOT NULL DEFAULT 0,
  sent_today_date DATE,
  is_active BOOLEAN NOT NULL DEFAULT true,
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inboxes_user ON inboxes(user_id);

-- Per-email open/click events (raw log; emails table keeps denormalized counters for fast stats).
CREATE TABLE IF NOT EXISTS email_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_id UUID NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_email_events_email ON email_events(email_id);

-- Additive columns for tables that already existed before this migration
-- (CREATE TABLE IF NOT EXISTS above does not alter an already-created table).
ALTER TABLE emails ADD COLUMN IF NOT EXISTS opened_at TIMESTAMPTZ;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS open_count INT NOT NULL DEFAULT 0;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS clicked_at TIMESTAMPTZ;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS click_count INT NOT NULL DEFAULT 0;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS inbox_id UUID REFERENCES inboxes(id) ON DELETE SET NULL;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS suppressed BOOLEAN NOT NULL DEFAULT false;

-- Tier 2: user-defined follow-up sequences (replaces the old hardcoded 2-step ramp).
CREATE TABLE IF NOT EXISTS sequence_steps (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  step_order INT NOT NULL,
  delay_days INT NOT NULL DEFAULT 3,
  angle TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sequence_steps_user ON sequence_steps(user_id, step_order);

-- Tier 2: CRM pipeline stage + freeform notes per lead.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT 'new';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS reply_intent TEXT;

-- Tier 2: A/B subject-line testing.
ALTER TABLE emails ADD COLUMN IF NOT EXISTS variant TEXT;

-- Tier 2: meeting-booking link surfaced as a CTA in AI-written emails.
ALTER TABLE settings ADD COLUMN IF NOT EXISTS meeting_link TEXT NOT NULL DEFAULT '';

-- Tier 3: team seats. A NULL owner_id means this user IS a tenant (owns their own
-- workspace); a set owner_id means this login shares that owner's entire workspace.
ALTER TABLE users ADD COLUMN IF NOT EXISTS owner_id UUID REFERENCES users(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_users_owner ON users(owner_id);

-- Tier 3: billing/subscription state, set via Stripe checkout + webhooks.
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'starter';
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;

-- Tier 4: AI voice-note personalization (generated on demand, served from local disk).
ALTER TABLE emails ADD COLUMN IF NOT EXISTS voice_note_url TEXT;

-- Tier 5: white-label branding, shown in the in-app sidebar to a workspace's own team/clients.
ALTER TABLE settings ADD COLUMN IF NOT EXISTS brand_name TEXT NOT NULL DEFAULT '';
ALTER TABLE settings ADD COLUMN IF NOT EXISTS brand_logo_url TEXT NOT NULL DEFAULT '';

-- Tier 5: referrals — tracked, not auto-rewarded (no reward-crediting logic exists yet).
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code TEXT UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by UUID REFERENCES users(id) ON DELETE SET NULL;

-- Tier 5: user-supplied real results/testimonials the AI may cite in follow-ups instead of
-- inventing statistics — each entry is a short, factual claim the user vouches for themselves.
ALTER TABLE settings ADD COLUMN IF NOT EXISTS proof_points TEXT[] NOT NULL DEFAULT '{}';

-- Tier 5: public API keys, for Zapier/Make-style generic webhook/HTTP integrations.
CREATE TABLE IF NOT EXISTS api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  label TEXT NOT NULL DEFAULT 'API key',
  key_hash TEXT NOT NULL,
  key_preview TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);

-- Tier 5: AI-drafted LinkedIn outreach text — manual copy-paste only, never automated
-- (LinkedIn's ToS prohibits automating a personal account; see PRD notes).
ALTER TABLE leads ADD COLUMN IF NOT EXISTS linkedin_note TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS linkedin_message TEXT;
