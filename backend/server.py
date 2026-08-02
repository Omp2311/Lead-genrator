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
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from urllib.parse import quote

import bcrypt
import jwt
from bson import ObjectId
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr

import httpx
from emergentintegrations.llm.chat import LlmChat, UserMessage

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = "HS256"

# Optional third-party providers (features go live automatically when keys are set)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev").strip()
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "").strip()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()

FOLLOWUP_DELAYS_DAYS = [3, 6]  # step 2 at +3 days, step 3 at +6 days

def integrations_status() -> dict:
    return {
        "email_live": bool(RESEND_API_KEY),
        "sender_email": SENDER_EMAIL if RESEND_API_KEY else None,
        "leads_live": bool(APOLLO_API_KEY),
        "whatsapp_live": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM),
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
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["id"] = str(user.pop("_id"))
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

async def llm_call(system: str, prompt: str) -> str:
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"op-{uuid.uuid4()}",
                   system_message=system).with_model("openai", "gpt-5.4")
    return await chat.send_message(UserMessage(text=prompt))

async def generate_leads(settings: dict, count: int, region=None, industry=None):
    regions = [region] if region else settings.get("regions", ["Dubai, UAE", "USA"])
    industries = [industry] if industry else settings.get("industries", ["SaaS", "IT Services"])
    system = ("You are a B2B sales research assistant that produces realistic, plausible "
              "prospect company profiles for a cold outreach demo. Output ONLY valid JSON.")
    prompt = f"""Generate {count} realistic B2B prospect leads for a cold-outreach demo.
Target regions: {', '.join(regions)}. Target industries: {', '.join(industries)}.
Focus on high-IT-density cities (Dubai, Silicon Valley, New York, Austin, London).
Each lead is a decision maker (Founder/CTO/Head of Growth) at a plausible company.
Return a JSON array. Each item MUST have keys:
"company", "contact_name", "title", "email" (plausible corporate email),
"phone" (E.164 with country code, or empty string for ~30% of them),
"location", "industry", "website", "pain_point" (1 short sentence specific to them).
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
                "industry": l.get("industry")} for idx, l in enumerate(leads)]
    prompt = f"""Write a personalized cold email for each prospect below.
Sender name: {sender}. Offer: {offer}. Tone: {tone}.
Rules: <=120 words, one clear CTA (a 15-min call), reference their pain_point naturally,
no fluff, no "I hope this finds you well". Subject line <=6 words, curiosity-driven.
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

async def send_email(to_email: str, subject: str, body: str) -> dict:
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

async def send_whatsapp(to_phone: str, body: str) -> dict:
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM):
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
        raise RuntimeError(f"Apollo search error {resp.status_code}")
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

    leads = await generate_leads(settings, count, region, industry)
    emails = await generate_emails(settings, leads)
    email_by_i = {e.get("i"): e for e in emails}

    now = datetime.now(timezone.utc).isoformat()
    created_emails = 0
    created_leads = 0
    for idx, lead in enumerate(leads):
        lead_id = str(uuid.uuid4())
        phone = (lead.get("phone") or "").strip()
        wa = whatsapp_link(phone, lead.get("company", ""), settings.get("sender_name", "Alex"),
                           settings.get("offer", "")) if phone else None
        lead_doc = {
            "_id": lead_id, "user_id": user_id, "company": lead.get("company", ""),
            "contact_name": lead.get("contact_name", ""), "title": lead.get("title", ""),
            "email": lead.get("email", ""), "phone": phone, "location": lead.get("location", ""),
            "industry": lead.get("industry", ""), "website": lead.get("website", ""),
            "pain_point": lead.get("pain_point", ""), "whatsapp_link": wa,
            "created_at": now, "source": source,
        }
        await db.leads.insert_one(lead_doc)
        created_leads += 1

        em = email_by_i.get(idx, {})
        email_doc = {
            "_id": str(uuid.uuid4()), "user_id": user_id, "lead_id": lead_id,
            "company": lead.get("company", ""), "contact_name": lead.get("contact_name", ""),
            "to_email": lead.get("email", ""),
            "subject": em.get("subject", "Quick question"),
            "body": em.get("body", ""),
            "channel": "email", "status": "sent", "created_at": now, "sent_at": now,
        }
        await db.emails.insert_one(email_doc)
        created_emails += 1

        if wa:
            await db.emails.insert_one({
                "_id": str(uuid.uuid4()), "user_id": user_id, "lead_id": lead_id,
                "company": lead.get("company", ""), "contact_name": lead.get("contact_name", ""),
                "to_email": phone, "subject": "WhatsApp proposal",
                "body": f"WhatsApp proposal ready for {lead.get('company','')}.",
                "channel": "whatsapp", "status": "ready", "whatsapp_link": wa,
                "created_at": now, "sent_at": None,
            })

    await db.activity.insert_one({
        "_id": str(uuid.uuid4()), "user_id": user_id, "type": source,
        "message": f"Outreach run: {created_leads} leads discovered, {created_emails} cold emails sent.",
        "created_at": now,
    })
    return {"leads": created_leads, "emails": created_emails, "run_at": now}


async def get_or_create_settings(user_id: str) -> dict:
    s = await db.settings.find_one({"user_id": user_id}, {"_id": 0})
    if not s:
        default = SettingsInput().model_dump()
        default["user_id"] = user_id
        default["last_run"] = None
        await db.settings.insert_one({**default, "_id": str(uuid.uuid4())})
        return default
    return s


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api_router.post("/auth/register")
async def register(data: RegisterInput, response: Response):
    email = data.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {"email": email, "name": data.name, "password_hash": hash_password(data.password),
           "role": "user", "created_at": datetime.now(timezone.utc).isoformat()}
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    set_auth_cookies(response, create_access_token(uid, email), create_refresh_token(uid))
    return {"id": uid, "email": email, "name": data.name, "role": "user"}

@api_router.post("/auth/login")
async def login(data: LoginInput, response: Response):
    email = data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    uid = str(user["_id"])
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
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        response.set_cookie("access_token", create_access_token(str(user["_id"]), user["email"]),
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
    total_leads = await db.leads.count_documents({"user_id": uid})
    emails_sent = await db.emails.count_documents({"user_id": uid, "channel": "email", "status": "sent"})
    wa_ready = await db.emails.count_documents({"user_id": uid, "channel": "whatsapp"})
    leads_with_phone = await db.leads.count_documents({"user_id": uid, "phone": {"$ne": ""}})

    # last 7 days email volume
    volume = []
    for d in range(6, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=d)).date().isoformat()
        cnt = await db.emails.count_documents({
            "user_id": uid, "channel": "email",
            "sent_at": {"$gte": day + "T00:00:00", "$lte": day + "T23:59:59.999999"}
        })
        volume.append({"day": day[5:], "emails": cnt})

    settings = await get_or_create_settings(uid)
    return {
        "total_leads": total_leads, "emails_sent": emails_sent,
        "whatsapp_ready": wa_ready, "leads_with_phone": leads_with_phone,
        "daily_target": settings.get("daily_target", 100),
        "auto_enabled": settings.get("auto_enabled", True),
        "volume": volume,
    }

@api_router.post("/automation/run")
async def run_now(data: RunInput, user: dict = Depends(get_current_user)):
    count = max(1, min(data.count, 15))
    result = await execute_run(user["id"], count, data.region, data.industry, data.offer, data.tone)
    await db.settings.update_one({"user_id": user["id"]},
                                 {"$set": {"last_run": result["run_at"]}})
    return result

@api_router.get("/leads")
async def list_leads(user: dict = Depends(get_current_user)):
    leads = await db.leads.find({"user_id": user["id"]}).sort("created_at", -1).to_list(500)
    for l in leads:
        l["id"] = l.pop("_id")
    return leads

@api_router.get("/emails")
async def list_emails(channel: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"user_id": user["id"]}
    if channel:
        q["channel"] = channel
    emails = await db.emails.find(q).sort("created_at", -1).to_list(1000)
    for e in emails:
        e["id"] = e.pop("_id")
    return emails

@api_router.get("/activity")
async def list_activity(user: dict = Depends(get_current_user)):
    acts = await db.activity.find({"user_id": user["id"]}).sort("created_at", -1).to_list(200)
    for a in acts:
        a["id"] = a.pop("_id")
    return acts

@api_router.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    return await get_or_create_settings(user["id"])

@api_router.put("/settings")
async def update_settings(data: SettingsInput, user: dict = Depends(get_current_user)):
    payload = data.model_dump()
    await db.settings.update_one({"user_id": user["id"]}, {"$set": payload}, upsert=True)
    return await get_or_create_settings(user["id"])


# ---------------------------------------------------------------------------
# Background daily scheduler
# ---------------------------------------------------------------------------
async def scheduler_loop():
    await asyncio.sleep(20)
    while True:
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            async for s in db.settings.find({"auto_enabled": True}):
                uid = s.get("user_id")
                last = s.get("last_run") or ""
                if not uid or last.startswith(today):
                    continue
                try:
                    await execute_run(uid, 8, source="auto")
                    await db.settings.update_one({"user_id": uid},
                        {"$set": {"last_run": datetime.now(timezone.utc).isoformat()}})
                    logger.info(f"Auto run completed for {uid}")
                except Exception as e:
                    logger.error(f"Auto run failed for {uid}: {e}")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        await asyncio.sleep(3600)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@outreachpilot.com")
    admin_pw = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({"email": admin_email, "name": "Admin",
            "password_hash": hash_password(admin_pw), "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()})
    elif not verify_password(admin_pw, existing["password_hash"]):
        await db.users.update_one({"email": admin_email},
                                  {"$set": {"password_hash": hash_password(admin_pw)}})
    asyncio.create_task(scheduler_loop())
    logger.info("OutreachPilot started")

@app.on_event("shutdown")
async def shutdown():
    client.close()


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
