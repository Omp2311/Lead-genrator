# OutreachPilot — PRD

## Original Problem Statement
Build a website that fully automates cold outreach: automatically find real client leads, send 100+ cold emails daily hands-free, and send proposals to WhatsApp when a phone number exists. Target: Dubai, USA, and high-IT-density cities. Position it as a sellable product. No payment integration for now.

## Architecture
- **Backend**: FastAPI + MongoDB (motor). JWT auth (httpOnly cookies). Emergent LLM key (OpenAI gpt-5.4) for lead generation, cold-email + follow-up copywriting, and per-lead project ideas. Background asyncio scheduler (daily autopilot + due follow-up processing).
- **Frontend**: React 19 + Router + Tailwind + shadcn, "Tactical Dark Mode" (Cabinet Grotesk / IBM Plex Sans, cyan accent). Recharts, sonner.
- **Integrations**: Gmail SMTP (email, LIVE), Apollo (leads, wired), Twilio (WhatsApp, wired). Features auto-activate from backend/.env keys.

## User Personas
- Freelancer / agency owner (full-stack + GenAI dev) who wants a hands-free engine that finds clients needing THEIR skills and pitches tailored projects.

## Core Requirements (static)
- Auth; AI lead discovery tuned to user's skills/regions/industries.
- Per-lead: pain point, tailored project idea + estimated value, personalized cold email, WhatsApp link.
- Editable email drafts with manual Send (single) + Send all; real SMTP delivery.
- Auto follow-up sequences (2 steps) that stop when a lead is marked replied.
- Daily autopilot + manual run. Dashboard, Leads, Outbox, Profile, Automation, Activity.

## Implemented
- **2026-08-02**: JWT auth + admin seed. AI lead+email pipeline. Dashboard, Leads, Outbox, Automation, Activity. Daily scheduler. (Tested 100%.)
- **2026-08-03**: Gmail SMTP live email, follow-up sequences, Profile & Skills page, per-lead project ideas + value, editable drafts with manual Send / Send-all.
- **2026-08-03 (b)**:
  - **Reply Detection (IMAP)** — scans the Gmail inbox (imap.gmail.com), auto-marks a lead replied and cancels its scheduled follow-ups. Runs hourly in scheduler + manual "Scan inbox for replies" button. Endpoint POST /api/replies/scan.
  - **Public Sales Landing Page** at `/` (hero, stats, 6 features, how-it-works, pricing showcase, CTA, footer). App moved under `/app/*`; login/register redirect to `/app`.

## Routing
- `/` public Landing · `/login` · `/register` · `/app` (protected) with nested profile/leads/outbox/automation/activity.

## Integration Status / Limitations
- **Email · Gmail SMTP = LIVE** (omprakashraj100078@gmail.com). Real sends work.
- **Leads · Apollo = BLOCKED** — key valid but on Apollo FREE plan; Search API is paid-only (403). App gracefully falls back to **AI demo leads** (fake emails). Autopilot only real-sends to real (Apollo) leads to protect sender reputation; AI-lead emails stay simulated unless manually sent from Outbox.
- **WhatsApp · Twilio = OFF** — wired, needs TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_FROM.
- No payment integration (per user).

## Backlog
- **P0**: User upgrades Apollo (paid) → real leads + real delivery end-to-end. Connect Twilio for auto WhatsApp (#3).
- **P1**: Reply/inbox tracking (IMAP) instead of manual "mark replied"; per-user email settings in UI; deliverability warm-up; CSV lead import.
- **P2**: Multi-step sequence editor, A/B subjects, analytics per campaign, landing/marketing page for selling the product.

## Next Tasks
- #3 Twilio WhatsApp auto-send (needs creds). Then revisit Apollo once upgraded.
