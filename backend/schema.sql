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
