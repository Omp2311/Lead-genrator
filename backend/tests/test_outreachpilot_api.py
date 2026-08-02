"""OutreachPilot backend API tests.

Covers:
- Auth: /api/auth/login, /register, /me, /logout
- Automation: /api/automation/run (LLM-driven)
- Data endpoints: /api/leads, /api/emails, /api/activity
- Dashboard stats
- Settings CRUD

The automation run calls the LLM twice (leads + emails) and can take 20-40s.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://auto-outreach-pro-1.preview.emergentagent.com').rstrip('/')
ADMIN_EMAIL = "admin@outreachpilot.com"
ADMIN_PASSWORD = "admin123"


# ---------------- Health & Auth ----------------
class TestHealth:
    def test_api_root(self):
        r = requests.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        assert "OutreachPilot" in r.json().get("message", "")


class TestAuth:
    def test_login_invalid(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "nobody@example.com", "password": "wrong"})
        assert r.status_code == 401

    def test_login_admin_and_cookies(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == ADMIN_EMAIL
        assert "id" in data
        # Check httpOnly cookie is set
        cookies = {c.name: c for c in s.cookies}
        assert "access_token" in cookies, f"access_token cookie missing. Got: {list(cookies)}"
        assert "refresh_token" in cookies

        # /auth/me works with cookies
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == ADMIN_EMAIL

    def test_me_unauth(self):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_register_and_login(self):
        s = requests.Session()
        email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{BASE_URL}/api/auth/register",
                   json={"name": "TEST User", "email": email, "password": "TESTpass123!"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == email
        assert data["role"] == "user"

        # Verify cookies auto-login
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == email

        # Duplicate registration returns 400
        r2 = requests.post(f"{BASE_URL}/api/auth/register",
                           json={"name": "TEST 2", "email": email, "password": "another"})
        assert r2.status_code == 400

    def test_logout_clears_session(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        r = s.post(f"{BASE_URL}/api/auth/logout")
        assert r.status_code == 200
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 401


# ---------------- Settings ----------------
class TestSettings:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.s = requests.Session()
        r = self.s.post(f"{BASE_URL}/api/auth/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200

    def test_get_settings_defaults(self):
        r = self.s.get(f"{BASE_URL}/api/settings")
        assert r.status_code == 200
        d = r.json()
        assert "daily_target" in d
        assert "auto_enabled" in d
        assert isinstance(d.get("regions"), list)
        assert isinstance(d.get("industries"), list)

    def test_update_settings_persists(self):
        payload = {
            "daily_target": 77,
            "auto_enabled": False,
            "regions": ["Dubai, UAE", "New York"],
            "industries": ["SaaS"],
            "offer": "Test offer TEST_",
            "sender_name": "TestOp",
            "tone": "friendly",
        }
        r = self.s.put(f"{BASE_URL}/api/settings", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["daily_target"] == 77
        assert d["auto_enabled"] is False
        assert d["offer"] == "Test offer TEST_"

        # GET-verify persistence
        r2 = self.s.get(f"{BASE_URL}/api/settings")
        assert r2.json()["daily_target"] == 77
        assert r2.json()["sender_name"] == "TestOp"

        # Restore
        payload["daily_target"] = 100
        payload["auto_enabled"] = True
        payload["sender_name"] = "Alex"
        payload["offer"] = "Custom AI-powered software & full-stack development services"
        payload["tone"] = "confident and concise"
        self.s.put(f"{BASE_URL}/api/settings", json=payload)


# ---------------- Automation (LLM) ----------------
class TestAutomationRun:
    """This class hits the real LLM. Uses small count to stay under 60s."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.s = requests.Session()
        r = self.s.post(f"{BASE_URL}/api/auth/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200

    def test_automation_run_generates_leads_and_emails(self):
        r = self.s.post(f"{BASE_URL}/api/automation/run",
                        json={"count": 4}, timeout=120)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        assert d["leads"] >= 1, f"No leads generated: {d}"
        assert d["emails"] >= 1, f"No emails generated: {d}"
        assert "run_at" in d

    def test_leads_endpoint_returns_generated(self):
        r = self.s.get(f"{BASE_URL}/api/leads")
        assert r.status_code == 200
        leads = r.json()
        assert isinstance(leads, list)
        assert len(leads) > 0, "No leads found after automation run"
        # Validate schema
        lead = leads[0]
        for k in ["id", "company", "contact_name", "email", "location", "pain_point"]:
            assert k in lead, f"Missing key {k}: {lead}"
        # _id must not be exposed
        assert "_id" not in lead
        # whatsapp_link should be present for leads with phone
        phoned = [l for l in leads if l.get("phone")]
        for l in phoned:
            assert l.get("whatsapp_link") and l["whatsapp_link"].startswith("https://wa.me/"), \
                f"Missing/invalid wa link for {l}"

    def test_emails_endpoint_email_channel(self):
        r = self.s.get(f"{BASE_URL}/api/emails", params={"channel": "email"})
        assert r.status_code == 200
        emails = r.json()
        assert isinstance(emails, list)
        assert len(emails) > 0, "No cold emails generated"
        e = emails[0]
        for k in ["id", "subject", "body", "to_email", "channel", "status"]:
            assert k in e
        assert e["channel"] == "email"
        assert e["status"] == "sent"
        # AI real output: subject and body should be non-trivial
        assert isinstance(e["subject"], str) and len(e["subject"]) >= 3, f"Subject too short: {e['subject']!r}"
        assert isinstance(e["body"], str) and len(e["body"]) >= 30, f"Body too short: {e['body']!r}"
        assert "_id" not in e

    def test_emails_endpoint_whatsapp_channel(self):
        r = self.s.get(f"{BASE_URL}/api/emails", params={"channel": "whatsapp"})
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # Only leads with phones create whatsapp items; if none, that's still OK
        for it in items:
            assert it["channel"] == "whatsapp"
            assert it.get("whatsapp_link", "").startswith("https://wa.me/")


# ---------------- Dashboard & Activity ----------------
class TestDashboard:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.s = requests.Session()
        r = self.s.post(f"{BASE_URL}/api/auth/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200

    def test_dashboard_stats_shape(self):
        r = self.s.get(f"{BASE_URL}/api/dashboard/stats")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["total_leads", "emails_sent", "whatsapp_ready",
                  "leads_with_phone", "daily_target", "auto_enabled", "volume"]:
            assert k in d, f"Missing key {k}"
        assert isinstance(d["volume"], list)
        assert len(d["volume"]) == 7
        for v in d["volume"]:
            assert "day" in v and "emails" in v
            assert isinstance(v["emails"], int)

    def test_activity_list(self):
        r = self.s.get(f"{BASE_URL}/api/activity")
        assert r.status_code == 200
        acts = r.json()
        assert isinstance(acts, list)
        if acts:
            a = acts[0]
            for k in ["id", "type", "message", "created_at"]:
                assert k in a
            assert "_id" not in a
