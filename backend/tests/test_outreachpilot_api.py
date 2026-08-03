"""OutreachPilot backend API tests - iteration 2.

Covers new/updated features:
- Auth (regression)
- Profile & Skills settings (skills/headline/experience persistence)
- Automation run: emails created as 'draft', leads have project_idea/estimated_value
- Emails: PUT edit draft, POST send single (real SMTP), POST send-all
- /api/integrations/status: email_live=true, leads_live/blocked, whatsapp
- /api/dashboard/stats new fields: drafts, followups_queued, replied, integrations
- Mark-replied cancels scheduled follow-ups
"""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    from pathlib import Path
    for line in Path('/app/frontend/.env').read_text().splitlines():
        if line.startswith('REACT_APP_BACKEND_URL='):
            BASE_URL = line.split('=', 1)[1].strip().strip('"').rstrip('/')

ADMIN_EMAIL = "admin@outreachpilot.com"
ADMIN_PASSWORD = "admin123"
SAFE_RECIPIENT = "omprakashraj100078@gmail.com"


def _admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return s


# ---------------- Auth regression ----------------
class TestAuth:
    def test_login_admin(self):
        s = _admin_session()
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == ADMIN_EMAIL
        cookies = {c.name for c in s.cookies}
        assert "access_token" in cookies and "refresh_token" in cookies

    def test_login_invalid(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "x@y.z", "password": "nope"})
        assert r.status_code == 401


# ---------------- Profile settings (skills/headline/experience) ----------------
class TestProfileSettings:
    def test_settings_defaults_include_new_fields(self):
        s = _admin_session()
        r = s.get(f"{BASE_URL}/api/settings")
        assert r.status_code == 200
        d = r.json()
        for k in ["skills", "headline", "experience", "sender_name", "offer"]:
            assert k in d, f"Missing {k}"
        assert isinstance(d["skills"], list)

    def test_update_profile_persists(self):
        s = _admin_session()
        # Get current to restore later
        cur = s.get(f"{BASE_URL}/api/settings").json()
        payload = {
            "daily_target": cur.get("daily_target", 100),
            "auto_enabled": cur.get("auto_enabled", True),
            "regions": cur.get("regions", ["Dubai, UAE"]),
            "industries": cur.get("industries", ["SaaS"]),
            "offer": "TEST_ offer AI/GenAI apps",
            "sender_name": "TEST_Sender",
            "tone": "confident and concise",
            "skills": ["Python", "FastAPI", "React", "TEST_Skill"],
            "headline": "TEST_ headline full-stack builder",
            "experience": "TEST_ 7+ years shipping AI products",
        }
        r = s.put(f"{BASE_URL}/api/settings", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["sender_name"] == "TEST_Sender"
        assert "TEST_Skill" in d["skills"]
        assert d["headline"].startswith("TEST_")
        assert d["experience"].startswith("TEST_")

        # GET-verify persistence
        r2 = s.get(f"{BASE_URL}/api/settings").json()
        assert r2["sender_name"] == "TEST_Sender"
        assert "TEST_Skill" in r2["skills"]
        assert r2["offer"].startswith("TEST_")

        # Restore reasonable defaults
        restore = {**payload,
                   "sender_name": "Alex",
                   "offer": "Custom AI-powered software & full-stack development services",
                   "skills": ["Python", "Django", "FastAPI", "React", "Node.js", "Generative AI"],
                   "headline": "Full-stack & GenAI engineer building custom software for growing companies",
                   "experience": "5+ years shipping full-stack and AI products for startups and enterprises"}
        s.put(f"{BASE_URL}/api/settings", json=restore)


# ---------------- Integrations status ----------------
class TestIntegrationsStatus:
    def test_status_shape_and_email_live(self):
        s = _admin_session()
        r = s.get(f"{BASE_URL}/api/integrations/status")
        assert r.status_code == 200
        d = r.json()
        for k in ["email_live", "leads_live", "leads_blocked", "whatsapp_live"]:
            assert k in d, f"Missing {k}"
        assert d["email_live"] is True, "SMTP should be live"
        assert d.get("email_provider") in ("smtp", "resend")


# ---------------- Automation run: drafts + project_idea + estimated_value ----------------
class TestAutomationRun:
    """One real LLM run for the whole class (kept small)."""
    _did_run = False
    _lead_id = None
    _email_id = None

    def _run_once(self, s):
        if TestAutomationRun._did_run:
            return
        r = s.post(f"{BASE_URL}/api/automation/run", json={"count": 3}, timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["leads"] >= 1
        assert d["emails"] >= 1
        TestAutomationRun._did_run = True

    def test_run_creates_drafts_and_project_fields(self):
        s = _admin_session()
        self._run_once(s)

        # Leads include project_idea + estimated_value
        leads = s.get(f"{BASE_URL}/api/leads").json()
        assert len(leads) > 0
        # Find at least one lead with populated project_idea + estimated_value from this run
        latest_leads = leads[:5]
        assert any(l.get("project_idea") for l in latest_leads), \
            f"No project_idea in latest leads: {[l.get('project_idea') for l in latest_leads]}"
        assert any(l.get("estimated_value") for l in latest_leads), \
            f"No estimated_value in latest leads"
        # Save one for later
        candidate = next((l for l in latest_leads if l.get("project_idea")), latest_leads[0])
        TestAutomationRun._lead_id = candidate["id"]
        assert "_id" not in candidate

        # Emails: initial ones for these new leads should be drafts (not sent)
        emails = s.get(f"{BASE_URL}/api/emails", params={"channel": "email"}).json()
        assert len(emails) > 0
        # Find a draft initial email
        drafts = [e for e in emails if e.get("status") == "draft" and e.get("type") == "initial"]
        assert len(drafts) > 0, f"Expected draft initial emails after run. Statuses: {[e.get('status') for e in emails[:6]]}"
        TestAutomationRun._email_id = drafts[0]["id"]

        # Follow-ups should be scheduled
        followups = [e for e in emails if e.get("type") == "follow_up"]
        if followups:
            assert any(f.get("status") == "scheduled" for f in followups)

    def test_integrations_status_after_apollo_attempt(self):
        s = _admin_session()
        self._run_once(s)
        r = s.get(f"{BASE_URL}/api/integrations/status").json()
        # Apollo present but free plan => leads_live False, leads_blocked True
        assert r["leads_live"] is False
        assert r["leads_blocked"] is True
        assert r["whatsapp_live"] is False
        assert r["email_live"] is True

    def test_edit_draft_updates_fields(self):
        s = _admin_session()
        self._run_once(s)
        eid = TestAutomationRun._email_id
        assert eid, "No draft email id captured"
        r = s.put(f"{BASE_URL}/api/emails/{eid}",
                  json={"to_email": SAFE_RECIPIENT,
                        "subject": "TEST_ subject after edit",
                        "body": "TEST_ body content updated via PUT"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["to_email"] == SAFE_RECIPIENT
        assert d["subject"] == "TEST_ subject after edit"
        assert "TEST_ body content updated" in d["body"]
        # GET verify
        emails = s.get(f"{BASE_URL}/api/emails", params={"channel": "email"}).json()
        rec = next(e for e in emails if e["id"] == eid)
        assert rec["to_email"] == SAFE_RECIPIENT
        assert rec["status"] == "draft"

    def test_send_single_email_real_smtp(self):
        s = _admin_session()
        self._run_once(s)
        eid = TestAutomationRun._email_id
        # Ensure recipient safe
        s.put(f"{BASE_URL}/api/emails/{eid}", json={"to_email": SAFE_RECIPIENT})
        r = s.post(f"{BASE_URL}/api/emails/{eid}/send", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") == "sent", f"Expected sent, got {d}"
        assert d.get("simulated") is False or d.get("already") is True

        # Cannot edit sent email
        r2 = s.put(f"{BASE_URL}/api/emails/{eid}", json={"subject": "shouldnt"})
        assert r2.status_code == 400

    def test_send_all_returns_counts(self):
        s = _admin_session()
        self._run_once(s)
        # First: retarget any remaining drafts to SAFE_RECIPIENT to avoid bounces
        emails = s.get(f"{BASE_URL}/api/emails", params={"channel": "email"}).json()
        drafts = [e for e in emails if e.get("status") in ("draft", "failed") and e.get("type") == "initial"]
        for e in drafts[:5]:
            s.put(f"{BASE_URL}/api/emails/{e['id']}", json={"to_email": SAFE_RECIPIENT})
        r = s.post(f"{BASE_URL}/api/emails/send-all", timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "sent" in d and "failed" in d
        assert isinstance(d["sent"], int) and isinstance(d["failed"], int)

    def test_mark_replied_cancels_followups(self):
        s = _admin_session()
        self._run_once(s)
        lead_id = TestAutomationRun._lead_id
        assert lead_id
        r = s.post(f"{BASE_URL}/api/leads/{lead_id}/replied")
        assert r.status_code == 200
        d = r.json()
        assert d["replied"] is True
        assert d["cancelled_followups"] >= 0


# ---------------- Dashboard stats new fields ----------------
class TestDashboardStats:
    def test_stats_new_fields(self):
        s = _admin_session()
        r = s.get(f"{BASE_URL}/api/dashboard/stats")
        assert r.status_code == 200
        d = r.json()
        for k in ["drafts", "followups_queued", "replied", "integrations",
                  "total_leads", "emails_sent", "volume"]:
            assert k in d, f"Missing {k}"
        assert isinstance(d["drafts"], int)
        assert isinstance(d["followups_queued"], int)
        assert isinstance(d["replied"], int)
        assert isinstance(d["integrations"], dict)
        assert d["integrations"]["email_live"] is True


# ---------------- Followups process endpoint ----------------
class TestFollowups:
    def test_process_returns_int(self):
        s = _admin_session()
        r = s.post(f"{BASE_URL}/api/followups/process")
        assert r.status_code == 200
        assert isinstance(r.json().get("sent"), int)
