# OutreachPilot — PRD

## Original Problem Statement
Build a website that fully automates cold outreach: automatically find real client leads, send 100+ cold emails daily hands-free, and send proposals to WhatsApp when a phone number exists. Target: Dubai, USA, and high-IT-density cities. Position it as a sellable product.

## Architecture
- **Backend**: FastAPI + PostgreSQL (asyncpg, raw SQL, no ORM). Single-file monolith (`backend/server.py`). JWT auth (httpOnly cookies). Anthropic (default) + OpenAI as LLM providers, one auto-falls back to the other. Background asyncio scheduler (hourly: reply scan → due follow-ups → daily-once autopilot run per workspace).
- **Frontend**: React 19 + Router + Tailwind + shadcn, "Tactical Dark Mode" (cyan accent). Recharts, sonner.
- **Multi-tenancy**: `users.owner_id` — a NULL owner_id means the login owns its own workspace; a set owner_id means it's an invited teammate sharing that owner's entire workspace (leads/emails/settings/pipeline/etc.). Every data query resolves through `tenant_id(user)`, never the raw login id.
- **Integrations** (all auto-activate once their env keys are set — nothing is hardcoded live): SMTP or Resend (email), Apollo (real leads, falls back to AI-generated demo leads), Twilio (WhatsApp) or plain `wa.me` links, IMAP (reply detection + body fetch for intent classification), Stripe (billing), OpenAI TTS (voice notes).

## User Personas
- Freelancer / agency owner (full-stack + GenAI dev) who wants a hands-free engine that finds clients needing THEIR skills and pitches tailored projects.
- Agencies running outreach on behalf of / alongside a small team — team seats share one workspace.

## Routing
- `/` public Landing · `/login` · `/register` (accepts `?ref=CODE`) · `/app` (protected) with nested:
  `` (Dashboard) `/profile` `/leads` `/pipeline` `/outbox` `/inboxes` `/automation` `/analytics`
  `/team` `/billing` `/referrals` `/docs` `/activity`.
- Public, unauthenticated: `/api/unsubscribe/{token}`, `/api/t/{id}.gif` + `/api/c/{id}` (tracking),
  `/api/voice/{id}.mp3`, `/api/billing/webhook`, `/api/public/v1/*` (API-key auth, not cookies).

## Implemented
**Pre-Tier** (original build): JWT auth + admin seed, AI lead+email pipeline, Dashboard/Leads/Outbox/Automation/Activity, daily scheduler, Gmail SMTP, 2-step follow-ups, Profile & Skills, IMAP reply detection (sender-only), public Landing page.

**Tier 1** — production-safety foundation: suppression list + unsubscribe links; multi-inbox rotation with age-based warm-up ramp and per-inbox daily caps (falls back to the legacy single env-configured inbox if none are added); open/click tracking; CSV lead import.

**Tier 2** — differentiation: user-defined multi-step follow-up sequences (replaces the fixed 2-step ramp); CRM pipeline (Kanban stages, notes, auto-advance on send/reply); reply-intent classification (fetches the actual IMAP body now, not just the sender); A/B subject-line testing; meeting-booking link CTA.

**Tier 3** — monetization: team seats (shared workspace via `owner_id`); Stripe billing (checkout/portal/webhook) with plan-based caps on inboxes/seats/daily send volume.

**Tier 4** — moat features: live-signal personalization (pulls a lead's own homepage title/meta, no paid search API); local deliverability/spam-score heuristic; AI-drafted replies to interested/question responses; voice-note personalization (OpenAI TTS).

**Tier 5** — closing the backlog: white-label branding (in-app sidebar only); referral tracking (no auto reward-crediting); public API + API keys for Zapier/Make-style generic webhook integrations; Docs page (API reference + real changelog); AI-drafted LinkedIn connection/message text (manual copy-paste only — deliberately not automated).

## Integration Status / Limitations (as of 2026-08-05, this dev environment)
- **Email**: no SMTP/Resend/Apollo/Twilio/Stripe/OpenAI keys are set in `backend/.env` in this environment — every integration degrades to its documented fallback (simulated sends, AI demo leads, `wa.me` links, etc.) rather than erroring. Set the real keys to go live.
- **Reply detection / intent / auto-drafted replies**: require `SMTP_USER`/`SMTP_PASSWORD` (IMAP) + an LLM key; untested against a live inbox in this environment.
- **Voice notes**: require `OPENAI_API_KEY` specifically (TTS). Only the error paths (missing key → 400, unknown email → 404) were verified live here — the actual `audio.speech.create` call shape was written from SDK docs, not exercised.
- **Billing**: requires real Stripe test-mode keys (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, three price IDs) to actually checkout; the tenant/plan-limit logic around it was verified live with a manually-set plan.
- **LinkedIn**: intentionally not automated (ToS/account-ban risk) — text-drafting only.

## Explicit scope-cuts (decided, not oversights)
- No self-service teammate invite email or password-reset flow anywhere in the app — an owner sets a teammate's password directly and shares it out-of-band.
- No automated referral reward-crediting — referrals are tracked and shown, not paid out automatically.
- No published Zapier App Store listing — the public API is generic-webhook-compatible (what Zapier's/Make's "Webhooks"/"HTTP" actions use today), not a reviewed/listed native app.
- No LinkedIn automation of any kind.

## Backlog (genuinely not built)
- Deeper live-signal personalization via a real search API (current version is a plain homepage fetch, not a search engine).
- A published/native Zapier app listing (vs. today's generic-webhook-compatible API).
- Self-service team invite emails + password reset (any account, not just teammates).
- Automated referral reward-crediting (e.g. auto-applying a Stripe coupon after N referrals).
