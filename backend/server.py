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
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional
from urllib.parse import quote

import bcrypt
import jwt
import asyncpg
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr

import httpx
import smtplib
from email.message import EmailMessage
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

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

FOLLOWUP_DELAYS_DAYS = [3, 6]  # step 2 at +3 days, step 3 at +6 days
_apollo_ok = None  # None=untested, True=working, False=blocked (e.g. free plan)

def _email_configured() -> bool:
    return bool((SMTP_HOST and SMTP_USER and SMTP_PASSWORD) or RESEND_API_KEY)

def integrations_status() -> dict:
    return {
        "email_live": _email_configured(),
        "email_provider": "smtp" if (SMTP_HOST and SMTP_USER) else ("resend" if RESEND_API_KEY else None),
        "sender_email": SENDER_EMAIL if _email_configured() else None,
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

class EmailUpdate(BaseModel):
    to_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


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

async def generate_emails(settings: dict, leads: List[dict]):
    system = ("You are an expert cold email copywriter. Write short, personalized, "
              "high-converting cold emails. Output ONLY valid JSON.")
    sender = settings.get("sender_name", "Alex")
    offer = settings.get("offer", "custom software development")
    tone = settings.get("tone", "confident and concise")
    compact = [{"i": idx, "company": l.get("company"), "contact_name": l.get("contact_name"),
                "title": l.get("title"), "pain_point": l.get("pain_point"),
                "project_idea": l.get("project_idea"), "industry": l.get("industry")}
               for idx, l in enumerate(leads)]
    prompt = f"""Write a personalized cold email for each prospect below.
Sender name: {sender}. Offer: {offer}. Tone: {tone}.
Rules: <=120 words, one clear CTA (a 15-min call), reference their pain_point naturally,
and pitch the specific "project_idea" as what you could build for them. No fluff, no
"I hope this finds you well". Subject line <=6 words, curiosity-driven.
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
# Delivery: Resend email + Twilio WhatsApp (auto-live when keys present)
# ---------------------------------------------------------------------------
def _body_to_html(body: str) -> str:
    safe = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return ("<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:14px;"
            "line-height:1.6;color:#111\">" + safe.replace("\n", "<br>") + "</div>")

async def send_email(to_email: str, subject: str, body: str, allow: bool = True) -> dict:
    if not allow:
        return {"status": "sent", "simulated": True, "provider_id": None, "error": None}
    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
        try:
            await asyncio.to_thread(_smtp_send_sync, to_email, subject, body)
            return {"status": "sent", "simulated": False, "provider_id": "smtp", "error": None}
        except Exception as e:
            logger.error(f"SMTP send failed: {e}")
            return {"status": "failed", "simulated": False, "provider_id": None, "error": str(e)}
    if not RESEND_API_KEY:
        return {"status": "sent", "simulated": True, "provider_id": None, "error": None}
    try:
        import resend
        resend.api_key = RESEND_API_KEY
        params = {"from": SENDER_EMAIL, "to": [to_email], "subject": subject,
                  "html": _body_to_html(body)}
        res = await asyncio.to_thread(resend.Emails.send, params)
        pid = res.get("id") if isinstance(res, dict) else getattr(res, "id", None)
        return {"status": "sent", "simulated": False, "provider_id": pid, "error": None}
    except Exception as e:
        logger.error(f"Resend send failed: {e}")
        return {"status": "failed", "simulated": False, "provider_id": None, "error": str(e)}


def _smtp_send_sync(to_email: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_alternative(_body_to_html(body), subtype="html")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.ehlo()
        s.starttls()
        s.login(SMTP_USER, SMTP_PASSWORD)
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


async def generate_followups(settings: dict, leads: List[dict]):
    """Two follow-up emails per lead for a no-reply sequence."""
    system = ("You are an expert cold-email copywriter writing polite, value-add "
              "FOLLOW-UP emails for prospects who did not reply. Output ONLY valid JSON.")
    sender = settings.get("sender_name", "Alex")
    offer = settings.get("offer", "custom software development")
    compact = [{"i": idx, "company": l.get("company"), "contact_name": l.get("contact_name"),
                "title": l.get("title"), "pain_point": l.get("pain_point"),
                "industry": l.get("industry")} for idx, l in enumerate(leads)]
    prompt = f"""For each prospect, write TWO short follow-up emails (they didn't reply to the first).
Sender: {sender}. Offer: {offer}.
Follow-up #1 (nudge): reference the first email lightly, add one new angle/proof point, <=70 words.
Follow-up #2 (breakup): short, friendly last touch, create urgency without pressure, <=55 words.
Both end with "{sender}". Subjects <=5 words, can start with "Re:".
Prospects: {json.dumps(compact)}
Return a JSON array where each item is {{"i": <index>, "followups": [{{"subject","body"}}, {{"subject","body"}}]}}.
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
    deliver = _email_configured() and lead_source == "apollo"
    emails = await generate_emails(settings, leads)
    email_by_i = {e.get("i"): e for e in emails}
    try:
        fups = await generate_followups(settings, leads)
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
        wa = whatsapp_link(phone, lead.get("company", ""), sender,
                           settings.get("offer", "")) if phone else None
        await pool.execute("""
            INSERT INTO leads (id, user_id, company, contact_name, title, email, phone, location,
                                industry, website, pain_point, project_idea, estimated_value,
                                whatsapp_link, created_at, source, lead_source, replied)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,false)
        """, lead_id, user_id, lead.get("company", ""), lead.get("contact_name", ""),
             lead.get("title", ""), lead.get("email", ""), phone, lead.get("location", ""),
             lead.get("industry", ""), lead.get("website", ""), lead.get("pain_point", ""),
             lead.get("project_idea", ""), lead.get("estimated_value", ""), wa, now_dt,
             source, lead_source)
        created_leads += 1

        em = email_by_i.get(idx, {})
        subject = em.get("subject", "Quick question")
        body = em.get("body", "")
        to_email = lead.get("email", "")
        # Emails are created as editable DRAFTS — user sends them from the Outbox.
        await pool.execute("""
            INSERT INTO emails (id, user_id, lead_id, company, contact_name, to_email, subject, body,
                                 channel, step, type, status, simulated, error, created_at,
                                 deliverable, lead_source, sent_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'email',1,'initial','draft',false,NULL,$9,$10,$11,NULL)
        """, str(uuid.uuid4()), user_id, lead_id, lead.get("company", ""),
             lead.get("contact_name", ""), to_email, subject, body, now_dt, deliver, lead_source)
        created_emails += 1

        # Schedule follow-ups (sent later if the lead hasn't replied)
        for step_i, fu in enumerate(fups_by_i.get(idx, [])[:2]):
            delay = FOLLOWUP_DELAYS_DAYS[step_i] if step_i < len(FOLLOWUP_DELAYS_DAYS) else 6
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
        result = await send_email(fu.get("to_email", ""), fu.get("subject", ""),
                                  fu.get("body", ""), allow=fu.get("deliverable", False))
        await pool.execute(
            "UPDATE emails SET status=$1, simulated=$2, error=$3, sent_at=$4 WHERE id=$5",
            result["status"], result.get("simulated", False), result.get("error"),
            now if result["status"] == "sent" else None, fu["id"])
        if result["status"] == "sent":
            sent += 1
    if sent:
        await pool.execute("""
            INSERT INTO activity (id, user_id, type, message, created_at)
            VALUES ($1,$2,'auto',$3,$4)
        """, str(uuid.uuid4()), user_id, f"{sent} scheduled follow-up email(s) sent to non-responders.", now)
    return sent


def _fetch_reply_senders_sync(days: int = 21) -> set:
    import imaplib
    from email.utils import parseaddr
    senders = set()
    M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        M.login(SMTP_USER, SMTP_PASSWORD)
        M.select("INBOX")
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = M.search(None, f'(SINCE {since})')
        ids = data[0].split() if data and data[0] else []
        for i in ids[-250:]:
            typ, msgdata = M.fetch(i, "(BODY[HEADER.FIELDS (FROM)])")
            for part in msgdata:
                if isinstance(part, tuple) and part[1]:
                    hdr = part[1].decode(errors="ignore")
                    _, addr = parseaddr(hdr)
                    if addr:
                        senders.add(addr.lower())
    finally:
        try:
            M.logout()
        except Exception:
            pass
    return senders

async def scan_replies(user_id: str = None) -> dict:
    """Read the inbox over IMAP and auto-stop follow-ups for any lead that replied."""
    if not (SMTP_USER and SMTP_PASSWORD):
        return {"matched": 0, "error": "Email not configured"}
    try:
        senders = await asyncio.to_thread(_fetch_reply_senders_sync)
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
        if (lead.get("email") or "").lower() in senders:
            await pool.execute("UPDATE leads SET replied=true WHERE id=$1", lead["id"])
            await pool.execute(
                "UPDATE emails SET status='cancelled' WHERE lead_id=$1 AND type='follow_up' AND status='scheduled'",
                lead["id"])
            await pool.execute("""
                INSERT INTO activity (id, user_id, type, message, created_at)
                VALUES ($1,$2,'auto',$3,$4)
            """, str(uuid.uuid4()), lead.get("user_id"),
                 (f"Reply detected from {lead.get('contact_name','')} "
                  f"({lead.get('company','')}) — follow-ups auto-stopped."),
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
    return {"id": uid, "email": email, "name": data.name, "role": "user"}

@api_router.post("/auth/login")
async def login(data: LoginInput, response: Response):
    email = data.email.lower()
    user = rec(await pool.fetchrow("SELECT * FROM users WHERE email=$1", email))
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    uid = user["id"]
    set_auth_cookies(response, create_access_token(uid, email), create_refresh_token(uid))
    return {"id": uid, "email": email, "name": user.get("name", ""), "role": user.get("role", "user")}

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
    uid = user["id"]
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
    return {
        "total_leads": total_leads, "emails_sent": emails_sent,
        "whatsapp_ready": wa_ready, "leads_with_phone": leads_with_phone,
        "daily_target": settings.get("daily_target", 100),
        "auto_enabled": settings.get("auto_enabled", True),
        "followups_queued": followups_queued, "replied": replied,
        "drafts": drafts,
        "volume": volume,
        "integrations": integrations_status(),
    }

@api_router.get("/integrations/status")
async def integrations(user: dict = Depends(get_current_user)):
    return integrations_status()

@api_router.post("/integrations/test-email")
async def test_email(user: dict = Depends(get_current_user)):
    result = await send_email(user["email"],
                              "OutreachPilot — test email ✅",
                              f"Hi {user.get('name','there')},\n\nYour SMTP email delivery is working. "
                              f"OutreachPilot can now send cold emails from your account.\n\n— OutreachPilot")
    return result

@api_router.post("/automation/run")
async def run_now(data: RunInput, user: dict = Depends(get_current_user)):
    count = max(1, min(data.count, 15))
    result = await execute_run(user["id"], count, data.region, data.industry, data.offer, data.tone)
    await pool.execute("UPDATE settings SET last_run=$1 WHERE user_id=$2",
                       datetime.fromisoformat(result["run_at"]), user["id"])
    return result

@api_router.get("/leads")
async def list_leads(user: dict = Depends(get_current_user)):
    return recs(await pool.fetch(
        "SELECT * FROM leads WHERE user_id=$1 ORDER BY created_at DESC LIMIT 500", user["id"]))

@api_router.get("/emails")
async def list_emails(channel: Optional[str] = None, user: dict = Depends(get_current_user)):
    if channel:
        rows = await pool.fetch(
            "SELECT * FROM emails WHERE user_id=$1 AND channel=$2 ORDER BY created_at DESC LIMIT 1000",
            user["id"], channel)
    else:
        rows = await pool.fetch(
            "SELECT * FROM emails WHERE user_id=$1 ORDER BY created_at DESC LIMIT 1000", user["id"])
    return recs(rows)

@api_router.get("/activity")
async def list_activity(user: dict = Depends(get_current_user)):
    return recs(await pool.fetch(
        "SELECT * FROM activity WHERE user_id=$1 ORDER BY created_at DESC LIMIT 200", user["id"]))

@api_router.put("/emails/{email_id}")
async def edit_email(email_id: str, data: EmailUpdate, user: dict = Depends(get_current_user)):
    em = rec(await pool.fetchrow("SELECT * FROM emails WHERE id=$1 AND user_id=$2", email_id, user["id"]))
    if not em:
        raise HTTPException(status_code=404, detail="Email not found")
    if em.get("status") == "sent":
        raise HTTPException(status_code=400, detail="Email already sent")
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if upd:
        set_clause = ", ".join(f"{k}=${i + 2}" for i, k in enumerate(upd.keys()))
        await pool.execute(f"UPDATE emails SET {set_clause} WHERE id=$1", email_id, *upd.values())
    return rec(await pool.fetchrow("SELECT * FROM emails WHERE id=$1", email_id))

async def _send_one_email(em: dict) -> dict:
    """Manual send always attempts real delivery to the address shown."""
    to_email = (em.get("to_email") or "").strip()
    if not to_email:
        return {"status": "failed", "error": "No recipient", "simulated": False}
    result = await send_email(to_email, em.get("subject", ""), em.get("body", ""), allow=True)
    now = datetime.now(timezone.utc)
    await pool.execute(
        "UPDATE emails SET status=$1, simulated=$2, error=$3, sent_at=$4 WHERE id=$5",
        result["status"], result.get("simulated", False), result.get("error"),
        now if result["status"] == "sent" else None, em["id"])
    return result

@api_router.post("/emails/{email_id}/send")
async def send_one(email_id: str, user: dict = Depends(get_current_user)):
    em = rec(await pool.fetchrow("SELECT * FROM emails WHERE id=$1 AND user_id=$2", email_id, user["id"]))
    if not em:
        raise HTTPException(status_code=404, detail="Email not found")
    if em.get("status") == "sent":
        return {"status": "sent", "already": True}
    result = await _send_one_email(em)
    await pool.execute("""
        INSERT INTO activity (id, user_id, type, message, created_at)
        VALUES ($1,$2,'manual',$3,$4)
    """, str(uuid.uuid4()), user["id"],
         (f"Email to {em.get('contact_name','')} ({em.get('company','')}) "
          f"{'sent' if result['status']=='sent' else 'failed to send'}."),
         datetime.now(timezone.utc))
    return result

@api_router.post("/emails/send-all")
async def send_all(user: dict = Depends(get_current_user)):
    drafts = recs(await pool.fetch("""
        SELECT * FROM emails WHERE user_id=$1 AND channel='email' AND type='initial'
        AND status = ANY($2::text[]) LIMIT 1000
    """, user["id"], ["draft", "failed"]))
    sent = 0
    failed = 0
    for em in drafts:
        result = await _send_one_email(em)
        if result["status"] == "sent":
            sent += 1
        else:
            failed += 1
    await pool.execute("""
        INSERT INTO activity (id, user_id, type, message, created_at)
        VALUES ($1,$2,'manual',$3,$4)
    """, str(uuid.uuid4()), user["id"], f"Send all: {sent} email(s) sent, {failed} failed.",
         datetime.now(timezone.utc))
    return {"sent": sent, "failed": failed}

@api_router.post("/leads/{lead_id}/replied")
async def mark_replied(lead_id: str, user: dict = Depends(get_current_user)):
    res = await pool.execute("UPDATE leads SET replied=true WHERE id=$1 AND user_id=$2", lead_id, user["id"])
    if res == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Lead not found")
    cancelled = await pool.execute(
        "UPDATE emails SET status='cancelled' WHERE lead_id=$1 AND type='follow_up' AND status='scheduled'",
        lead_id)
    cancelled_count = int(cancelled.split()[-1]) if cancelled.startswith("UPDATE") else 0
    return {"replied": True, "cancelled_followups": cancelled_count}

@api_router.post("/followups/process")
async def followups_process(user: dict = Depends(get_current_user)):
    sent = await process_due_followups(user["id"])
    return {"sent": sent}

@api_router.post("/replies/scan")
async def replies_scan(user: dict = Depends(get_current_user)):
    return await scan_replies(user["id"])

@api_router.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    return await get_or_create_settings(user["id"])

@api_router.put("/settings")
async def update_settings(data: SettingsInput, user: dict = Depends(get_current_user)):
    payload = data.model_dump()
    await get_or_create_settings(user["id"])  # ensure row exists
    await pool.execute("""
        UPDATE settings SET daily_target=$1, auto_enabled=$2, regions=$3, industries=$4, offer=$5,
                            sender_name=$6, tone=$7, skills=$8, headline=$9, experience=$10
        WHERE user_id=$11
    """, payload["daily_target"], payload["auto_enabled"], payload["regions"], payload["industries"],
         payload["offer"], payload["sender_name"], payload["tone"], payload["skills"],
         payload["headline"], payload["experience"], user["id"])
    return await get_or_create_settings(user["id"])


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
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
