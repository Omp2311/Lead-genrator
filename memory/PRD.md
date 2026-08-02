# OutreachPilot — PRD

## Original Problem Statement
Build a website that fully automates cold outreach: automatically find real client leads, send 100+ cold emails daily hands-free, and send proposals to WhatsApp when a phone number exists. Target: Dubai, USA, and high-IT-density cities.

## Architecture
- **Backend**: FastAPI + MongoDB (motor). JWT auth via httpOnly cookies. Emergent LLM key (OpenAI gpt-5.4) for lead generation & email copywriting. Background asyncio scheduler for daily autopilot.
- **Frontend**: React 19 + React Router + Tailwind + shadcn, "Tactical Dark Mode" design (Cabinet Grotesk / IBM Plex Sans, cyan accent). Recharts for volume chart, sonner toasts.

## User Personas
- Solo founder / agency owner (full-stack dev) who wants a hands-free B2B lead + outreach engine.

## Core Requirements (static)
- Auth (register/login/logout/session).
- AI lead discovery targeting chosen regions/industries.
- AI-personalized cold email per lead.
- WhatsApp proposal links for leads with phone numbers.
- Daily autopilot + manual "run now".
- Dashboard stats, leads list, outbox, activity log, automation settings.

## Implemented (2026-08-02)
- JWT cookie auth + admin seed (admin@outreachpilot.com / admin123).
- `/api/automation/run` → AI generates realistic leads + personalized emails, stores leads/emails/activity, builds wa.me WhatsApp links.
- Dashboard (stats + 7-day email volume chart + autopilot status), Leads, Outbox (email/whatsapp tabs), Automation (settings: daily target, regions, industries, offer, tone, autopilot toggle), Activity timeline.
- Hourly background scheduler runs daily for users with autopilot enabled.
- Verified: backend 14/14 pytest, frontend Playwright — 100%.

## Known Mocks / Limitations
- **Email sending is SIMULATED** (stored with status "sent"; no real SMTP/provider). Real sending needs a provider key (Resend/SendGrid).
- **Lead data is AI-generated (realistic demo)**, not from a live data provider (Apollo/Hunter need paid API keys).
- WhatsApp = click-to-send wa.me links (semi-manual), not automated WhatsApp Business API.

## Backlog
- **P0**: Real email sending (Resend/SendGrid) once user provides key; real lead provider integration.
- **P1**: Twilio WhatsApp automated send; reply tracking / inbox; per-lead approval before send; CSV lead import.
- **P2**: Follow-up sequences, A/B subject testing, deliverability warm-up, analytics per campaign.

## Next Tasks
- Connect a real email provider and lead source when keys are available.
