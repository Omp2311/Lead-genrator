from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import logging
import uuid
import json
import secrets
import asyncio
import csv
import io
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional
from urllib.parse import quote

import bcrypt
import jwt
import asyncpg
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, UploadFile, File
from fastapi.responses import RedirectResponse
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr

import httpx
import smtplib
from email.message import EmailMessage
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
import stripe

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ['DATABASE_URL']
pool: asyncpg.Pool = None  # set on startup

async def _init_connection(conn):
    # Treat uuid columns as plain strings everywhere (no uuid.UUID juggling in route code).
    await conn.set_type_codec('uuid', encoder=str, decoder=str, schema='pg_catalog', format='text')

def rec(r):
    return dict(r) if r is not None else None

def recs(rows):
    return [dict(r) for r in rows]

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = "HS256"

# Optional third-party providers (features go live automatically when keys are set)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev").strip()
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").replace(" ", "").strip()
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com").strip()
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993") or 993)
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "").strip()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()
BACKEND_URL = os.environ.get("BACKEND_URL", "").strip().rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").strip().rstrip("/")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_PRICE_IDS = {
    "starter": os.environ.get("STRIPE_PRICE_STARTER", "").strip(),
    "pro": os.environ.get("STRIPE_PRICE_PRO", "").strip(),
    "agency": os.environ.get("STRIPE_PRICE_AGENCY", "").strip(),
}
stripe.api_key = STRIPE_SECRET_KEY

PLAN_LIMITS = {
    "starter": {"max_inboxes": 2, "max_team_seats": 1, "max_daily_target": 50},
    "pro": {"max_inboxes": 5, "max_team_seats": 3, "max_daily_target": 300},
    "agency": {"max_inboxes": 15, "max_team_seats": 15, "max_daily_target": 1000},
}

_apollo_ok = None  # None=untested, True=working, False=blocked (e.g. free plan)

def _email_configured() -> bool:
    return bool((SMTP_HOST and SMTP_USER and SMTP_PASSWORD) or RESEND_API_KEY)

def _default_email_cfg() -> Optional[dict]:
    """Legacy global env-configured sender, used when a user has no Inboxes set up."""
    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
        return {"provider": "smtp", "smtp_host": SMTP_HOST, "smtp_port": SMTP_PORT,
                "smtp_user": SMTP_USER, "smtp_password": SMTP_PASSWORD, "from_email": SENDER_EMAIL}
    if RESEND_API_KEY:
        return {"provider": "resend", "resend_api_key": RESEND_API_KEY, "from_email": SENDER_EMAIL}
    return None

async def integrations_status(user_id: str = None) -> dict:
    inbox_count = 0
    if user_id and pool:
        inbox_count = await pool.fetchval(
            "SELECT count(*) FROM inboxes WHERE user_id=$1 AND is_active=true", user_id) or 0
    return {
        "email_live": _email_configured() or inbox_count > 0,
        "email_provider": "smtp" if (SMTP_HOST and SMTP_USER) else ("resend" if RESEND_API_KEY else ("inbox" if inbox_count else None)),
        "sender_email": SENDER_EMAIL if _email_configured() else None,
        "inboxes_configured": inbox_count,
        "leads_live": bool(APOLLO_API_KEY) and _apollo_ok is not False,
        "leads_blocked": bool(APOLLO_API_KEY) and _apollo_ok is False,
        "whatsapp_live": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM),
        "reply_detection_live": bool(SMTP_USER and SMTP_PASSWORD),
    }

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("outreachpilot")

app = FastAPI(title="OutreachPilot")
api_router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(hours=12)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "type": "refresh",
               "exp": datetime.now(timezone.utc) + timedelta(days=7)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def set_auth_cookies(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, httponly=True, secure=True,
                        samesite="none", max_age=43200, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = rec(await pool.fetchrow("SELECT * FROM users WHERE id=$1", payload["sub"]))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def tenant_id(user: dict) -> str:
    """The workspace whose leads/emails/settings/etc. this login should read & write.

    Team members (users.owner_id set) share the owner's entire workspace; an owner
    (owner_id NULL) is their own tenant. Every data-scoping query must use this, not
    the login's own id, so invited teammates see and act on the shared workspace.
    """
    return user.get("owner_id") or user["id"]

async def plan_limits_for(tid: str) -> dict:
    plan = await pool.fetchval("SELECT plan FROM users WHERE id=$1", tid) or "starter"
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class RegisterInput(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class RunInput(BaseModel):
    count: int = 8
    region: Optional[str] = None
    industry: Optional[str] = None
    offer: Optional[str] = None
    tone: Optional[str] = None

class SettingsInput(BaseModel):
    daily_target: int = 100
    auto_enabled: bool = True
    regions: List[str] = ["Dubai, UAE", "USA", "San Francisco", "New York"]
    industries: List[str] = ["SaaS", "Fintech", "E-commerce", "IT Services"]
    offer: str = "Custom AI-powered software & full-stack development services"
    sender_name: str = "Alex"
    tone: str = "confident and concise"
    skills: List[str] = ["Python", "Django", "FastAPI", "React", "Node.js", "Generative AI"]
    headline: str = "Full-stack & GenAI engineer building custom software for growing companies"
    experience: str = "5+ years shipping full-stack and AI products for startups and enterprises"
    meeting_link: str = ""

class EmailUpdate(BaseModel):
    to_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None

class LeadUpdate(BaseModel):
    stage: Optional[str] = None
    notes: Optional[str] = None

class SequenceStepInput(BaseModel):
    delay_days: int = 3
    angle: str = ""

class TeamMemberInput(BaseModel):
    name: str
    email: EmailStr
    password: str

class CheckoutInput(BaseModel):
    plan: str

class InboxInput(BaseModel):
    label: str = "Inbox"
    provider: str = "smtp"  # 'smtp' | 'resend'
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    resend_api_key: str = ""
    from_email: str = ""
    daily_cap: int = 30
    warmup_enabled: bool = True
    is_active: bool = True

class SuppressionInput(BaseModel):
    email: EmailStr
    reason: str = "manual"


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------
def _extract_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    start = min([i for i in [text.find("["), text.find("{")] if i != -1], default=0)
    return json.loads(text[start:])

async def _call_anthropic(system: str, prompt: str) -> str:
    resp = await anthropic_client.messages.create(
        model=ANTHROPIC_MODEL, max_tokens=4096, system=system,
        messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in resp.content if b.type == "text")

async def _call_openai(system: str, prompt: str) -> str:
    resp = await openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
    return resp.choices[0].message.content

async def llm_call(system: str, prompt: str) -> str:
    providers = [LLM_PROVIDER] + [p for p in ("anthropic", "openai") if p != LLM_PROVIDER]
    last_err = None
    for provider in providers:
        if provider == "anthropic" and anthropic_client:
            try:
                return await _call_anthropic(system, prompt)
            except Exception as e:
                logger.error(f"Anthropic call failed: {e}")
                last_err = e
        elif provider == "openai" and openai_client:
            try:
                return await _call_openai(system, prompt)
            except Exception as e:
                logger.error(f"OpenAI call failed: {e}")
                last_err = e
    raise RuntimeError(f"No LLM provider available/working (set ANTHROPIC_API_KEY and/or "
                       f"OPENAI_API_KEY in backend/.env). Last error: {last_err}")

async def generate_leads(settings: dict, count: int, region=None, industry=None):
    regions = [region] if region else settings.get("regions", ["Dubai, UAE", "USA"])
    industries = [industry] if industry else settings.get("industries", ["SaaS", "IT Services"])
    skills = settings.get("skills", ["Python", "React", "GenAI"])
    system = ("You are a B2B sales research assistant that produces realistic, plausible "
              "prospect company profiles for a cold outreach demo. Output ONLY valid JSON.")
    prompt = f"""Generate {count} realistic B2B prospect leads for a freelancer/agency doing cold outreach.
The sender's skills: {', '.join(skills)}. Offer: {settings.get('offer','custom software')}.
Target regions: {', '.join(regions)}. Target industries: {', '.join(industries)}.
Focus on high-IT-density cities (Dubai, Silicon Valley, New York, Austin, London).
Each lead is a decision maker (Founder/CTO/Head of Growth) at a plausible company that would
plausibly NEED the sender's skills.
Return a JSON array. Each item MUST have keys:
"company", "contact_name", "title", "email" (plausible corporate email),
"phone" (E.164 with country code, or empty string for ~30% of them),
"location", "industry", "website", "pain_point" (1 short sentence specific to them),
"project_idea" (1 sentence: a concrete project the sender could build for them using their skills),
"estimated_value" (a realistic project budget range in USD, e.g. "$4k–$8k").
Return ONLY the JSON array, no prose."""
    raw = await llm_call(system, prompt)
    return _extract_json(raw)

def subject_variant(idx: int) -> str:
    """Alternates two subject-line styles across a batch so open rates can be A/B compared."""
    return "A" if idx % 2 == 0 else "B"

async def generate_emails(settings: dict, leads: List[dict]):
    system = ("You are an expert cold email copywriter. Write short, personalized, "
              "high-converting cold emails. Output ONLY valid JSON.")
    sender = settings.get("sender_name", "Alex")
    offer = settings.get("offer", "custom software development")
    tone = settings.get("tone", "confident and concise")
    meeting_link = (settings.get("meeting_link") or "").strip()
    style_by_variant = {"A": "curiosity-driven question", "B": "direct value statement"}
    compact = [{"i": idx, "company": l.get("company"), "contact_name": l.get("contact_name"),
                "title": l.get("title"), "pain_point": l.get("pain_point"),
                "project_idea": l.get("project_idea"), "industry": l.get("industry"),
                "subject_style": style_by_variant[subject_variant(idx)]}
               for idx, l in enumerate(leads)]
    meeting_note = (f'\nA booking link is available ({meeting_link}) — you may offer it as an '
                    f'alternative to proposing a call time yourself.' if meeting_link else "")
    prompt = f"""Write a personalized cold email for each prospect below.
Sender name: {sender}. Offer: {offer}. Tone: {tone}.
Rules: <=120 words, one clear CTA (a 15-min call), reference their pain_point naturally,
and pitch the specific "project_idea" as what you could build for them. No fluff, no
"I hope this finds you well". Subject line <=6 words, matching each prospect's "subject_style".{meeting_note}
Prospects: {json.dumps(compact)}
Return a JSON array where each item has: "i" (matching index), "subject", "body".
Body should use \\n for line breaks and end with "{sender}". Return ONLY JSON."""
    raw = await llm_call(system, prompt)
    return _extract_json(raw)

def whatsapp_link(phone: str, company: str, sender: str, offer: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    msg = (f"Hi, this is {sender}. I came across {company} and put together a quick "
           f"proposal on how we can help with {offer}. Do you have 2 minutes?")
    return f"https://wa.me/{digits}?text={quote(msg)}"


# ---------------------------------------------------------------------------
# Suppression list (unsubscribes / manual opt-outs) — checked before every send
# ---------------------------------------------------------------------------
async def is_suppressed(user_id: str, email: str) -> bool:
    if not (user_id and email):
        return False
    return bool(await pool.fetchval(
        "SELECT 1 FROM suppressions WHERE user_id=$1 AND email=$2", user_id, email.strip().lower()))

async def add_suppression(user_id: str, email: str, reason: str = "unsubscribed"):
    email = (email or "").strip().lower()
    if not (user_id and email):
        return
    await pool.execute("""
        INSERT INTO suppressions (id, user_id, email, reason) VALUES ($1,$2,$3,$4)
        ON CONFLICT (user_id, email) DO NOTHING
    """, str(uuid.uuid4()), user_id, email, reason)
    await pool.execute("UPDATE leads SET suppressed=true WHERE user_id=$1 AND email=$2", user_id, email)

def unsubscribe_token(user_id: str, email: str) -> str:
    return jwt.encode({"type": "unsub", "user_id": user_id, "email": email.strip().lower()},
                      JWT_SECRET, algorithm=JWT_ALGORITHM)

def unsubscribe_url(user_id: str, email: str) -> Optional[str]:
    if not (BACKEND_URL and user_id and email):
        return None
    return f"{BACKEND_URL}/api/unsubscribe/{unsubscribe_token(user_id, email)}"


# ---------------------------------------------------------------------------
# Sending inboxes: multi-inbox rotation, warm-up ramp, per-inbox daily caps
# ---------------------------------------------------------------------------
async def pick_inbox(user_id: str) -> Optional[dict]:
    """Least-recently-used active inbox that still has daily-cap/warm-up headroom today."""
    if not user_id:
        return None
    today = date.today()
    rows = recs(await pool.fetch(
        "SELECT * FROM inboxes WHERE user_id=$1 AND is_active=true ORDER BY last_used_at NULLS FIRST",
        user_id))
    for row in rows:
        sent_today = row["sent_today"] if row.get("sent_today_date") == today else 0
        cap = row["daily_cap"]
        if row.get("warmup_enabled") and row.get("created_at"):
            # Ramp: 5/day on day 0, +5/day, until the inbox's configured daily_cap is reached.
            # Computed from age rather than a mutable counter, so it self-corrects even if
            # the scheduler was down for a while.
            days_active = max(0, (today - row["created_at"].date()).days)
            cap = min(cap, 5 + days_active * 5)
        if sent_today < cap:
            return row
    return None

def _inbox_to_cfg(inbox: dict) -> dict:
    if inbox["provider"] == "resend":
        return {"provider": "resend", "resend_api_key": inbox["resend_api_key"], "from_email": inbox["from_email"]}
    return {"provider": "smtp", "smtp_host": inbox["smtp_host"], "smtp_port": inbox["smtp_port"],
            "smtp_user": inbox["smtp_user"], "smtp_password": inbox["smtp_password"],
            "from_email": inbox["from_email"]}

async def record_inbox_send(inbox_id: str):
    today = date.today()
    row = rec(await pool.fetchrow("SELECT sent_today, sent_today_date FROM inboxes WHERE id=$1", inbox_id))
    if not row:
        return
    sent_today = row["sent_today"] if row["sent_today_date"] == today else 0
    await pool.execute(
        "UPDATE inboxes SET sent_today=$1, sent_today_date=$2, last_used_at=$3 WHERE id=$4",
        sent_today + 1, today, datetime.now(timezone.utc), inbox_id)


# ---------------------------------------------------------------------------
# Delivery: SMTP/Resend email + Twilio WhatsApp (auto-live when keys present)
# ---------------------------------------------------------------------------
_PIXEL_GIF = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01'
              b'\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')

def _body_to_html(body: str, email_id: str = None, unsub_url: str = None) -> str:
    safe = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = ("<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:14px;"
            "line-height:1.6;color:#111\">" + safe.replace("\n", "<br>"))
    if unsub_url:
        html += (f'<div style="margin-top:24px;padding-top:12px;border-top:1px solid #eee;'
                 f'font-size:11px;color:#999">Don\'t want to hear from us again? '
                 f'<a href="{unsub_url}" style="color:#999">Unsubscribe</a>.</div>')
    html += "</div>"
    if email_id and BACKEND_URL:
        html += f'<img src="{BACKEND_URL}/api/t/{email_id}.gif" width="1" height="1" style="display:none" alt="">'
    return html

def _plaintext_with_footer(body: str, unsub_url: str = None) -> str:
    if not unsub_url:
        return body
    return f"{body}\n\n---\nUnsubscribe: {unsub_url}"

async def send_email(to_email: str, subject: str, body: str, allow: bool = True,
                     user_id: str = None, email_id: str = None, cfg: dict = None) -> dict:
    if not allow:
        return {"status": "sent", "simulated": True, "provider_id": None, "error": None}
    if await is_suppressed(user_id, to_email):
        return {"status": "suppressed", "simulated": False, "provider_id": None,
                "error": "Recipient has unsubscribed"}

    cfg = cfg or _default_email_cfg()
    if not cfg:
        return {"status": "sent", "simulated": True, "provider_id": None, "error": None}

    unsub = unsubscribe_url(user_id, to_email)
    html_body = _body_to_html(body, email_id=email_id, unsub_url=unsub)
    text_body = _plaintext_with_footer(body, unsub)

    if cfg["provider"] == "smtp":
        try:
            await asyncio.to_thread(_smtp_send_sync, cfg, to_email, subject, text_body, html_body)
            return {"status": "sent", "simulated": False, "provider_id": "smtp", "error": None}
        except Exception as e:
            logger.error(f"SMTP send failed: {e}")
            return {"status": "failed", "simulated": False, "provider_id": None, "error": str(e)}
    try:
        import resend
        resend.api_key = cfg["resend_api_key"]
        params = {"from": cfg["from_email"], "to": [to_email], "subject": subject, "html": html_body}
        res = await asyncio.to_thread(resend.Emails.send, params)
        pid = res.get("id") if isinstance(res, dict) else getattr(res, "id", None)
        return {"status": "sent", "simulated": False, "provider_id": pid, "error": None}
    except Exception as e:
        logger.error(f"Resend send failed: {e}")
        return {"status": "failed", "simulated": False, "provider_id": None, "error": str(e)}


def _smtp_send_sync(cfg: dict, to_email: str, subject: str, text_body: str, html_body: str):
    msg = EmailMessage()
    msg["From"] = cfg["from_email"]
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30) as s:
        s.ehlo()
        s.starttls()
        s.login(cfg["smtp_user"], cfg["smtp_password"])
        s.send_message(msg)

async def send_whatsapp(to_phone: str, body: str, allow: bool = True) -> dict:
    if not allow or not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM):
        return {"status": "ready", "simulated": True, "sid": None, "error": None}
    try:
        from twilio.rest import Client
        tw = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = await asyncio.to_thread(
            lambda: tw.messages.create(
                from_=f"whatsapp:{TWILIO_WHATSAPP_FROM}",
                to=f"whatsapp:+{''.join(c for c in to_phone if c.isdigit())}",
                body=body))
        return {"status": "sent", "simulated": False, "sid": msg.sid, "error": None}
    except Exception as e:
        logger.error(f"Twilio WhatsApp failed: {e}")
        return {"status": "failed", "simulated": False, "sid": None, "error": str(e)}


# ---------------------------------------------------------------------------
# Real lead sourcing via Apollo (falls back to AI demo leads)
# ---------------------------------------------------------------------------
async def fetch_apollo_leads(regions, industries, count) -> List[dict]:
    global _apollo_ok
    headers = {"x-api-key": APOLLO_API_KEY, "Content-Type": "application/json",
               "Accept": "application/json", "Cache-Control": "no-cache"}
    titles = ["CEO", "CTO", "Founder", "VP Engineering", "IT Director", "Head of Growth"]
    params = []
    for r in regions:
        params.append(("person_locations[]", r))
    for t in titles:
        params.append(("person_titles[]", t))
    for ind in industries:
        params.append(("q_organization_keyword_tags[]", ind))
    params += [("page", 1), ("per_page", min(count, 25))]
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.post("https://api.apollo.io/api/v1/mixed_people/api_search",
                            params=params, headers=headers, json={})
    if resp.is_error:
        if resp.status_code in (401, 403):
            _apollo_ok = False
        raise RuntimeError(f"Apollo search error {resp.status_code}")
    _apollo_ok = True
    people = resp.json().get("people", [])[:count]

    ids = [p["id"] for p in people if p.get("id")]
    enriched = {}
    if ids:
        try:
            details = [{"id": i} for i in ids[:10]]
            async with httpx.AsyncClient(timeout=40) as c:
                er = await c.post("https://api.apollo.io/api/v1/people/bulk_match",
                                  params=[("reveal_personal_emails", "false")],
                                  headers=headers, json={"details": details})
            if not er.is_error:
                for m in er.json().get("matches", []) or []:
                    if m and m.get("id"):
                        enriched[m["id"]] = m
        except Exception as e:
            logger.warning(f"Apollo enrichment skipped: {e}")

    leads = []
    for p in people:
        m = enriched.get(p.get("id"), p)
        org = m.get("organization") or p.get("organization") or {}
        phone = ""
        for pn in (m.get("phone_numbers") or []):
            if pn.get("sanitized_number"):
                phone = pn["sanitized_number"]
                break
        leads.append({
            "company": org.get("name") or p.get("organization_name") or "",
            "contact_name": " ".join(x for x in [p.get("first_name"), p.get("last_name")] if x),
            "title": p.get("title") or "",
            "email": m.get("email") or "",
            "phone": phone,
            "location": ", ".join(x for x in [p.get("city"), p.get("state"), p.get("country")] if x),
            "industry": (industries[0] if industries else ""),
            "website": org.get("website_url") or (("https://" + org["primary_domain"]) if org.get("primary_domain") else ""),
            "pain_point": "",
        })
    return [l for l in leads if l["email"]]

async def source_leads(settings: dict, count: int, region=None, industry=None):
    regions = [region] if region else settings.get("regions", ["Dubai, UAE", "United States"])
    industries = [industry] if industry else settings.get("industries", ["SaaS", "IT Services"])
    if APOLLO_API_KEY:
        try:
            leads = await fetch_apollo_leads(regions, industries, count)
            if leads:
                return leads, "apollo"
        except Exception as e:
            logger.error(f"Apollo failed, using AI leads: {e}")
    ai = await generate_leads(settings, count, region, industry)
    return ai, "ai"


DEFAULT_SEQUENCE_STEPS = [
    {"step_order": 1, "delay_days": 3,
     "angle": "Nudge: reference the first email lightly, add one new angle/proof point, <=70 words."},
    {"step_order": 2, "delay_days": 6,
     "angle": "Breakup: short, friendly last touch, create urgency without pressure, <=55 words."},
]

async def get_sequence_steps(user_id: str) -> List[dict]:
    """User-defined follow-up sequence. Lazily seeded with the classic 2-step nudge/breakup ramp."""
    rows = recs(await pool.fetch(
        "SELECT * FROM sequence_steps WHERE user_id=$1 ORDER BY step_order", user_id))
    if rows:
        return rows
    for d in DEFAULT_SEQUENCE_STEPS:
        await pool.execute(
            "INSERT INTO sequence_steps (id, user_id, step_order, delay_days, angle) VALUES ($1,$2,$3,$4,$5)",
            str(uuid.uuid4()), user_id, d["step_order"], d["delay_days"], d["angle"])
    return recs(await pool.fetch(
        "SELECT * FROM sequence_steps WHERE user_id=$1 ORDER BY step_order", user_id))

async def generate_followups(settings: dict, leads: List[dict], steps: List[dict]):
    """One follow-up email per lead per step in the user's sequence, for leads that don't reply."""
    if not steps:
        return []
    system = ("You are an expert cold-email copywriter writing polite, value-add "
              "FOLLOW-UP emails for prospects who did not reply. Output ONLY valid JSON.")
    sender = settings.get("sender_name", "Alex")
    offer = settings.get("offer", "custom software development")
    compact = [{"i": idx, "company": l.get("company"), "contact_name": l.get("contact_name"),
                "title": l.get("title"), "pain_point": l.get("pain_point"),
                "industry": l.get("industry")} for idx, l in enumerate(leads)]
    steps_desc = "\n".join(f'Follow-up #{i + 1}: {s.get("angle") or "brief, polite follow-up"}'
                           for i, s in enumerate(steps))
    prompt = f"""For each prospect, write ONE short follow-up email per step below (they didn't reply
to the earlier email(s) in the sequence).
Sender: {sender}. Offer: {offer}.
{steps_desc}
All end with "{sender}". Subjects <=5 words, can start with "Re:".
Prospects: {json.dumps(compact)}
Return a JSON array where each item is {{"i": <index>, "followups": [{{"subject","body"}}, ...]}}
with exactly {len(steps)} followup(s) per prospect, in the same order as the steps above.
Return ONLY JSON."""
    raw = await llm_call(system, prompt)
    return _extract_json(raw)


# ---------------------------------------------------------------------------
# Core automation run
# ---------------------------------------------------------------------------
async def execute_run(user_id: str, count: int, region=None, industry=None,
                      offer=None, tone=None, source="manual"):
    settings = await get_or_create_settings(user_id)
    if offer:
        settings = {**settings, "offer": offer}
    if tone:
        settings = {**settings, "tone": tone}

    leads, lead_source = await source_leads(settings, count, region, industry)
    has_inbox = bool(await pool.fetchval(
        "SELECT count(*) FROM inboxes WHERE user_id=$1 AND is_active=true", user_id))
    deliver = (_email_configured() or has_inbox) and lead_source == "apollo"
    emails = await generate_emails(settings, leads)
    email_by_i = {e.get("i"): e for e in emails}
    steps = await get_sequence_steps(user_id)
    try:
        fups = await generate_followups(settings, leads, steps)
        fups_by_i = {f.get("i"): (f.get("followups") or []) for f in fups}
    except Exception as e:
        logger.error(f"Follow-up generation failed: {e}")
        fups_by_i = {}

    now_dt = datetime.now(timezone.utc)
    sender = settings.get("sender_name", "Alex")
    created_emails = 0
    created_leads = 0
    real_sent = 0
    wa_sent = 0

    for idx, lead in enumerate(leads):
        lead_id = str(uuid.uuid4())
        phone = (lead.get("phone") or "").strip()
        to_email = lead.get("email", "")
        suppressed_lead = await is_suppressed(user_id, to_email) if to_email else False
        wa = whatsapp_link(phone, lead.get("company", ""), sender,
                           settings.get("offer", "")) if phone else None
        await pool.execute("""
            INSERT INTO leads (id, user_id, company, contact_name, title, email, phone, location,
                                industry, website, pain_point, project_idea, estimated_value,
                                whatsapp_link, created_at, source, lead_source, replied, suppressed)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,false,$18)
        """, lead_id, user_id, lead.get("company", ""), lead.get("contact_name", ""),
             lead.get("title", ""), to_email, phone, lead.get("location", ""),
             lead.get("industry", ""), lead.get("website", ""), lead.get("pain_point", ""),
             lead.get("project_idea", ""), lead.get("estimated_value", ""), wa, now_dt,
             source, lead_source, suppressed_lead)
        created_leads += 1

        em = email_by_i.get(idx, {})
        subject = em.get("subject", "Quick question")
        body = em.get("body", "")
        # Emails are created as editable DRAFTS — user sends them from the Outbox.
        # Suppressed (unsubscribed) recipients get a distinct status and no follow-ups.
        await pool.execute("""
            INSERT INTO emails (id, user_id, lead_id, company, contact_name, to_email, subject, body,
                                 channel, step, type, status, simulated, error, created_at,
                                 deliverable, lead_source, sent_at, variant)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'email',1,'initial',$9,false,NULL,$10,$11,$12,NULL,$13)
        """, str(uuid.uuid4()), user_id, lead_id, lead.get("company", ""),
             lead.get("contact_name", ""), to_email, subject, body,
             "suppressed" if suppressed_lead else "draft", now_dt, deliver, lead_source,
             subject_variant(idx))
        created_emails += 1

        # Schedule follow-ups (sent later if the lead hasn't replied) — skipped for suppressed leads
        if not suppressed_lead:
            for step_i, fu in enumerate(fups_by_i.get(idx, [])[:len(steps)]):
                delay = steps[step_i]["delay_days"] if step_i < len(steps) else 6
                scheduled_for = now_dt + timedelta(days=delay)
                await pool.execute("""
                    INSERT INTO emails (id, user_id, lead_id, company, contact_name, to_email, subject, body,
                                         channel, step, type, status, simulated, error, created_at, sent_at,
                                         deliverable, lead_source, scheduled_for)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'email',$9,'follow_up','scheduled',false,NULL,$10,NULL,$11,$12,$13)
                """, str(uuid.uuid4()), user_id, lead_id, lead.get("company", ""),
                     lead.get("contact_name", ""), to_email, fu.get("subject", "Re: quick follow-up"),
                     fu.get("body", ""), step_i + 2, now_dt, deliver, lead_source, scheduled_for)

        # WhatsApp proposal
        if wa:
            wa_body = (f"Hi {lead.get('contact_name','').split(' ')[0]}, this is {sender}. "
                       f"I put together a quick proposal for {lead.get('company','')} on "
                       f"{settings.get('offer','')}. Do you have 2 minutes?")
            wa_res = await send_whatsapp(phone, wa_body, allow=(lead_source == "apollo"))
            if wa_res["status"] == "sent" and not wa_res.get("simulated"):
                wa_sent += 1
            await pool.execute("""
                INSERT INTO emails (id, user_id, lead_id, company, contact_name, to_email, subject, body,
                                     channel, step, type, status, simulated, error, whatsapp_link,
                                     created_at, sent_at)
                VALUES ($1,$2,$3,$4,$5,$6,'WhatsApp proposal',$7,'whatsapp',1,'initial',$8,$9,$10,$11,$12,$13)
            """, str(uuid.uuid4()), user_id, lead_id, lead.get("company", ""),
                 lead.get("contact_name", ""), phone, wa_body, wa_res["status"],
                 wa_res.get("simulated", False), wa_res.get("error"), wa, now_dt,
                 now_dt if wa_res["status"] == "sent" else None)

    src_label = "Apollo" if lead_source == "apollo" else "AI"
    await pool.execute("""
        INSERT INTO activity (id, user_id, type, message, created_at)
        VALUES ($1,$2,$3,$4,$5)
    """, str(uuid.uuid4()), user_id, source,
         (f"Outreach run: {created_leads} {src_label} leads discovered, "
          f"{created_emails} personalized emails drafted (ready to send), "
          f"follow-ups scheduled."), now_dt)
    return {"leads": created_leads, "emails": created_emails, "run_at": now_dt.isoformat(),
            "real_sent": real_sent, "whatsapp_sent": wa_sent, "lead_source": lead_source,
            "email_live": _email_configured()}


async def process_due_followups(user_id: str = None) -> int:
    now = datetime.now(timezone.utc)
    if user_id:
        due = recs(await pool.fetch(
            "SELECT * FROM emails WHERE type='follow_up' AND status='scheduled' "
            "AND scheduled_for<=$1 AND user_id=$2", now, user_id))
    else:
        due = recs(await pool.fetch(
            "SELECT * FROM emails WHERE type='follow_up' AND status='scheduled' "
            "AND scheduled_for<=$1", now))
    sent = 0
    for fu in due:
        lead = rec(await pool.fetchrow("SELECT * FROM leads WHERE id=$1", fu.get("lead_id")))
        if lead and lead.get("replied"):
            await pool.execute("UPDATE emails SET status='cancelled' WHERE id=$1", fu["id"])
            continue
        fu_user_id = fu.get("user_id")
        inbox = await pick_inbox(fu_user_id)
        cfg = _inbox_to_cfg(inbox) if inbox else None
        result = await send_email(fu.get("to_email", ""), fu.get("subject", ""),
                                  fu.get("body", ""), allow=fu.get("deliverable", False),
                                  user_id=fu_user_id, email_id=fu["id"], cfg=cfg)
        await pool.execute(
            "UPDATE emails SET status=$1, simulated=$2, error=$3, sent_at=$4, inbox_id=$5 WHERE id=$6",
            result["status"], result.get("simulated", False), result.get("error"),
            now if result["status"] == "sent" else None,
            inbox["id"] if (inbox and result["status"] == "sent") else None, fu["id"])
        if result["status"] == "sent":
            sent += 1
            if inbox:
                await record_inbox_send(inbox["id"])
            if fu.get("lead_id"):
                await advance_stage(fu["lead_id"], "contacted", from_stages=("new",))
    if sent:
        await pool.execute("""
            INSERT INTO activity (id, user_id, type, message, created_at)
            VALUES ($1,$2,'auto',$3,$4)
        """, str(uuid.uuid4()), user_id, f"{sent} scheduled follow-up email(s) sent to non-responders.", now)
    return sent


VALID_STAGES = ("new", "contacted", "replied", "meeting", "won", "lost")

async def advance_stage(lead_id: str, to_stage: str, from_stages: tuple = None):
    """Move a lead forward in the pipeline, never overwriting a manually-set later stage."""
    if from_stages:
        await pool.execute(
            f"UPDATE leads SET stage=$1 WHERE id=$2 AND stage = ANY($3::text[])",
            to_stage, lead_id, list(from_stages))
    else:
        await pool.execute("UPDATE leads SET stage=$1 WHERE id=$2", to_stage, lead_id)

REPLY_INTENT_LABELS = ("interested", "not_interested", "referral", "out_of_office", "question")

async def classify_reply_intent(body: str) -> str:
    if not body.strip() or not (anthropic_client or openai_client):
        return "unknown"
    system = ("Classify a cold-email reply into exactly one label: " + ", ".join(REPLY_INTENT_LABELS) +
              ". Output ONLY the label, nothing else.")
    try:
        raw = await llm_call(system, f"Reply:\n{body[:800]}")
        label = raw.strip().lower().split()[0].strip('.,"\'')
        return label if label in REPLY_INTENT_LABELS else "unknown"
    except Exception as e:
        logger.error(f"Reply intent classification failed: {e}")
        return "unknown"

def _fetch_replies_sync(days: int = 21) -> dict:
    """Returns {sender_email_lower: body_snippet} for inbox messages in the time window."""
    import imaplib
    import email as email_lib
    from email.utils import parseaddr
    result = {}
    M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        M.login(SMTP_USER, SMTP_PASSWORD)
        M.select("INBOX")
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = M.search(None, f'(SINCE {since})')
        ids = data[0].split() if data and data[0] else []
        for i in ids[-250:]:
            typ, msgdata = M.fetch(i, "(RFC822)")
            for part in msgdata:
                if not (isinstance(part, tuple) and part[1]):
                    continue
                msg = email_lib.message_from_bytes(part[1])
                _, addr = parseaddr(msg.get("From", ""))
                if not addr:
                    continue
                body = ""
                if msg.is_multipart():
                    for p in msg.walk():
                        if p.get_content_type() == "text/plain":
                            try:
                                body = (p.get_payload(decode=True) or b"").decode(errors="ignore")
                            except Exception:
                                body = ""
                            break
                else:
                    try:
                        body = (msg.get_payload(decode=True) or b"").decode(errors="ignore")
                    except Exception:
                        body = str(msg.get_payload())
                result[addr.lower()] = body[:800]
    finally:
        try:
            M.logout()
        except Exception:
            pass
    return result

async def scan_replies(user_id: str = None) -> dict:
    """Read the inbox over IMAP, classify reply intent, and auto-stop follow-ups for repliers."""
    if not (SMTP_USER and SMTP_PASSWORD):
        return {"matched": 0, "error": "Email not configured"}
    try:
        replies = await asyncio.to_thread(_fetch_replies_sync)
    except Exception as e:
        logger.error(f"IMAP reply scan failed: {e}")
        return {"matched": 0, "error": str(e)}
    if user_id:
        candidates = recs(await pool.fetch(
            "SELECT * FROM leads WHERE replied=false AND email != '' AND user_id=$1", user_id))
    else:
        candidates = recs(await pool.fetch(
            "SELECT * FROM leads WHERE replied=false AND email != ''"))
    matched = 0
    for lead in candidates:
        addr = (lead.get("email") or "").lower()
        if addr in replies:
            intent = await classify_reply_intent(replies[addr])
            await pool.execute(
                "UPDATE leads SET replied=true, reply_intent=$2 WHERE id=$1", lead["id"], intent)
            await advance_stage(lead["id"], "replied", from_stages=("new", "contacted"))
            await pool.execute(
                "UPDATE emails SET status='cancelled' WHERE lead_id=$1 AND type='follow_up' AND status='scheduled'",
                lead["id"])
            await pool.execute("""
                INSERT INTO activity (id, user_id, type, message, created_at)
                VALUES ($1,$2,'auto',$3,$4)
            """, str(uuid.uuid4()), lead.get("user_id"),
                 (f"Reply detected from {lead.get('contact_name','')} "
                  f"({lead.get('company','')}) — intent: {intent}. Follow-ups auto-stopped."),
                 datetime.now(timezone.utc))
            matched += 1
    return {"matched": matched}


async def get_or_create_settings(user_id: str) -> dict:
    s = rec(await pool.fetchrow("SELECT * FROM settings WHERE user_id=$1", user_id))
    if not s:
        d = SettingsInput().model_dump()
        await pool.execute("""
            INSERT INTO settings (user_id, daily_target, auto_enabled, regions, industries, offer,
                                   sender_name, tone, skills, headline, experience)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, d["daily_target"], d["auto_enabled"], d["regions"], d["industries"],
             d["offer"], d["sender_name"], d["tone"], d["skills"], d["headline"], d["experience"])
        d["user_id"] = user_id
        d["last_run"] = None
        return d
    # Backfill any new schema fields for rows created before they existed
    return {**SettingsInput().model_dump(), **s}


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api_router.post("/auth/register")
async def register(data: RegisterInput, response: Response):
    email = data.email.lower()
    if await pool.fetchrow("SELECT 1 FROM users WHERE email=$1", email):
        raise HTTPException(status_code=400, detail="Email already registered")
    row = await pool.fetchrow("""
        INSERT INTO users (email, name, password_hash, role) VALUES ($1,$2,$3,'user') RETURNING id
    """, email, data.name, hash_password(data.password))
    uid = row["id"]
    set_auth_cookies(response, create_access_token(uid, email), create_refresh_token(uid))
    return {"id": uid, "email": email, "name": data.name, "role": "user", "owner_id": None}

@api_router.post("/auth/login")
async def login(data: LoginInput, response: Response):
    email = data.email.lower()
    user = rec(await pool.fetchrow("SELECT * FROM users WHERE email=$1", email))
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    uid = user["id"]  # the actual login's own identity — JWT subject, never the tenant/workspace id
    set_auth_cookies(response, create_access_token(uid, email), create_refresh_token(uid))
    return {"id": uid, "email": email, "name": user.get("name", ""), "role": user.get("role", "user"),
            "owner_id": user.get("owner_id")}

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

@api_router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = rec(await pool.fetchrow("SELECT * FROM users WHERE id=$1", payload["sub"]))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        response.set_cookie("access_token", create_access_token(user["id"], user["email"]),
                            httponly=True, secure=True, samesite="none", max_age=43200, path="/")
        return {"message": "refreshed"}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


# ---------------------------------------------------------------------------
# App routes
# ---------------------------------------------------------------------------
@api_router.get("/")
async def root():
    return {"message": "OutreachPilot API"}

@api_router.get("/dashboard/stats")
async def dashboard_stats(user: dict = Depends(get_current_user)):
    uid = tenant_id(user)
    total_leads = await pool.fetchval("SELECT count(*) FROM leads WHERE user_id=$1", uid)
    emails_sent = await pool.fetchval(
        "SELECT count(*) FROM emails WHERE user_id=$1 AND channel='email' AND status='sent'", uid)
    drafts = await pool.fetchval(
        "SELECT count(*) FROM emails WHERE user_id=$1 AND channel='email' AND status = ANY($2::text[])",
        uid, ["draft", "failed"])
    wa_ready = await pool.fetchval(
        "SELECT count(*) FROM emails WHERE user_id=$1 AND channel='whatsapp'", uid)
    leads_with_phone = await pool.fetchval(
        "SELECT count(*) FROM leads WHERE user_id=$1 AND phone != ''", uid)

    # last 7 days email volume
    volume = []
    for d in range(6, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=d)).date()
        cnt = await pool.fetchval(
            "SELECT count(*) FROM emails WHERE user_id=$1 AND channel='email' AND sent_at::date=$2",
            uid, day)
        volume.append({"day": day.isoformat()[5:], "emails": cnt})

    settings = await get_or_create_settings(uid)
    followups_queued = await pool.fetchval(
        "SELECT count(*) FROM emails WHERE user_id=$1 AND type='follow_up' AND status='scheduled'", uid)
    replied = await pool.fetchval("SELECT count(*) FROM leads WHERE user_id=$1 AND replied=true", uid)
    opened = await pool.fetchval(
        "SELECT count(*) FROM emails WHERE user_id=$1 AND channel='email' AND status='sent' AND open_count>0", uid)
    suppressed_count = await pool.fetchval("SELECT count(*) FROM suppressions WHERE user_id=$1", uid)
    return {
        "total_leads": total_leads, "emails_sent": emails_sent,
        "whatsapp_ready": wa_ready, "leads_with_phone": leads_with_phone,
        "daily_target": settings.get("daily_target", 100),
        "auto_enabled": settings.get("auto_enabled", True),
        "followups_queued": followups_queued, "replied": replied,
        "drafts": drafts,
        "opened": opened, "suppressed_count": suppressed_count,
        "volume": volume,
        "integrations": await integrations_status(uid),
    }

@api_router.get("/integrations/status")
async def integrations(user: dict = Depends(get_current_user)):
    return await integrations_status(tenant_id(user))

@api_router.post("/integrations/test-email")
async def test_email(user: dict = Depends(get_current_user)):
    inbox = await pick_inbox(tenant_id(user))
    cfg = _inbox_to_cfg(inbox) if inbox else None
    result = await send_email(user["email"],
                              "OutreachPilot — test email ✅",
                              f"Hi {user.get('name','there')},\n\nYour email delivery is working. "
                              f"OutreachPilot can now send cold emails from your account.\n\n— OutreachPilot",
                              allow=True, user_id=tenant_id(user), cfg=cfg)
    if inbox and result["status"] == "sent":
        await record_inbox_send(inbox["id"])
    return result

@api_router.post("/automation/run")
async def run_now(data: RunInput, user: dict = Depends(get_current_user)):
    count = max(1, min(data.count, 15))
    result = await execute_run(tenant_id(user), count, data.region, data.industry, data.offer, data.tone)
    await pool.execute("UPDATE settings SET last_run=$1 WHERE user_id=$2",
                       datetime.fromisoformat(result["run_at"]), tenant_id(user))
    return result

@api_router.get("/leads")
async def list_leads(user: dict = Depends(get_current_user)):
    return recs(await pool.fetch(
        "SELECT * FROM leads WHERE user_id=$1 ORDER BY created_at DESC LIMIT 500", tenant_id(user)))

@api_router.put("/leads/{lead_id}")
async def update_lead(lead_id: str, data: LeadUpdate, user: dict = Depends(get_current_user)):
    lead = rec(await pool.fetchrow("SELECT * FROM leads WHERE id=$1 AND user_id=$2", lead_id, tenant_id(user)))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if "stage" in upd and upd["stage"] not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Must be one of {VALID_STAGES}")
    if upd:
        set_clause = ", ".join(f"{k}=${i + 2}" for i, k in enumerate(upd.keys()))
        await pool.execute(f"UPDATE leads SET {set_clause} WHERE id=$1", lead_id, *upd.values())
    return rec(await pool.fetchrow("SELECT * FROM leads WHERE id=$1", lead_id))

@api_router.get("/emails")
async def list_emails(channel: Optional[str] = None, user: dict = Depends(get_current_user)):
    if channel:
        rows = await pool.fetch(
            "SELECT * FROM emails WHERE user_id=$1 AND channel=$2 ORDER BY created_at DESC LIMIT 1000",
            tenant_id(user), channel)
    else:
        rows = await pool.fetch(
            "SELECT * FROM emails WHERE user_id=$1 ORDER BY created_at DESC LIMIT 1000", tenant_id(user))
    return recs(rows)

@api_router.get("/activity")
async def list_activity(user: dict = Depends(get_current_user)):
    return recs(await pool.fetch(
        "SELECT * FROM activity WHERE user_id=$1 ORDER BY created_at DESC LIMIT 200", tenant_id(user)))

@api_router.put("/emails/{email_id}")
async def edit_email(email_id: str, data: EmailUpdate, user: dict = Depends(get_current_user)):
    em = rec(await pool.fetchrow("SELECT * FROM emails WHERE id=$1 AND user_id=$2", email_id, tenant_id(user)))
    if not em:
        raise HTTPException(status_code=404, detail="Email not found")
    if em.get("status") == "sent":
        raise HTTPException(status_code=400, detail="Email already sent")
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if upd:
        set_clause = ", ".join(f"{k}=${i + 2}" for i, k in enumerate(upd.keys()))
        await pool.execute(f"UPDATE emails SET {set_clause} WHERE id=$1", email_id, *upd.values())
    return rec(await pool.fetchrow("SELECT * FROM emails WHERE id=$1", email_id))

async def _send_one_email(em: dict, user_id: str) -> dict:
    """Manual send always attempts real delivery to the address shown."""
    to_email = (em.get("to_email") or "").strip()
    if not to_email:
        return {"status": "failed", "error": "No recipient", "simulated": False}
    inbox = await pick_inbox(user_id)
    cfg = _inbox_to_cfg(inbox) if inbox else None
    result = await send_email(to_email, em.get("subject", ""), em.get("body", ""), allow=True,
                              user_id=user_id, email_id=em["id"], cfg=cfg)
    now = datetime.now(timezone.utc)
    await pool.execute(
        "UPDATE emails SET status=$1, simulated=$2, error=$3, sent_at=$4, inbox_id=$5 WHERE id=$6",
        result["status"], result.get("simulated", False), result.get("error"),
        now if result["status"] == "sent" else None,
        inbox["id"] if (inbox and result["status"] == "sent") else None, em["id"])
    if inbox and result["status"] == "sent":
        await record_inbox_send(inbox["id"])
    if result["status"] == "sent" and em.get("lead_id"):
        await advance_stage(em["lead_id"], "contacted", from_stages=("new",))
    return result

@api_router.post("/emails/{email_id}/send")
async def send_one(email_id: str, user: dict = Depends(get_current_user)):
    em = rec(await pool.fetchrow("SELECT * FROM emails WHERE id=$1 AND user_id=$2", email_id, tenant_id(user)))
    if not em:
        raise HTTPException(status_code=404, detail="Email not found")
    if em.get("status") == "sent":
        return {"status": "sent", "already": True}
    result = await _send_one_email(em, tenant_id(user))
    await pool.execute("""
        INSERT INTO activity (id, user_id, type, message, created_at)
        VALUES ($1,$2,'manual',$3,$4)
    """, str(uuid.uuid4()), tenant_id(user),
         (f"Email to {em.get('contact_name','')} ({em.get('company','')}) "
          f"{'sent' if result['status']=='sent' else 'failed to send'}."),
         datetime.now(timezone.utc))
    return result

@api_router.post("/emails/send-all")
async def send_all(user: dict = Depends(get_current_user)):
    drafts = recs(await pool.fetch("""
        SELECT * FROM emails WHERE user_id=$1 AND channel='email' AND type='initial'
        AND status = ANY($2::text[]) LIMIT 1000
    """, tenant_id(user), ["draft", "failed"]))
    sent = 0
    failed = 0
    for em in drafts:
        result = await _send_one_email(em, tenant_id(user))
        if result["status"] == "sent":
            sent += 1
        else:
            failed += 1
    await pool.execute("""
        INSERT INTO activity (id, user_id, type, message, created_at)
        VALUES ($1,$2,'manual',$3,$4)
    """, str(uuid.uuid4()), tenant_id(user), f"Send all: {sent} email(s) sent, {failed} failed.",
         datetime.now(timezone.utc))
    return {"sent": sent, "failed": failed}

@api_router.post("/leads/{lead_id}/replied")
async def mark_replied(lead_id: str, user: dict = Depends(get_current_user)):
    res = await pool.execute("UPDATE leads SET replied=true WHERE id=$1 AND user_id=$2", lead_id, tenant_id(user))
    if res == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Lead not found")
    cancelled = await pool.execute(
        "UPDATE emails SET status='cancelled' WHERE lead_id=$1 AND type='follow_up' AND status='scheduled'",
        lead_id)
    cancelled_count = int(cancelled.split()[-1]) if cancelled.startswith("UPDATE") else 0
    return {"replied": True, "cancelled_followups": cancelled_count}

@api_router.post("/followups/process")
async def followups_process(user: dict = Depends(get_current_user)):
    sent = await process_due_followups(tenant_id(user))
    return {"sent": sent}

@api_router.post("/replies/scan")
async def replies_scan(user: dict = Depends(get_current_user)):
    return await scan_replies(tenant_id(user))

@api_router.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    return await get_or_create_settings(tenant_id(user))

@api_router.put("/settings")
async def update_settings(data: SettingsInput, user: dict = Depends(get_current_user)):
    tid = tenant_id(user)
    payload = data.model_dump()
    limits = await plan_limits_for(tid)
    if payload["daily_target"] > limits["max_daily_target"]:
        raise HTTPException(status_code=402,
                            detail=f"Your plan caps the daily target at {limits['max_daily_target']}. Upgrade for more volume.")
    await get_or_create_settings(tid)  # ensure row exists
    await pool.execute("""
        UPDATE settings SET daily_target=$1, auto_enabled=$2, regions=$3, industries=$4, offer=$5,
                            sender_name=$6, tone=$7, skills=$8, headline=$9, experience=$10, meeting_link=$11
        WHERE user_id=$12
    """, payload["daily_target"], payload["auto_enabled"], payload["regions"], payload["industries"],
         payload["offer"], payload["sender_name"], payload["tone"], payload["skills"],
         payload["headline"], payload["experience"], payload["meeting_link"], tid)
    return await get_or_create_settings(tid)


# ---------------------------------------------------------------------------
# Follow-up sequence builder
# ---------------------------------------------------------------------------
@api_router.get("/sequence")
async def get_sequence(user: dict = Depends(get_current_user)):
    return await get_sequence_steps(tenant_id(user))

@api_router.put("/sequence")
async def update_sequence(steps: List[SequenceStepInput], user: dict = Depends(get_current_user)):
    if len(steps) > 10:
        raise HTTPException(status_code=400, detail="A sequence can have at most 10 steps")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM sequence_steps WHERE user_id=$1", tenant_id(user))
            for i, st in enumerate(steps):
                await conn.execute(
                    "INSERT INTO sequence_steps (id, user_id, step_order, delay_days, angle) "
                    "VALUES ($1,$2,$3,$4,$5)",
                    str(uuid.uuid4()), tenant_id(user), i + 1, max(1, st.delay_days), st.angle)
    return await get_sequence_steps(tenant_id(user))


# ---------------------------------------------------------------------------
# Funnel + A/B analytics
# ---------------------------------------------------------------------------
@api_router.get("/analytics/funnel")
async def analytics_funnel(user: dict = Depends(get_current_user)):
    uid = tenant_id(user)
    stage_counts = {}
    for st in VALID_STAGES:
        stage_counts[st] = await pool.fetchval(
            "SELECT count(*) FROM leads WHERE user_id=$1 AND stage=$2", uid, st)
    sent = await pool.fetchval(
        "SELECT count(*) FROM emails WHERE user_id=$1 AND channel='email' AND status='sent'", uid)
    opened = await pool.fetchval(
        "SELECT count(*) FROM emails WHERE user_id=$1 AND channel='email' AND status='sent' AND open_count>0", uid)
    clicked = await pool.fetchval(
        "SELECT count(*) FROM emails WHERE user_id=$1 AND channel='email' AND status='sent' AND click_count>0", uid)
    ab_variants = recs(await pool.fetch("""
        SELECT variant, count(*) AS sent, count(*) FILTER (WHERE open_count > 0) AS opened
        FROM emails WHERE user_id=$1 AND channel='email' AND status='sent' AND variant IS NOT NULL
        GROUP BY variant ORDER BY variant
    """, uid))
    return {"sent": sent, "opened": opened, "clicked": clicked, "stages": stage_counts,
            "ab_variants": ab_variants}


# ---------------------------------------------------------------------------
# CSV lead import
# ---------------------------------------------------------------------------
@api_router.post("/leads/import")
async def import_leads(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    raw = (await file.read()).decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(raw))
    settings = await get_or_create_settings(tenant_id(user))
    sender = settings.get("sender_name", "")
    offer = settings.get("offer", "")
    now_dt = datetime.now(timezone.utc)
    imported = 0
    skipped = 0
    for row in reader:
        email = (row.get("email") or "").strip().lower()
        if not email:
            skipped += 1
            continue
        exists = await pool.fetchval(
            "SELECT 1 FROM leads WHERE user_id=$1 AND email=$2", tenant_id(user), email)
        if exists:
            skipped += 1
            continue
        phone = (row.get("phone") or "").strip()
        wa = whatsapp_link(phone, row.get("company", ""), sender, offer) if phone else None
        suppressed_lead = await is_suppressed(tenant_id(user), email)
        await pool.execute("""
            INSERT INTO leads (id, user_id, company, contact_name, title, email, phone, location,
                                industry, website, pain_point, project_idea, estimated_value,
                                whatsapp_link, created_at, source, lead_source, replied, suppressed)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,'csv_import','csv',false,$16)
        """, str(uuid.uuid4()), tenant_id(user), row.get("company", ""), row.get("contact_name", ""),
             row.get("title", ""), email, phone, row.get("location", ""), row.get("industry", ""),
             row.get("website", ""), row.get("pain_point", ""), row.get("project_idea", ""),
             row.get("estimated_value", ""), wa, now_dt, suppressed_lead)
        imported += 1
    await pool.execute("""
        INSERT INTO activity (id, user_id, type, message, created_at)
        VALUES ($1,$2,'manual',$3,$4)
    """, str(uuid.uuid4()), tenant_id(user),
         f"Imported {imported} lead(s) from CSV ({skipped} skipped — missing email or duplicate).", now_dt)
    return {"imported": imported, "skipped": skipped}


# ---------------------------------------------------------------------------
# Sending inboxes (multi-inbox rotation + warm-up)
# ---------------------------------------------------------------------------
_MASK = "••••••••"

def _inbox_public(row: dict) -> dict:
    d = dict(row)
    if d.get("smtp_password"):
        d["smtp_password"] = _MASK
    if d.get("resend_api_key"):
        d["resend_api_key"] = _MASK
    return d

@api_router.get("/inboxes")
async def list_inboxes(user: dict = Depends(get_current_user)):
    rows = recs(await pool.fetch(
        "SELECT * FROM inboxes WHERE user_id=$1 ORDER BY created_at", tenant_id(user)))
    return [_inbox_public(r) for r in rows]

@api_router.post("/inboxes")
async def create_inbox(data: InboxInput, user: dict = Depends(get_current_user)):
    tid = tenant_id(user)
    limits = await plan_limits_for(tid)
    current = await pool.fetchval("SELECT count(*) FROM inboxes WHERE user_id=$1", tid)
    if current >= limits["max_inboxes"]:
        raise HTTPException(status_code=402,
                            detail=f"Your plan allows up to {limits['max_inboxes']} inbox(es). Upgrade to add more.")
    row = await pool.fetchrow("""
        INSERT INTO inboxes (id, user_id, label, provider, smtp_host, smtp_port, smtp_user, smtp_password,
                              resend_api_key, from_email, daily_cap, warmup_enabled, is_active)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING *
    """, str(uuid.uuid4()), tid, data.label, data.provider, data.smtp_host, data.smtp_port,
         data.smtp_user, data.smtp_password, data.resend_api_key, data.from_email, data.daily_cap,
         data.warmup_enabled, data.is_active)
    return _inbox_public(rec(row))

@api_router.put("/inboxes/{inbox_id}")
async def update_inbox(inbox_id: str, data: InboxInput, user: dict = Depends(get_current_user)):
    existing = rec(await pool.fetchrow(
        "SELECT * FROM inboxes WHERE id=$1 AND user_id=$2", inbox_id, tenant_id(user)))
    if not existing:
        raise HTTPException(status_code=404, detail="Inbox not found")
    # Keep the stored secret if the client echoed back the masked placeholder unchanged.
    smtp_password = existing["smtp_password"] if data.smtp_password == _MASK else data.smtp_password
    resend_api_key = existing["resend_api_key"] if data.resend_api_key == _MASK else data.resend_api_key
    row = await pool.fetchrow("""
        UPDATE inboxes SET label=$1, provider=$2, smtp_host=$3, smtp_port=$4, smtp_user=$5,
                            smtp_password=$6, resend_api_key=$7, from_email=$8, daily_cap=$9,
                            warmup_enabled=$10, is_active=$11
        WHERE id=$12 RETURNING *
    """, data.label, data.provider, data.smtp_host, data.smtp_port, data.smtp_user, smtp_password,
         resend_api_key, data.from_email, data.daily_cap, data.warmup_enabled, data.is_active, inbox_id)
    return _inbox_public(rec(row))

@api_router.delete("/inboxes/{inbox_id}")
async def delete_inbox(inbox_id: str, user: dict = Depends(get_current_user)):
    res = await pool.execute("DELETE FROM inboxes WHERE id=$1 AND user_id=$2", inbox_id, tenant_id(user))
    if res == "DELETE 0":
        raise HTTPException(status_code=404, detail="Inbox not found")
    return {"deleted": True}

@api_router.post("/inboxes/{inbox_id}/test")
async def test_inbox(inbox_id: str, user: dict = Depends(get_current_user)):
    inbox = rec(await pool.fetchrow(
        "SELECT * FROM inboxes WHERE id=$1 AND user_id=$2", inbox_id, tenant_id(user)))
    if not inbox:
        raise HTTPException(status_code=404, detail="Inbox not found")
    result = await send_email(
        user["email"], "OutreachPilot — inbox test ✅",
        f"Hi {user.get('name','there')},\n\nInbox '{inbox['label']}' is wired up correctly and "
        f"ready to send.\n\n— OutreachPilot",
        allow=True, user_id=tenant_id(user), cfg=_inbox_to_cfg(inbox))
    return result


# ---------------------------------------------------------------------------
# Suppression list (unsubscribes / manual opt-outs)
# ---------------------------------------------------------------------------
@api_router.get("/suppressions")
async def list_suppressions_route(user: dict = Depends(get_current_user)):
    return recs(await pool.fetch(
        "SELECT * FROM suppressions WHERE user_id=$1 ORDER BY created_at DESC", tenant_id(user)))

@api_router.post("/suppressions")
async def add_suppression_route(data: SuppressionInput, user: dict = Depends(get_current_user)):
    await add_suppression(tenant_id(user), data.email, data.reason)
    return {"added": True}

@api_router.delete("/suppressions/{suppression_id}")
async def remove_suppression_route(suppression_id: str, user: dict = Depends(get_current_user)):
    res = await pool.execute(
        "DELETE FROM suppressions WHERE id=$1 AND user_id=$2", suppression_id, tenant_id(user))
    if res == "DELETE 0":
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Team seats: invited members share the owner's entire workspace
# ---------------------------------------------------------------------------
@api_router.get("/team/members")
async def list_team_members(user: dict = Depends(get_current_user)):
    tid = tenant_id(user)
    rows = recs(await pool.fetch(
        "SELECT id, name, email, created_at, owner_id FROM users WHERE id=$1 OR owner_id=$1 ORDER BY created_at",
        tid))
    return [{**r, "is_owner": r["owner_id"] is None} for r in rows]

@api_router.post("/team/members")
async def add_team_member(data: TeamMemberInput, user: dict = Depends(get_current_user)):
    if user.get("owner_id"):
        raise HTTPException(status_code=403, detail="Only the workspace owner can add teammates")
    tid = tenant_id(user)
    limits = await plan_limits_for(tid)
    seats = await pool.fetchval("SELECT count(*) FROM users WHERE id=$1 OR owner_id=$1", tid)
    if seats >= limits["max_team_seats"]:
        raise HTTPException(status_code=402,
                            detail=f"Your plan allows {limits['max_team_seats']} seat(s). Upgrade to add teammates.")
    email = data.email.lower()
    if await pool.fetchrow("SELECT 1 FROM users WHERE email=$1", email):
        raise HTTPException(status_code=400, detail="That email is already registered")
    row = await pool.fetchrow(
        "INSERT INTO users (email, name, password_hash, role, owner_id) VALUES ($1,$2,$3,'user',$4) RETURNING id",
        email, data.name, hash_password(data.password), tid)
    return {"id": row["id"], "email": email, "name": data.name, "is_owner": False}

@api_router.delete("/team/members/{member_id}")
async def remove_team_member(member_id: str, user: dict = Depends(get_current_user)):
    if user.get("owner_id"):
        raise HTTPException(status_code=403, detail="Only the workspace owner can remove teammates")
    tid = tenant_id(user)
    if member_id == tid:
        raise HTTPException(status_code=400, detail="Cannot remove the workspace owner")
    res = await pool.execute("DELETE FROM users WHERE id=$1 AND owner_id=$2", member_id, tid)
    if res == "DELETE 0":
        raise HTTPException(status_code=404, detail="Team member not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Billing (Stripe) — checkout, customer portal, webhook. Owner-only.
# ---------------------------------------------------------------------------
@api_router.get("/billing/status")
async def billing_status(user: dict = Depends(get_current_user)):
    tid = tenant_id(user)
    owner = rec(await pool.fetchrow(
        "SELECT plan, subscription_status FROM users WHERE id=$1", tid)) or {}
    return {
        "plan": owner.get("plan") or "starter",
        "subscription_status": owner.get("subscription_status"),
        "is_owner": not user.get("owner_id"),
        "limits": await plan_limits_for(tid),
        "stripe_configured": bool(STRIPE_SECRET_KEY),
    }

@api_router.post("/billing/checkout")
async def billing_checkout(data: CheckoutInput, user: dict = Depends(get_current_user)):
    if user.get("owner_id"):
        raise HTTPException(status_code=403, detail="Only the workspace owner can manage billing")
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Billing isn't configured yet (missing STRIPE_SECRET_KEY)")
    price_id = STRIPE_PRICE_IDS.get(data.plan)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Unknown or unconfigured plan: {data.plan}")
    tid = tenant_id(user)
    owner = rec(await pool.fetchrow("SELECT * FROM users WHERE id=$1", tid))
    customer_id = owner.get("stripe_customer_id")
    try:
        if not customer_id:
            customer = await asyncio.to_thread(
                stripe.Customer.create, email=owner["email"], name=owner["name"])
            customer_id = customer.id
            await pool.execute("UPDATE users SET stripe_customer_id=$1 WHERE id=$2", customer_id, tid)
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            customer=customer_id, mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{FRONTEND_URL}/app/billing?checkout=success",
            cancel_url=f"{FRONTEND_URL}/app/billing?checkout=cancelled",
            metadata={"tenant_id": tid, "plan": data.plan})
    except Exception as e:
        logger.error(f"Stripe checkout failed: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    return {"url": session.url}

@api_router.post("/billing/portal")
async def billing_portal(user: dict = Depends(get_current_user)):
    if user.get("owner_id"):
        raise HTTPException(status_code=403, detail="Only the workspace owner can manage billing")
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Billing isn't configured yet")
    tid = tenant_id(user)
    owner = rec(await pool.fetchrow("SELECT stripe_customer_id FROM users WHERE id=$1", tid))
    if not owner or not owner.get("stripe_customer_id"):
        raise HTTPException(status_code=400, detail="No billing account yet — start a checkout first")
    try:
        session = await asyncio.to_thread(
            stripe.billing_portal.Session.create,
            customer=owner["stripe_customer_id"], return_url=f"{FRONTEND_URL}/app/billing")
    except Exception as e:
        logger.error(f"Stripe portal failed: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    return {"url": session.url}

@api_router.post("/billing/webhook")
async def billing_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Webhook not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {e}")
    etype = event["type"]
    obj = event["data"]["object"]
    if etype == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        tid, plan = meta.get("tenant_id"), meta.get("plan")
        if tid and plan:
            await pool.execute(
                "UPDATE users SET plan=$1, subscription_status='active', stripe_subscription_id=$2 WHERE id=$3",
                plan, obj.get("subscription"), tid)
    elif etype == "customer.subscription.updated":
        await pool.execute(
            "UPDATE users SET subscription_status=$1 WHERE stripe_customer_id=$2",
            obj.get("status"), obj.get("customer"))
    elif etype == "customer.subscription.deleted":
        await pool.execute(
            "UPDATE users SET plan='starter', subscription_status='canceled' WHERE stripe_customer_id=$1",
            obj.get("customer"))
    return {"received": True}


# ---------------------------------------------------------------------------
# Public endpoints hit by email clients — no auth (unsubscribe link, open pixel, click redirect)
# ---------------------------------------------------------------------------
@api_router.get("/unsubscribe/{token}")
async def unsubscribe(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "unsub":
            raise ValueError("wrong token type")
    except Exception:
        return Response(content="<h3>Invalid or expired unsubscribe link.</h3>",
                        media_type="text/html", status_code=400)
    await add_suppression(payload["user_id"], payload["email"], reason="unsubscribed")
    return Response(
        content="<h3>You've been unsubscribed and won't receive further emails from us.</h3>",
        media_type="text/html")

@api_router.get("/t/{email_id}.gif")
async def track_open(email_id: str):
    try:
        now = datetime.now(timezone.utc)
        await pool.execute(
            "UPDATE emails SET open_count = open_count + 1, opened_at = COALESCE(opened_at, $1) WHERE id=$2",
            now, email_id)
        await pool.execute(
            "INSERT INTO email_events (id, email_id, type) VALUES ($1,$2,'open')",
            str(uuid.uuid4()), email_id)
    except Exception as e:
        logger.error(f"Open tracking failed: {e}")
    return Response(content=_PIXEL_GIF, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

@api_router.get("/c/{email_id}")
async def track_click(email_id: str, u: str):
    try:
        now = datetime.now(timezone.utc)
        await pool.execute(
            "UPDATE emails SET click_count = click_count + 1, clicked_at = COALESCE(clicked_at, $1) WHERE id=$2",
            now, email_id)
        await pool.execute(
            "INSERT INTO email_events (id, email_id, type, url) VALUES ($1,$2,'click',$3)",
            str(uuid.uuid4()), email_id, u)
    except Exception as e:
        logger.error(f"Click tracking failed: {e}")
    return RedirectResponse(url=u)


# ---------------------------------------------------------------------------
# Background daily scheduler
# ---------------------------------------------------------------------------
async def scheduler_loop():
    await asyncio.sleep(20)
    while True:
        try:
            today = datetime.now(timezone.utc).date()
            # Detect replies first so we don't send follow-ups to people who answered
            try:
                await scan_replies()
            except Exception as e:
                logger.error(f"Reply scan error: {e}")
            # Send any follow-ups that are now due
            try:
                await process_due_followups()
            except Exception as e:
                logger.error(f"Follow-up processing error: {e}")
            for s in recs(await pool.fetch("SELECT * FROM settings WHERE auto_enabled=true")):
                uid = s.get("user_id")
                last_run = s.get("last_run")
                if not uid or (last_run and last_run.date() == today):
                    continue
                try:
                    await execute_run(uid, 8, source="auto")
                    await pool.execute("UPDATE settings SET last_run=$1 WHERE user_id=$2",
                                       datetime.now(timezone.utc), uid)
                    logger.info(f"Auto run completed for {uid}")
                except Exception as e:
                    logger.error(f"Auto run failed for {uid}: {e}")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        await asyncio.sleep(3600)


@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, init=_init_connection)
    async with pool.acquire() as conn:
        await conn.execute((ROOT_DIR / "schema.sql").read_text())

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@outreachpilot.com")
    admin_pw = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = rec(await pool.fetchrow("SELECT * FROM users WHERE email=$1", admin_email))
    if not existing:
        await pool.execute(
            "INSERT INTO users (email, name, password_hash, role) VALUES ($1,'Admin',$2,'admin')",
            admin_email, hash_password(admin_pw))
    elif not verify_password(admin_pw, existing["password_hash"]):
        await pool.execute("UPDATE users SET password_hash=$1 WHERE email=$2",
                           hash_password(admin_pw), admin_email)
    asyncio.create_task(scheduler_loop())
    logger.info("OutreachPilot started")

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
