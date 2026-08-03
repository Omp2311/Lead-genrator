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
- **2026-08-02**: JWT auth + admin seed. AI lead+email pipeline. Dashboard (stats + 7-day chart + autopilot), Leads, Outbox, Automation, Activity. Daily scheduler. (Tested 100%.)
- **2026-08-03 (this session)**:
  - **Live email via Gmail SMTP** — verified real delivery (send to omprakashraj100078@gmail.com returned sent, simulated=false).
  - **Follow-up sequences** — 2 AI follow-ups auto-scheduled per lead (+3d, +6d); cancel on "mark replied"; scheduler sends due ones.
  - **Profile & Skills page** — skills/headline/experience/offer/tone/targeting; tailors leads + project pitches.
  - **Project details per lead** — project_idea + estimated_value shown on Leads.
  - **Editable drafts + manual send** — emails created as drafts; per-email Edit/Send + "Send all"; real SMTP on click.
  - Integrations status panel + honest LIVE/OFF/blocked indicators; test-email + process-follow-ups buttons.
  - Backfill defaults in get_or_create_settings. (Tested: FE 100%, BE 100% after fix.)

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
