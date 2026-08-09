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
import re
import html as html_lib
import hashlib
import ipaddress
import socket
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional
from urllib.parse import quote, urlparse

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
HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "").strip()
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
FOURSQUARE_API_KEY = os.environ.get("FOURSQUARE_API_KEY", "").strip()
GITHUB_API_KEY = os.environ.get("GITHUB_API_KEY", "").strip()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()
BACKEND_URL = os.environ.get("BACKEND_URL", "").strip().rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").strip().rstrip("/")
IS_PRODUCTION = FRONTEND_URL.startswith("https://")

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

VOICE_NOTES_DIR = ROOT_DIR / "voice_notes"

_apollo_ok = None  # None=untested, True=working, False=blocked (e.g. free plan)
_places_hunter_ok = None  # None=untested, True=working, False=blocked

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
        "places_hunter_live": bool(HUNTER_API_KEY and GOOGLE_PLACES_API_KEY) and _places_hunter_ok is not False,
        "places_hunter_blocked": bool(HUNTER_API_KEY and GOOGLE_PLACES_API_KEY) and _places_hunter_ok is False,
        "foursquare_hunter_live": bool(HUNTER_API_KEY and FOURSQUARE_API_KEY) and _foursquare_hunter_ok is not False,
        "foursquare_hunter_blocked": bool(HUNTER_API_KEY and FOURSQUARE_API_KEY) and _foursquare_hunter_ok is False,
        "github_live": bool(GITHUB_API_KEY) and _github_ok is not False,
        "github_blocked": bool(GITHUB_API_KEY) and _github_ok is False,
        "osm_hunter_live": bool(HUNTER_API_KEY) and _osm_hunter_ok is not False,
        "osm_hunter_blocked": bool(HUNTER_API_KEY) and _osm_hunter_ok is False,
        "whatsapp_live": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM),
        "reply_detection_live": bool(SMTP_USER and SMTP_PASSWORD),
    }

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("outreachpilot")

app = FastAPI(
    title="OutreachPilot",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
api_router = APIRouter(prefix="/api")
public_router = APIRouter(prefix="/api/public/v1")


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

COOKIE_SECURE = IS_PRODUCTION
COOKIE_SAMESITE = "none" if COOKIE_SECURE else "lax"

_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"timing-attack-mitigation", bcrypt.gensalt()).decode("utf-8")

_rate_limit_buckets: dict = defaultdict(deque)

def rate_limit(key: str, max_requests: int, window_seconds: int):
    """In-memory sliding-window limiter. Per-process only — fine for a single-instance deploy."""
    now = datetime.now(timezone.utc).timestamp()
    bucket = _rate_limit_buckets[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= max_requests:
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.")
    bucket.append(now)

def set_auth_cookies(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, httponly=True, secure=COOKIE_SECURE,
                        samesite=COOKIE_SAMESITE, max_age=43200, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=COOKIE_SECURE,
                        samesite=COOKIE_SAMESITE, max_age=604800, path="/")

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

async def get_api_tenant(request: Request) -> str:
    """Auth for /api/public/v1/* — a long-lived API key instead of a login cookie."""
    auth = request.headers.get("Authorization", "")
    key = auth[7:] if auth.startswith("Bearer ") else request.headers.get("X-API-Key", "")
    if not key:
        raise HTTPException(status_code=401, detail="Missing API key (Authorization: Bearer <key>)")
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    row = rec(await pool.fetchrow("SELECT * FROM api_keys WHERE key_hash=$1", key_hash))
    if not row:
        raise HTTPException(status_code=401, detail="Invalid API key")
    await pool.execute("UPDATE api_keys SET last_used_at=$1 WHERE id=$2",
                       datetime.now(timezone.utc), row["id"])
    return row["user_id"]  # already the tenant id — set at key-creation time

async def plan_limits_for(tid: str) -> dict:
    plan = await pool.fetchval("SELECT plan FROM users WHERE id=$1", tid) or "starter"
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class RegisterInput(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    ref: Optional[str] = None

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class PasswordChangeInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

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
    brand_name: str = ""
    brand_logo_url: str = ""
    proof_points: List[str] = []

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
    password: str = Field(min_length=8)

class CheckoutInput(BaseModel):
    plan: str

class SpamCheckInput(BaseModel):
    subject: str = ""
    body: str = ""

class ApiKeyInput(BaseModel):
    label: str = "API key"

class PublicLeadInput(BaseModel):
    email: EmailStr
    company: str = ""
    contact_name: str = ""
    title: str = ""
    phone: str = ""
    location: str = ""
    industry: str = ""
    website: str = ""
    pain_point: str = ""

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

# Some providers occasionally mis-encode smart quotes/dashes as U+FFFD when generating
# copy (e.g. "Let�s schedule..."), which reaches recipients as a broken character.
# Normalize those to plain ASCII before any generated text is stored or sent.
_TEXT_CLEANUP = {
    "�": "'", "‘": "'", "’": "'",
    "“": '"', "”": '"', "–": "-", "—": "-",
}

def clean_copy(value):
    if not isinstance(value, str):
        return value
    for bad, good in _TEXT_CLEANUP.items():
        value = value.replace(bad, good)
    return value

def clean_copy_fields(item: dict, keys) -> dict:
    for k in keys:
        if k in item and item[k] is not None:
            item[k] = clean_copy(item[k])
    return item

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
                "live_signal": l.get("live_signal") or "",
                "subject_style": style_by_variant[subject_variant(idx)]}
               for idx, l in enumerate(leads)]
    meeting_note = (f'\nA booking link is available ({meeting_link}) — you may offer it as an '
                    f'alternative to proposing a call time yourself.' if meeting_link else "")
    prompt = f"""Write a personalized cold email for each prospect below.
Sender name: {sender}. Offer: {offer}. Tone: {tone}.
Rules: <=120 words, one clear CTA (a 15-min call), reference their pain_point naturally,
and pitch the specific "project_idea" as what you could build for them. If "live_signal" is
non-empty for a prospect, it's a real, current snippet pulled from their own website — weave
in one specific detail from it naturally if it fits; ignore it if it doesn't add anything
concrete. No fluff, no "I hope this finds you well", no clickbait subject lines, and never
invent statistics, client results, or case studies that weren't given to you — the only claims
you can make are the pain_point and project_idea provided. Use plain straight quotes/apostrophes
and hyphens only — no smart quotes or em-dashes. Subject line <=6 words, matching each
prospect's "subject_style".{meeting_note}
Prospects: {json.dumps(compact)}
Return a JSON array where each item has: "i" (matching index), "subject", "body".
Body should use \\n for line breaks and end with "{sender}". Return ONLY JSON."""
    raw = await llm_call(system, prompt)
    emails = _extract_json(raw)
    return [clean_copy_fields(e, ["subject", "body"]) for e in emails]

def build_whatsapp_message(lead: dict, sender: str, offer: str) -> str:
    """Personalized WhatsApp opener — mirrors the email's use of pain_point/project_idea
    instead of a generic mass-blast line, so it reads as researched rather than templated."""
    first_name = (lead.get("contact_name") or "").strip().split(" ")[0] or "there"
    company = (lead.get("company") or "your team").strip()
    project_idea = (lead.get("project_idea") or "").strip().rstrip(".")
    if project_idea:
        pitch = f"I put together a quick idea for {company}: {project_idea}"
    else:
        pitch = f"I put together a quick proposal for {company} on {offer}"
    msg = f"Hi {first_name}, this is {sender}. {pitch}. Do you have 2 minutes for a quick call?"
    return clean_copy(msg)

def whatsapp_link(phone: str, lead: dict, sender: str, offer: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    msg = build_whatsapp_message(lead, sender, offer)
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
# Deliverability / spam-score heuristic — pure local check, no external API
# ---------------------------------------------------------------------------
SPAM_TRIGGER_PHRASES = [
    "100% free", "act now", "buy now", "cash bonus", "cheap", "congratulations",
    "double your", "earn money", "for free", "guarantee", "limited time", "no obligation",
    "no purchase necessary", "risk-free", "winner", "you have been selected",
    "dear friend", "make money fast", "click here", "urgent",
]

def spam_score(subject: str, body: str) -> dict:
    subject = subject or ""
    body = body or ""
    text = f"{subject}\n{body}"
    lower = text.lower()
    score = 100
    flags = []

    hits = [p for p in SPAM_TRIGGER_PHRASES if p in lower]
    if hits:
        score -= min(30, 6 * len(hits))
        flags.append(f"Spam trigger phrase(s): {', '.join(hits[:5])}")

    exclam = text.count("!")
    if exclam > 1:
        score -= min(15, exclam * 5)
        flags.append(f"{exclam} exclamation marks")

    caps_words = [w for w in re.findall(r"[A-Za-z]{3,}", subject) if w.isupper()]
    if caps_words:
        score -= min(15, 5 * len(caps_words))
        flags.append(f"ALL-CAPS word(s) in subject: {', '.join(caps_words)}")

    if len(subject) > 60:
        score -= 5
        flags.append("Subject line longer than 60 characters")
    if not subject.strip():
        score -= 20
        flags.append("Empty subject line")

    link_count = len(re.findall(r"https?://", body))
    if link_count > 2:
        score -= min(15, 5 * (link_count - 2))
        flags.append(f"{link_count} links in body")

    score = max(0, min(100, score))
    return {"score": score, "flags": flags}


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


# ---------------------------------------------------------------------------
# Real lead sourcing via Google Places (discovers real companies) + Hunter.io
# (finds real, verified emails at those companies' domains). Second real
# source, independent of Apollo — useful when Apollo access is blocked.
# ---------------------------------------------------------------------------
def _domain_from_url(url: str) -> str:
    from urllib.parse import urlparse
    netloc = urlparse(url if url.startswith("http") else f"https://{url}").netloc
    return netloc[4:] if netloc.startswith("www.") else netloc

async def fetch_places_companies(regions, industries, limit) -> List[dict]:
    """Real local businesses via Google Places Text Search + Place Details."""
    companies = []
    async with httpx.AsyncClient(timeout=20) as c:
        for region in regions:
            for industry in industries:
                if len(companies) >= limit:
                    break
                resp = await c.get("https://maps.googleapis.com/maps/api/place/textsearch/json",
                                   params={"query": f"{industry} companies in {region}",
                                           "key": GOOGLE_PLACES_API_KEY})
                if resp.is_error:
                    raise RuntimeError(f"Google Places error {resp.status_code}")
                data = resp.json()
                status = data.get("status")
                if status not in ("OK", "ZERO_RESULTS"):
                    raise RuntimeError(f"Google Places status {status}: {data.get('error_message', '')}")
                for place in data.get("results", []):
                    place_id = place.get("place_id")
                    if not place_id:
                        continue
                    det = await c.get("https://maps.googleapis.com/maps/api/place/details/json",
                                      params={"place_id": place_id,
                                              "fields": "name,website,formatted_phone_number,"
                                                        "international_phone_number,formatted_address",
                                              "key": GOOGLE_PLACES_API_KEY})
                    if det.is_error:
                        continue
                    d = det.json().get("result", {})
                    website = d.get("website")
                    if not website:
                        continue  # no domain to look up real contacts at — skip
                    companies.append({
                        "company": d.get("name") or place.get("name") or "",
                        "website": website,
                        "phone": d.get("international_phone_number") or d.get("formatted_phone_number") or "",
                        "location": d.get("formatted_address") or region,
                        "industry": industry,
                    })
    return companies

async def fetch_hunter_contact(domain: str) -> Optional[dict]:
    """Real, verified email + name/title at a domain, via Hunter's Domain Search."""
    async with httpx.AsyncClient(timeout=20) as c:
        resp = await c.get("https://api.hunter.io/v2/domain-search",
                           params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 5})
    if resp.is_error:
        if resp.status_code in (401, 403):
            raise RuntimeError(f"Hunter auth error {resp.status_code}")
        return None
    emails = (resp.json().get("data") or {}).get("emails") or []
    decision_maker_titles = ("ceo", "founder", "cto", "director", "head", "vp", "manager", "owner")
    emails.sort(key=lambda e: 0 if (e.get("position") or "").lower().startswith(decision_maker_titles) else 1)
    for e in emails:
        if e.get("value"):
            return {"email": e["value"],
                    "contact_name": " ".join(x for x in [e.get("first_name"), e.get("last_name")] if x),
                    "title": e.get("position") or ""}
    return None

async def fetch_places_hunter_leads(regions, industries, count) -> List[dict]:
    global _places_hunter_ok
    companies = await fetch_places_companies(regions, industries, count * 4)
    leads = []
    for comp in companies:
        if len(leads) >= count:
            break
        domain = _domain_from_url(comp["website"])
        try:
            contact = await fetch_hunter_contact(domain)
        except Exception as e:
            logger.warning(f"Hunter lookup failed for {domain}: {e}")
            continue
        if not contact:
            continue
        leads.append({
            "company": comp["company"], "contact_name": contact["contact_name"],
            "title": contact["title"], "email": contact["email"], "phone": comp.get("phone", ""),
            "location": comp.get("location", ""), "industry": comp.get("industry", ""),
            "website": comp["website"], "pain_point": "",
        })
    _places_hunter_ok = True
    return leads


# ---------------------------------------------------------------------------
# Real lead sourcing via Foursquare Places (worldwide business directory,
# free tier, no billing account required — unlike Google Places) + Hunter.io.
# Foursquare resolves a plain-text location server-side, so no separate
# geocoding step is needed. Like OSM, its categories are broad rather than
# precise verticals, so "industry" is used as a soft text filter only.
# ---------------------------------------------------------------------------
_foursquare_hunter_ok = None  # None=untested, True=working, False=blocked

async def fetch_foursquare_companies(regions, industries, limit) -> List[dict]:
    companies = []
    keyword = industries[0] if industries else ""
    async with httpx.AsyncClient(timeout=20) as c:
        for region in regions:
            if len(companies) >= limit:
                break
            # X-Places-Api-Version is a dated API-contract pin (Foursquare's equivalent of
            # Stripe's API versioning) — bump this if Foursquare sunsets this version.
            resp = await c.get("https://places-api.foursquare.com/places/search",
                               params={"near": region, "query": keyword, "limit": min(limit * 3, 50)},
                               headers={"Authorization": f"Bearer {FOURSQUARE_API_KEY}",
                                       "X-Places-Api-Version": "2025-06-17",
                                       "Accept": "application/json"})
            if resp.is_error:
                raise RuntimeError(f"Foursquare search error {resp.status_code}")
            for place in resp.json().get("results", []):
                website = place.get("website")
                if not website:
                    continue  # no domain to look up real contacts at — skip
                loc = place.get("location", {})
                companies.append({
                    "company": place.get("name", ""),
                    "website": website,
                    "phone": place.get("tel", ""),
                    "location": loc.get("formatted_address") or region,
                    "industry": keyword,
                })
    return companies

async def fetch_foursquare_hunter_leads(regions, industries, count) -> List[dict]:
    global _foursquare_hunter_ok
    companies = await fetch_foursquare_companies(regions, industries, count * 4)
    leads = []
    for comp in companies:
        if len(leads) >= count:
            break
        domain = _domain_from_url(comp["website"])
        try:
            contact = await fetch_hunter_contact(domain)
        except Exception as e:
            logger.warning(f"Hunter lookup failed for {domain}: {e}")
            continue
        if not contact:
            continue
        leads.append({
            "company": comp["company"], "contact_name": contact["contact_name"],
            "title": contact["title"], "email": contact["email"], "phone": comp.get("phone", ""),
            "location": comp.get("location", ""), "industry": comp.get("industry", ""),
            "website": comp["website"], "pain_point": "",
        })
    _foursquare_hunter_ok = True
    return leads


# ---------------------------------------------------------------------------
# Real lead sourcing via GitHub organizations (free, instant personal access
# token — no approval process, no billing) + Hunter.io as a fallback when an
# org doesn't list an email directly. Best fit for tech/software/SaaS targets
# specifically, since it only surfaces companies with a public GitHub org.
# ---------------------------------------------------------------------------
_github_ok = None  # None=untested, True=working, False=blocked
_GITHUB_API_VERSION = "2026-03-10"  # dated API-contract pin; bump if GitHub sunsets this version

async def fetch_github_companies(regions, industries, limit) -> List[dict]:
    companies = []
    keyword = industries[0] if industries else ""
    headers = {"Authorization": f"Bearer {GITHUB_API_KEY}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": _GITHUB_API_VERSION}
    async with httpx.AsyncClient(timeout=20) as c:
        for region in regions:
            if len(companies) >= limit:
                break
            query = f'type:org location:"{region}"' + (f" {keyword}" if keyword else "")
            resp = await c.get("https://api.github.com/search/users",
                               params={"q": query, "per_page": min(limit * 3, 30)}, headers=headers)
            if resp.is_error:
                raise RuntimeError(f"GitHub search error {resp.status_code}")
            for item in resp.json().get("items", []):
                if len(companies) >= limit:
                    break
                org_resp = await c.get(f"https://api.github.com/orgs/{item['login']}", headers=headers)
                if org_resp.is_error:
                    continue
                org = org_resp.json()
                blog = (org.get("blog") or "").strip()
                website = blog if blog.startswith("http") else (f"https://{blog}" if blog else "")
                email = (org.get("email") or "").strip()
                if not website and not email:
                    continue  # nothing to reach them at or look a contact up with — skip
                companies.append({
                    "company": org.get("name") or org.get("login", ""),
                    "website": website, "email": email, "phone": "",
                    "location": org.get("location") or region, "industry": keyword,
                })
    return companies

async def fetch_github_leads(regions, industries, count) -> List[dict]:
    global _github_ok
    companies = await fetch_github_companies(regions, industries, count * 4)
    leads = []
    for comp in companies:
        if len(leads) >= count:
            break
        if comp["email"]:
            # Org lists a contact email directly — no Hunter lookup needed.
            leads.append({
                "company": comp["company"], "contact_name": "", "title": "",
                "email": comp["email"], "phone": "", "location": comp["location"],
                "industry": comp["industry"], "website": comp["website"], "pain_point": "",
            })
            continue
        if not comp["website"] or not HUNTER_API_KEY:
            continue
        domain = _domain_from_url(comp["website"])
        try:
            contact = await fetch_hunter_contact(domain)
        except Exception as e:
            logger.warning(f"Hunter lookup failed for {domain}: {e}")
            continue
        if not contact:
            continue
        leads.append({
            "company": comp["company"], "contact_name": contact["contact_name"],
            "title": contact["title"], "email": contact["email"], "phone": "",
            "location": comp["location"], "industry": comp["industry"],
            "website": comp["website"], "pain_point": "",
        })
    _github_ok = True
    return leads


# ---------------------------------------------------------------------------
# Real lead sourcing via OpenStreetMap (free, no API key or billing) + Hunter.io.
# Third real source — works even without a Google Cloud billing account, at
# the cost of coarser business categorization than Places (OSM's "office" tag
# doesn't distinguish verticals like "Fintech" from "IT Services").
#
# Nominatim/Overpass are shared, rate-limited public services — this queries
# once per region (not per region x industry, unlike Places) and pauses
# between geocoding calls to stay within their fair-use guidelines. Fine for
# occasional lead-gen runs; not meant for high-volume/bulk use.
# ---------------------------------------------------------------------------
_osm_hunter_ok = None  # None=untested, True=working, False=blocked

_NOMINATIM_UA = f"OutreachPilot-LeadGen/1.0 (contact: {SENDER_EMAIL or 'no-reply@example.com'})"

async def _geocode_region(c: httpx.AsyncClient, region: str) -> Optional[tuple]:
    """Region name -> (south, west, north, east) bounding box, via OSM's free Nominatim geocoder."""
    resp = await c.get("https://nominatim.openstreetmap.org/search",
                       params={"q": region, "format": "json", "limit": 1},
                       headers={"User-Agent": _NOMINATIM_UA})
    if resp.is_error:
        return None
    results = resp.json()
    if not results or not results[0].get("boundingbox"):
        return None
    south, north, west, east = (float(x) for x in results[0]["boundingbox"])
    return south, west, north, east

async def fetch_osm_companies(regions, industries, limit) -> List[dict]:
    """Real companies with a listed website, via OpenStreetMap Overpass — free, no API key."""
    companies = []
    keyword = (industries[0] if industries else "").lower()
    async with httpx.AsyncClient(timeout=30) as c:
        for region in regions:
            if len(companies) >= limit:
                break
            await asyncio.sleep(1)  # Nominatim fair-use: max ~1 request/second
            bbox = await _geocode_region(c, region)
            if not bbox:
                continue
            south, west, north, east = bbox
            query = (f'[out:json][timeout:25];(node["office"]({south},{west},{north},{east});'
                     f'way["office"]({south},{west},{north},{east}););out center tags {limit * 3};')
            resp = await c.post("https://overpass-api.de/api/interpreter",
                                data={"data": query}, headers={"User-Agent": _NOMINATIM_UA})
            if resp.is_error:
                continue
            region_matches = []
            for el in resp.json().get("elements", []):
                tags = el.get("tags", {})
                name = tags.get("name")
                website = tags.get("website") or tags.get("contact:website")
                if not name or not website:
                    continue
                region_matches.append({
                    "company": name,
                    "website": website,
                    "phone": tags.get("phone") or tags.get("contact:phone") or "",
                    "location": ", ".join(x for x in [tags.get("addr:city"), tags.get("addr:country")] if x) or region,
                    "industry": industries[0] if industries else "",
                    "_office_tag": (tags.get("office") or "").lower(),
                })
            # Soft industry filter: OSM's "office" tag is too coarse to hard-filter on, so
            # prefer matches that mention the target industry, but don't exclude the rest.
            if keyword:
                region_matches.sort(key=lambda m: 0 if keyword in (m["company"] + m["_office_tag"]).lower() else 1)
            for m in region_matches:
                m.pop("_office_tag", None)
            companies.extend(region_matches)
    return companies[:limit]

async def fetch_osm_hunter_leads(regions, industries, count) -> List[dict]:
    global _osm_hunter_ok
    companies = await fetch_osm_companies(regions, industries, count * 4)
    leads = []
    for comp in companies:
        if len(leads) >= count:
            break
        domain = _domain_from_url(comp["website"])
        try:
            contact = await fetch_hunter_contact(domain)
        except Exception as e:
            logger.warning(f"Hunter lookup failed for {domain}: {e}")
            continue
        if not contact:
            continue
        leads.append({
            "company": comp["company"], "contact_name": contact["contact_name"],
            "title": contact["title"], "email": contact["email"], "phone": comp.get("phone", ""),
            "location": comp.get("location", ""), "industry": comp.get("industry", ""),
            "website": comp["website"], "pain_point": "",
        })
    _osm_hunter_ok = True
    return leads

async def source_leads(settings: dict, count: int, region=None, industry=None):
    regions = [region] if region else settings.get("regions", ["Dubai, UAE", "United States"])
    industries = [industry] if industry else settings.get("industries", ["SaaS", "IT Services"])
    errors = []
    if APOLLO_API_KEY:
        try:
            leads = await fetch_apollo_leads(regions, industries, count)
            if leads:
                return leads, "apollo"
            errors.append("Apollo returned no matching people for your current filters.")
        except Exception as e:
            logger.error(f"Apollo failed: {e}")
            errors.append(f"Apollo: {e}")
    if HUNTER_API_KEY and GOOGLE_PLACES_API_KEY:
        try:
            leads = await fetch_places_hunter_leads(regions, industries, count)
            if leads:
                return leads, "places_hunter"
            errors.append("Google Places + Hunter found no matching companies for your current filters.")
        except Exception as e:
            logger.error(f"Places/Hunter failed: {e}")
            errors.append(f"Places/Hunter: {e}")
    if HUNTER_API_KEY and FOURSQUARE_API_KEY:
        try:
            leads = await fetch_foursquare_hunter_leads(regions, industries, count)
            if leads:
                return leads, "foursquare_hunter"
            errors.append("Foursquare + Hunter found no matching companies for your current filters.")
        except Exception as e:
            logger.error(f"Foursquare/Hunter failed: {e}")
            errors.append(f"Foursquare/Hunter: {e}")
    if GITHUB_API_KEY:
        try:
            leads = await fetch_github_leads(regions, industries, count)
            if leads:
                return leads, "github"
            errors.append("GitHub found no matching organizations for your current filters.")
        except Exception as e:
            logger.error(f"GitHub failed: {e}")
            errors.append(f"GitHub: {e}")
    if HUNTER_API_KEY:
        try:
            leads = await fetch_osm_hunter_leads(regions, industries, count)
            if leads:
                return leads, "osm_hunter"
            errors.append("OpenStreetMap + Hunter found no matching companies for your current filters.")
        except Exception as e:
            logger.error(f"OSM/Hunter failed: {e}")
            errors.append(f"OSM/Hunter: {e}")
    raise RuntimeError(
        "No real lead source is available — " +
        (" ".join(errors) if errors else "No lead integrations are connected.") +
        " Connect Apollo, Google Places + Hunter, Foursquare + Hunter, GitHub, or just Hunter alone "
        "(free OpenStreetMap sourcing), or import a CSV of real contacts."
    )


# ---------------------------------------------------------------------------
# Live-signal personalization: pull a fresh, real detail from the lead's own
# homepage instead of relying purely on LLM invention.
# ---------------------------------------------------------------------------
def _clean_html_text(raw: str) -> str:
    text = html_lib.unescape(raw)
    return re.sub(r"\s+", " ", text).strip()

def _resolves_to_public_address(url: str) -> bool:
    """Blocks SSRF: refuses to fetch hosts that resolve to loopback/private/link-local/reserved IPs."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        for family, _, _, _, sockaddr in socket.getaddrinfo(parsed.hostname, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False

async def fetch_company_signal(website: str) -> str:
    """Best-effort: title + meta description from a lead's own website, truncated. Empty on any failure."""
    if not website:
        return ""
    url = website if website.startswith("http") else f"https://{website}"
    if not _resolves_to_public_address(url):
        return ""
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
            resp = await c.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; OutreachPilotBot/1.0)"})
        if resp.is_error:
            return ""
        page = resp.text[:20000]
        title_m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', page, re.I)
        parts = [_clean_html_text(m.group(1)) for m in (title_m, desc_m) if m and m.group(1).strip()]
        return " — ".join(parts)[:300]
    except Exception as e:
        logger.warning(f"Live-signal fetch failed for {website}: {e}")
        return ""

async def attach_live_signals(leads: List[dict]) -> List[dict]:
    async def _one(lead):
        lead["live_signal"] = await fetch_company_signal(lead.get("website", ""))
        return lead
    return list(await asyncio.gather(*[_one(l) for l in leads]))


DEFAULT_SEQUENCE_STEPS = [
    {"step_order": 1, "delay_days": 3,
     "angle": "Nudge: reference the first email lightly, then add one new angle — a verified proof "
              "point if one was provided, otherwise a specific detail on the project_idea or the "
              "cost of leaving the pain_point unaddressed. <=70 words."},
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
    proof_points = [p.strip() for p in (settings.get("proof_points") or []) if p.strip()]
    if proof_points:
        proof_rule = ("You may cite AT MOST ONE of these real, user-verified results if one fits "
                      "naturally — quote it accurately, do not alter numbers or add embellishment:\n"
                      + "\n".join(f"- {p}" for p in proof_points))
    else:
        proof_rule = "No verified results have been provided — do not cite any statistics or results at all."
    prompt = f"""For each prospect, write ONE short follow-up email per step below (they didn't reply
to the earlier email(s) in the sequence).
Sender: {sender}. Offer: {offer}.
{steps_desc}
{proof_rule}
Never invent statistics, client results, or case studies beyond what's listed above — the only
claims you can make are the pain_point, title, and industry given below, plus the verified result(s)
above if any were given. Use plain straight quotes/apostrophes and hyphens only — no smart quotes
or em-dashes.
All end with "{sender}". Subjects <=5 words, can start with "Re:".
Prospects: {json.dumps(compact)}
Return a JSON array where each item is {{"i": <index>, "followups": [{{"subject","body"}}, ...]}}
with exactly {len(steps)} followup(s) per prospect, in the same order as the steps above.
Return ONLY JSON."""
    raw = await llm_call(system, prompt)
    results = _extract_json(raw)
    for r in results:
        r["followups"] = [clean_copy_fields(f, ["subject", "body"]) for f in r.get("followups", [])]
    return results


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
    leads = await attach_live_signals(leads)
    leads = await attach_linkedin_drafts(settings, leads)
    has_inbox = bool(await pool.fetchval(
        "SELECT count(*) FROM inboxes WHERE user_id=$1 AND is_active=true", user_id))
    email_ready = _email_configured() or has_inbox
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
        deliver = email_ready and bool(to_email)
        suppressed_lead = await is_suppressed(user_id, to_email) if to_email else False
        wa = whatsapp_link(phone, lead, sender, settings.get("offer", "")) if phone else None
        await pool.execute("""
            INSERT INTO leads (id, user_id, company, contact_name, title, email, phone, location,
                                industry, website, pain_point, project_idea, estimated_value,
                                whatsapp_link, created_at, source, lead_source, replied, suppressed,
                                linkedin_note, linkedin_message)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,false,$18,$19,$20)
        """, lead_id, user_id, lead.get("company", ""), lead.get("contact_name", ""),
             lead.get("title", ""), to_email, phone, lead.get("location", ""),
             lead.get("industry", ""), lead.get("website", ""), lead.get("pain_point", ""),
             lead.get("project_idea", ""), lead.get("estimated_value", ""), wa, now_dt,
             source, lead_source, suppressed_lead,
             lead.get("linkedin_note", ""), lead.get("linkedin_message", ""))
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
            wa_body = build_whatsapp_message(lead, sender, settings.get("offer", ""))
            wa_res = await send_whatsapp(phone, wa_body, allow=True)
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

    src_label = {"apollo": "Apollo", "places_hunter": "Google Places + Hunter",
                "foursquare_hunter": "Foursquare + Hunter", "github": "GitHub",
                "osm_hunter": "OpenStreetMap + Hunter"}.get(lead_source, lead_source)
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


async def draft_emails_for_leads(user_id: str) -> dict:
    """Generate an initial email, follow-up sequence, and WhatsApp message for leads that
    already exist (e.g. CSV-imported) but don't have an initial email drafted yet."""
    settings = await get_or_create_settings(user_id)
    leads = recs(await pool.fetch("""
        SELECT * FROM leads WHERE user_id=$1 AND id NOT IN (
            SELECT lead_id FROM emails WHERE user_id=$1 AND type='initial' AND lead_id IS NOT NULL
        )
    """, user_id))
    if not leads:
        return {"drafted": 0, "whatsapp_sent": 0}

    has_inbox = bool(await pool.fetchval(
        "SELECT count(*) FROM inboxes WHERE user_id=$1 AND is_active=true", user_id))
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
    drafted = 0
    wa_sent = 0

    for idx, lead in enumerate(leads):
        lead_id = lead["id"]
        lead_source = lead.get("lead_source") or "csv"
        deliver = (_email_configured() or has_inbox) and lead_source != "ai"
        to_email = lead.get("email", "")
        phone = (lead.get("phone") or "").strip()
        suppressed_lead = await is_suppressed(user_id, to_email) if to_email else False

        em = email_by_i.get(idx, {})
        subject = em.get("subject", "Quick question")
        body = em.get("body", "")
        await pool.execute("""
            INSERT INTO emails (id, user_id, lead_id, company, contact_name, to_email, subject, body,
                                 channel, step, type, status, simulated, error, created_at,
                                 deliverable, lead_source, sent_at, variant)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'email',1,'initial',$9,false,NULL,$10,$11,$12,NULL,$13)
        """, str(uuid.uuid4()), user_id, lead_id, lead.get("company", ""),
             lead.get("contact_name", ""), to_email, subject, body,
             "suppressed" if suppressed_lead else "draft", now_dt, deliver, lead_source,
             subject_variant(idx))
        drafted += 1

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

        if phone:
            wa = whatsapp_link(phone, lead, sender, settings.get("offer", ""))
            wa_body = build_whatsapp_message(lead, sender, settings.get("offer", ""))
            wa_res = await send_whatsapp(phone, wa_body, allow=(lead_source != "ai"))
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
            await pool.execute("UPDATE leads SET whatsapp_link=$1 WHERE id=$2", wa, lead_id)

    await pool.execute("""
        INSERT INTO activity (id, user_id, type, message, created_at)
        VALUES ($1,$2,'manual',$3,$4)
    """, str(uuid.uuid4()), user_id, f"Drafted emails for {drafted} imported lead(s).", now_dt)
    return {"drafted": drafted, "whatsapp_sent": wa_sent}


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

AUTO_DRAFT_INTENTS = ("interested", "question")

async def generate_reply_draft(settings: dict, incoming_body: str, intent: str) -> dict:
    """Draft a suggested reply-to-the-reply. Lands in the Outbox as an editable draft."""
    sender = settings.get("sender_name", "Alex")
    offer = settings.get("offer", "custom software development")
    meeting_link = (settings.get("meeting_link") or "").strip()
    meeting_note = f' A booking link is available: {meeting_link}.' if meeting_link else ""
    system = ("You are an expert at replying to inbound cold-email responses. Write a short, "
              "warm, professional reply. Output ONLY valid JSON.")
    prompt = f"""A prospect replied to a cold email. Their reply intent was classified as "{intent}".
Sender: {sender}. Offer: {offer}.{meeting_note}
Their reply:
{incoming_body[:800]}

Write a short reply (<=90 words) that directly responds to what they said and moves the
conversation forward appropriately for a "{intent}" reply. End with "{sender}".
Return JSON: {{"subject": "...", "body": "..."}}. Return ONLY JSON."""
    raw = await llm_call(system, prompt)
    return _extract_json(raw)


# ---------------------------------------------------------------------------
# LinkedIn outreach drafting — the note + first message are written automatically
# for every new lead, but sending is deliberately NOT automated: LinkedIn's ToS
# prohibits automating actions on a personal account, and doing so risks the
# user's account being banned. The user still copy-pastes the draft themselves.
# ---------------------------------------------------------------------------
async def generate_linkedin_message(settings: dict, lead: dict) -> dict:
    sender = settings.get("sender_name", "Alex")
    offer = settings.get("offer", "custom software development")
    system = ("You write short, natural LinkedIn outreach text — a connection request note "
              "and a first message. Output ONLY valid JSON.")
    prompt = f"""Write a LinkedIn connection note and a short first message for this prospect.
Sender: {sender}. Offer: {offer}.
Prospect: {lead.get('contact_name','')}, {lead.get('title','')} at {lead.get('company','')}.
Pain point: {lead.get('pain_point','')}.

Connection note: <=300 characters (LinkedIn's limit), no pitch, just a genuine reason to connect.
First message (sent only after they accept): <=60 words, references the pain_point, one soft CTA.
Both end with "{sender}".
Return JSON: {{"connection_note": "...", "first_message": "..."}}. Return ONLY JSON."""
    raw = await llm_call(system, prompt)
    return _extract_json(raw)

async def attach_linkedin_drafts(settings: dict, leads: List[dict]) -> List[dict]:
    """Best-effort: pre-write the LinkedIn note + first message for each named lead, so
    there's a ready-to-paste draft waiting instead of a manual per-lead 'Draft' click.
    Still text only — the user still copy-pastes it into LinkedIn themselves."""
    async def _one(lead):
        if not lead.get("contact_name"):
            return lead
        try:
            draft = await generate_linkedin_message(settings, lead)
            lead["linkedin_note"] = draft.get("connection_note", "")
            lead["linkedin_message"] = draft.get("first_message", "")
        except Exception as e:
            logger.warning(f"Auto LinkedIn draft failed for {lead.get('company')}: {e}")
        return lead
    return list(await asyncio.gather(*[_one(l) for l in leads]))


# ---------------------------------------------------------------------------
# Voice-note personalization: script via the usual LLM, audio via OpenAI TTS
# (OpenAI specifically — Anthropic has no text-to-speech endpoint).
# ---------------------------------------------------------------------------
async def generate_voice_script(settings: dict, em: dict) -> str:
    sender = settings.get("sender_name", "Alex")
    system = ("You write short voice-over scripts for personalized sales voice notes. "
              "Output plain spoken text only — no markdown, no labels.")
    prompt = f"""Turn this cold email into a warm, natural-sounding spoken voice note script
(<=70 words), first person, as if {sender} is leaving a friendly voicemail for the recipient.
No email formatting, no "Subject:", just natural spoken words ending with a simple sign-off.
Email subject: {em.get('subject', '')}
Email body: {em.get('body', '')}"""
    raw = await llm_call(system, prompt)
    return raw.strip().strip('"')

async def synthesize_voice(script: str) -> bytes:
    if not openai_client:
        raise RuntimeError("OPENAI_API_KEY not configured")
    resp = await openai_client.audio.speech.create(model="tts-1", voice="alloy", input=script)
    return resp.read() if hasattr(resp, "read") else bytes(resp.content)

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
            draft_note = ""
            if intent in AUTO_DRAFT_INTENTS:
                try:
                    lead_settings = await get_or_create_settings(lead.get("user_id"))
                    draft = await generate_reply_draft(lead_settings, replies[addr], intent)
                    await pool.execute("""
                        INSERT INTO emails (id, user_id, lead_id, company, contact_name, to_email, subject,
                                             body, channel, step, type, status, simulated, created_at, lead_source)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'email',1,'reply_draft','draft',false,$9,$10)
                    """, str(uuid.uuid4()), lead.get("user_id"), lead["id"], lead.get("company", ""),
                         lead.get("contact_name", ""), lead.get("email", ""),
                         draft.get("subject", "Re: following up"), draft.get("body", ""),
                         datetime.now(timezone.utc), lead.get("lead_source"))
                    draft_note = " A suggested reply is ready in the Outbox."
                except Exception as e:
                    logger.error(f"Reply draft generation failed: {e}")
            await pool.execute("""
                INSERT INTO activity (id, user_id, type, message, created_at)
                VALUES ($1,$2,'auto',$3,$4)
            """, str(uuid.uuid4()), lead.get("user_id"),
                 (f"Reply detected from {lead.get('contact_name','')} "
                  f"({lead.get('company','')}) — intent: {intent}. Follow-ups auto-stopped.{draft_note}"),
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
async def _gen_referral_code() -> str:
    for _ in range(5):
        code = secrets.token_hex(4).upper()
        if not await pool.fetchval("SELECT 1 FROM users WHERE referral_code=$1", code):
            return code
    return secrets.token_hex(6).upper()

@api_router.post("/auth/register")
async def register(data: RegisterInput, request: Request, response: Response):
    rate_limit(f"register:{request.client.host}", max_requests=5, window_seconds=3600)
    email = data.email.lower()
    if await pool.fetchrow("SELECT 1 FROM users WHERE email=$1", email):
        raise HTTPException(status_code=400, detail="Email already registered")
    referred_by = None
    if data.ref:
        referrer = rec(await pool.fetchrow("SELECT id FROM users WHERE referral_code=$1", data.ref.strip().upper()))
        if referrer:
            referred_by = referrer["id"]
    referral_code = await _gen_referral_code()
    row = await pool.fetchrow("""
        INSERT INTO users (email, name, password_hash, role, referral_code, referred_by)
        VALUES ($1,$2,$3,'user',$4,$5) RETURNING id
    """, email, data.name, hash_password(data.password), referral_code, referred_by)
    uid = row["id"]
    set_auth_cookies(response, create_access_token(uid, email), create_refresh_token(uid))
    return {"id": uid, "email": email, "name": data.name, "role": "user", "owner_id": None}

@api_router.post("/auth/login")
async def login(data: LoginInput, request: Request, response: Response):
    rate_limit(f"login:{request.client.host}", max_requests=10, window_seconds=300)
    email = data.email.lower()
    user = rec(await pool.fetchrow("SELECT * FROM users WHERE email=$1", email))
    # Always run bcrypt, even for a nonexistent email, so response time can't be used to enumerate accounts.
    password_hash = user["password_hash"] if user else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(data.password, password_hash)
    if not user or not password_ok:
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

@api_router.post("/auth/change-password")
async def change_password(data: PasswordChangeInput, user: dict = Depends(get_current_user)):
    rate_limit(f"change-password:{user['id']}", max_requests=10, window_seconds=300)
    password_hash = await pool.fetchval("SELECT password_hash FROM users WHERE id=$1", user["id"])
    if not verify_password(data.current_password, password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    await pool.execute("UPDATE users SET password_hash=$1 WHERE id=$2",
                       hash_password(data.new_password), user["id"])
    return {"message": "Password updated"}

@api_router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    rate_limit(f"refresh:{request.client.host}", max_requests=30, window_seconds=300)
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
                            httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=43200, path="/")
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
    try:
        result = await execute_run(tenant_id(user), count, data.region, data.industry, data.offer,
                                   data.tone)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
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

@api_router.post("/leads/{lead_id}/linkedin-draft")
async def draft_linkedin_message(lead_id: str, user: dict = Depends(get_current_user)):
    tid = tenant_id(user)
    lead = rec(await pool.fetchrow("SELECT * FROM leads WHERE id=$1 AND user_id=$2", lead_id, tid))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    settings = await get_or_create_settings(tid)
    try:
        draft = await generate_linkedin_message(settings, lead)
    except Exception as e:
        logger.error(f"LinkedIn draft generation failed: {e}")
        raise HTTPException(status_code=502, detail=f"Draft generation failed: {e}")
    await pool.execute(
        "UPDATE leads SET linkedin_note=$1, linkedin_message=$2 WHERE id=$3",
        draft.get("connection_note", ""), draft.get("first_message", ""), lead_id)
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

@api_router.post("/emails/spam-check")
async def check_spam_score(data: SpamCheckInput, user: dict = Depends(get_current_user)):
    return spam_score(data.subject, data.body)

@api_router.post("/emails/{email_id}/voice-note")
async def generate_voice_note(email_id: str, user: dict = Depends(get_current_user)):
    tid = tenant_id(user)
    em = rec(await pool.fetchrow("SELECT * FROM emails WHERE id=$1 AND user_id=$2", email_id, tid))
    if not em:
        raise HTTPException(status_code=404, detail="Email not found")
    if not openai_client:
        raise HTTPException(status_code=400,
                            detail="Voice notes require OPENAI_API_KEY (OpenAI does the text-to-speech step)")
    settings = await get_or_create_settings(tid)
    try:
        script = await generate_voice_script(settings, em)
        audio_bytes = await synthesize_voice(script)
    except Exception as e:
        logger.error(f"Voice note generation failed: {e}")
        raise HTTPException(status_code=502, detail=f"Voice generation failed: {e}")
    VOICE_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    (VOICE_NOTES_DIR / f"{email_id}.mp3").write_bytes(audio_bytes)
    url = f"{BACKEND_URL}/api/voice/{email_id}.mp3" if BACKEND_URL else f"/api/voice/{email_id}.mp3"
    await pool.execute("UPDATE emails SET voice_note_url=$1 WHERE id=$2", url, email_id)
    return {"voice_note_url": url}

@api_router.get("/voice/{email_id}.mp3")
async def get_voice_note(email_id: str):
    path = VOICE_NOTES_DIR / f"{email_id}.mp3"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Voice note not found")
    return Response(content=path.read_bytes(), media_type="audio/mpeg")

async def _send_one_email(em: dict, user_id: str) -> dict:
    """Manual send always attempts real delivery to the address shown."""
    to_email = (em.get("to_email") or "").strip()
    inbox = None
    if not to_email:
        result = {"status": "failed", "error": "No recipient", "simulated": False}
    elif em.get("lead_source") == "ai":
        result = {"status": "failed", "simulated": False,
                  "error": ("This lead was AI-generated for demo purposes and is not a real, "
                            "contactable person — sending would likely bounce or reach an unrelated "
                            "business. Connect Apollo (Settings > Integrations) or import a CSV of "
                            "real contacts to send to actual prospects.")}
    else:
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
                            sender_name=$6, tone=$7, skills=$8, headline=$9, experience=$10, meeting_link=$11,
                            brand_name=$12, brand_logo_url=$13, proof_points=$14
        WHERE user_id=$15
    """, payload["daily_target"], payload["auto_enabled"], payload["regions"], payload["industries"],
         payload["offer"], payload["sender_name"], payload["tone"], payload["skills"],
         payload["headline"], payload["experience"], payload["meeting_link"],
         payload["brand_name"], payload["brand_logo_url"], payload["proof_points"], tid)
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
    enriched = 0
    for row in reader:
        email = (row.get("email") or "").strip().lower()
        website = (row.get("website") or "").strip()
        if not email and website and HUNTER_API_KEY:
            # No email given, but we have a domain — look up a real, verified one via Hunter
            # instead of skipping the row (uses your Hunter credits, not Google Places).
            try:
                contact = await fetch_hunter_contact(_domain_from_url(website))
            except Exception as e:
                logger.warning(f"Hunter lookup failed during import for {website}: {e}")
                contact = None
            if contact and contact.get("email"):
                email = contact["email"].strip().lower()
                row = {**row, "contact_name": row.get("contact_name") or contact.get("contact_name", ""),
                       "title": row.get("title") or contact.get("title", "")}
                enriched += 1
        if not email:
            skipped += 1
            continue
        exists = await pool.fetchval(
            "SELECT 1 FROM leads WHERE user_id=$1 AND email=$2", tenant_id(user), email)
        if exists:
            skipped += 1
            continue
        phone = (row.get("phone") or "").strip()
        wa = whatsapp_link(phone, row, sender, offer) if phone else None
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
         (f"Imported {imported} lead(s) from CSV ({skipped} skipped — missing email or duplicate; "
          f"{enriched} email(s) found via Hunter)."), now_dt)
    return {"imported": imported, "skipped": skipped, "enriched_via_hunter": enriched}

@api_router.post("/leads/draft-missing")
async def draft_missing_leads(user: dict = Depends(get_current_user)):
    """Generate cold email + follow-ups + WhatsApp for existing leads with no draft yet —
    the step CSV-imported (or otherwise manually-added) leads need before they can be sent."""
    return await draft_emails_for_leads(tenant_id(user))


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
# Referrals — tracked and shown to the user; no automated reward-crediting yet
# ---------------------------------------------------------------------------
@api_router.get("/referrals/status")
async def referral_status(user: dict = Depends(get_current_user)):
    tid = tenant_id(user)
    owner = rec(await pool.fetchrow("SELECT referral_code FROM users WHERE id=$1", tid))
    code = (owner or {}).get("referral_code")
    if not code:
        code = await _gen_referral_code()
        await pool.execute("UPDATE users SET referral_code=$1 WHERE id=$2", code, tid)
    referred_count = await pool.fetchval("SELECT count(*) FROM users WHERE referred_by=$1", tid)
    return {
        "referral_code": code,
        "referral_url": f"{FRONTEND_URL}/register?ref={code}",
        "referred_count": referred_count,
    }


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
# API keys — for Zapier/Make and other generic HTTP/webhook integrations
# ---------------------------------------------------------------------------
_KEY_PREFIX = "op_"

@api_router.get("/api-keys")
async def list_api_keys(user: dict = Depends(get_current_user)):
    return recs(await pool.fetch(
        "SELECT id, label, key_preview, created_at, last_used_at FROM api_keys WHERE user_id=$1 ORDER BY created_at DESC",
        tenant_id(user)))

@api_router.post("/api-keys")
async def create_api_key(data: ApiKeyInput, user: dict = Depends(get_current_user)):
    raw_key = _KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    preview = raw_key[:10] + "…"
    row = await pool.fetchrow("""
        INSERT INTO api_keys (id, user_id, label, key_hash, key_preview)
        VALUES ($1,$2,$3,$4,$5) RETURNING id, label, key_preview, created_at
    """, str(uuid.uuid4()), tenant_id(user), data.label, key_hash, preview)
    return {**rec(row), "key": raw_key}  # full key is only ever shown here, once

@api_router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str, user: dict = Depends(get_current_user)):
    res = await pool.execute("DELETE FROM api_keys WHERE id=$1 AND user_id=$2", key_id, tenant_id(user))
    if res == "DELETE 0":
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Public API (api_key auth, not cookies) — Zapier/Make and generic integrations
# ---------------------------------------------------------------------------
@public_router.get("/leads")
async def public_list_leads(tenant: str = Depends(get_api_tenant)):
    return recs(await pool.fetch(
        "SELECT * FROM leads WHERE user_id=$1 ORDER BY created_at DESC LIMIT 500", tenant))

@public_router.post("/leads")
async def public_create_lead(data: PublicLeadInput, tenant: str = Depends(get_api_tenant)):
    email = data.email.lower()
    if await pool.fetchval("SELECT 1 FROM leads WHERE user_id=$1 AND email=$2", tenant, email):
        raise HTTPException(status_code=409, detail="A lead with this email already exists")
    suppressed_lead = await is_suppressed(tenant, email)
    lead_id = str(uuid.uuid4())
    await pool.execute("""
        INSERT INTO leads (id, user_id, company, contact_name, title, email, phone, location,
                            industry, website, pain_point, created_at, source, lead_source, replied, suppressed)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'api','api',false,$13)
    """, lead_id, tenant, data.company, data.contact_name, data.title, email, data.phone,
         data.location, data.industry, data.website, data.pain_point,
         datetime.now(timezone.utc), suppressed_lead)
    return {"id": lead_id, "created": True}

@public_router.get("/emails")
async def public_list_emails(tenant: str = Depends(get_api_tenant)):
    return recs(await pool.fetch(
        "SELECT * FROM emails WHERE user_id=$1 ORDER BY created_at DESC LIMIT 500", tenant))


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

    admin_email = os.environ.get("ADMIN_EMAIL", "").strip()
    admin_pw = os.environ.get("ADMIN_PASSWORD", "").strip()
    if admin_email and admin_pw:
        existing = rec(await pool.fetchrow("SELECT * FROM users WHERE email=$1", admin_email))
        if not existing:
            await pool.execute(
                "INSERT INTO users (email, name, password_hash, role) VALUES ($1,'Admin',$2,'admin')",
                admin_email, hash_password(admin_pw))
        elif not verify_password(admin_pw, existing["password_hash"]):
            await pool.execute("UPDATE users SET password_hash=$1 WHERE email=$2",
                               hash_password(admin_pw), admin_email)
    else:
        logger.warning("ADMIN_EMAIL/ADMIN_PASSWORD not set — skipping admin account seeding")
    asyncio.create_task(scheduler_loop())
    logger.info("OutreachPilot started")

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()


app.include_router(api_router)
app.include_router(public_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
