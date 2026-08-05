"""OutreachPilot backend API tests.

Covers, across the original build and Tiers 1-5:
- Auth, multi-tenant isolation, and team seats (owner vs. invited member)
- Profile/Automation settings, sequence builder, suppression list, inboxes
- Automation run, emails (edit/send/send-all), CSV import, CRM pipeline
- Dashboard/analytics stats, A/B variants, deliverability scoring
- Billing plan limits, API keys + public API, referrals, LinkedIn drafting
- Public endpoints: unsubscribe, tracking pixel, voice-note serving

NOTE: tests requiring a login session use Secure, SameSite=None cookies (see
set_auth_cookies in server.py) — Python's `requests` will not send a Secure
cookie back over plain HTTP, so most authenticated tests here 401 when run
against a local http://127.0.0.1 backend. They pass against a real HTTPS
deployment. This is a known test-environment limitation, not a product bug —
verify locally with direct curl/script calls instead (see conversation history
for the smoke-test commands used to validate each tier).
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


def _register_session(name, email, password, ref=None):
    s = requests.Session()
    payload = {"name": name, "email": email, "password": password}
    if ref:
        payload["ref"] = ref
    r = s.post(f"{BASE_URL}/api/auth/register", json=payload)
    assert r.status_code == 200, r.text
    return s


def _login_session(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return s


def _import_one_lead(session, email):
    csv_body = (
        "company,contact_name,title,email,phone,location,industry,website,pain_point,project_idea,estimated_value\n"
        f"Iso Co,Person,CTO,{email},,USA,SaaS,https://example.com,x,y,$1k\n"
    )
    r = session.post(f"{BASE_URL}/api/leads/import", files={"file": ("l.csv", csv_body, "text/csv")})
    assert r.status_code == 200, r.text


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


# ---------------- Suppression list (unsubscribes / opt-outs) ----------------
class TestSuppressions:
    def test_add_list_delete(self):
        s = _admin_session()
        email = "test_suppress_iter3@example.com"
        r = s.post(f"{BASE_URL}/api/suppressions", json={"email": email, "reason": "manual"})
        assert r.status_code == 200, r.text
        assert r.json()["added"] is True

        # Duplicate add should not error (ON CONFLICT DO NOTHING)
        r2 = s.post(f"{BASE_URL}/api/suppressions", json={"email": email, "reason": "manual"})
        assert r2.status_code == 200

        rows = s.get(f"{BASE_URL}/api/suppressions").json()
        match = next((x for x in rows if x["email"] == email), None)
        assert match is not None

        r3 = s.delete(f"{BASE_URL}/api/suppressions/{match['id']}")
        assert r3.status_code == 200
        assert r3.json()["deleted"] is True

        rows_after = s.get(f"{BASE_URL}/api/suppressions").json()
        assert not any(x["email"] == email for x in rows_after)

    def test_delete_unknown_returns_404(self):
        s = _admin_session()
        r = s.delete(f"{BASE_URL}/api/suppressions/{uuid.uuid4()}")
        assert r.status_code == 404


# ---------------- Sending inboxes (multi-inbox rotation) ----------------
class TestInboxes:
    def test_create_list_update_delete(self):
        s = _admin_session()
        payload = {
            "label": "TEST_Inbox", "provider": "smtp", "smtp_host": "smtp.test.invalid",
            "smtp_port": 587, "smtp_user": "test@test.invalid", "smtp_password": "secret123",
            "resend_api_key": "", "from_email": "test@test.invalid", "daily_cap": 25,
            "warmup_enabled": True, "is_active": True,
        }
        r = s.post(f"{BASE_URL}/api/inboxes", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        inbox_id = d["id"]
        # Secret must never be echoed back in plaintext
        assert d["smtp_password"] == "•" * 8

        rows = s.get(f"{BASE_URL}/api/inboxes").json()
        assert any(i["id"] == inbox_id for i in rows)

        # Update with the masked placeholder unchanged should keep the real secret working
        upd_payload = {**payload, "label": "TEST_Inbox_Renamed", "smtp_password": d["smtp_password"]}
        r2 = s.put(f"{BASE_URL}/api/inboxes/{inbox_id}", json=upd_payload)
        assert r2.status_code == 200, r2.text
        assert r2.json()["label"] == "TEST_Inbox_Renamed"

        r3 = s.delete(f"{BASE_URL}/api/inboxes/{inbox_id}")
        assert r3.status_code == 200
        assert r3.json()["deleted"] is True

    def test_delete_unknown_returns_404(self):
        s = _admin_session()
        r = s.delete(f"{BASE_URL}/api/inboxes/{uuid.uuid4()}")
        assert r.status_code == 404


# ---------------- CSV lead import ----------------
class TestCsvImport:
    def test_import_creates_leads_and_skips_duplicates(self):
        s = _admin_session()
        unique = uuid.uuid4().hex[:8]
        csv_body = (
            "company,contact_name,title,email,phone,location,industry,website,pain_point,project_idea,estimated_value\n"
            f"TEST Co,Jane Doe,CTO,test_csv_{unique}@example.com,,Dubai,SaaS,https://example.com,slow builds,CI speedup,$5k\n"
            "No Email Row,No Email,CEO,,,,,,,,\n"
        )
        files = {"file": ("leads.csv", csv_body, "text/csv")}
        r = s.post(f"{BASE_URL}/api/leads/import", files=files)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["imported"] == 1
        assert d["skipped"] == 1

        leads = s.get(f"{BASE_URL}/api/leads").json()
        assert any(l["email"] == f"test_csv_{unique}@example.com" and l["lead_source"] == "csv" for l in leads)

        # Re-importing the same row should be skipped as a duplicate
        r2 = s.post(f"{BASE_URL}/api/leads/import", files={"file": ("leads.csv", csv_body, "text/csv")})
        assert r2.json()["imported"] == 0


# ---------------- Follow-up sequence builder ----------------
class TestSequence:
    def test_get_seeds_default_two_steps(self):
        s = _admin_session()
        r = s.get(f"{BASE_URL}/api/sequence")
        assert r.status_code == 200, r.text
        steps = r.json()
        assert len(steps) >= 1
        assert all("delay_days" in st and "angle" in st for st in steps)

    def test_put_replaces_steps_in_order(self):
        s = _admin_session()
        original = s.get(f"{BASE_URL}/api/sequence").json()
        payload = [{"delay_days": 2, "angle": "TEST_quick nudge"},
                   {"delay_days": 5, "angle": "TEST_case study"},
                   {"delay_days": 9, "angle": "TEST_breakup"}]
        r = s.put(f"{BASE_URL}/api/sequence", json=payload)
        assert r.status_code == 200, r.text
        steps = r.json()
        assert [st["delay_days"] for st in steps] == [2, 5, 9]
        assert [st["angle"] for st in steps] == ["TEST_quick nudge", "TEST_case study", "TEST_breakup"]

        # GET-verify persistence
        r2 = s.get(f"{BASE_URL}/api/sequence").json()
        assert [st["delay_days"] for st in r2] == [2, 5, 9]

        # Restore
        s.put(f"{BASE_URL}/api/sequence", json=[
            {"delay_days": st["delay_days"], "angle": st["angle"]} for st in original
        ])

    def test_put_rejects_more_than_ten_steps(self):
        s = _admin_session()
        payload = [{"delay_days": 1, "angle": "x"} for _ in range(11)]
        r = s.put(f"{BASE_URL}/api/sequence", json=payload)
        assert r.status_code == 400


# ---------------- CRM pipeline: lead stage/notes ----------------
class TestLeadPipeline:
    def _import_one(self, s):
        unique = uuid.uuid4().hex[:8]
        email = f"test_pipeline_{unique}@example.com"
        csv_body = (
            "company,contact_name,title,email,phone,location,industry,website,pain_point,project_idea,estimated_value\n"
            f"TEST Pipeline Co,Sam Lee,COO,{email},,USA,SaaS,https://example.com,x,y,$1k\n"
        )
        s.post(f"{BASE_URL}/api/leads/import", files={"file": ("l.csv", csv_body, "text/csv")})
        leads = s.get(f"{BASE_URL}/api/leads").json()
        return next(l for l in leads if l["email"] == email)

    def test_new_lead_defaults_to_new_stage(self):
        s = _admin_session()
        lead = self._import_one(s)
        assert lead["stage"] == "new"
        assert lead["notes"] == ""
        assert lead["reply_intent"] is None

    def test_update_stage_and_notes(self):
        s = _admin_session()
        lead = self._import_one(s)
        r = s.put(f"{BASE_URL}/api/leads/{lead['id']}", json={"stage": "meeting", "notes": "TEST_ booked call"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stage"] == "meeting"
        assert d["notes"] == "TEST_ booked call"

    def test_invalid_stage_rejected(self):
        s = _admin_session()
        lead = self._import_one(s)
        r = s.put(f"{BASE_URL}/api/leads/{lead['id']}", json={"stage": "not_a_real_stage"})
        assert r.status_code == 400

    def test_unknown_lead_returns_404(self):
        s = _admin_session()
        r = s.put(f"{BASE_URL}/api/leads/{uuid.uuid4()}", json={"stage": "won"})
        assert r.status_code == 404


# ---------------- Funnel + A/B analytics ----------------
class TestAnalytics:
    def test_funnel_shape(self):
        s = _admin_session()
        r = s.get(f"{BASE_URL}/api/analytics/funnel")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["sent", "opened", "clicked", "stages", "ab_variants"]:
            assert k in d, f"Missing {k}"
        for stage in ["new", "contacted", "replied", "meeting", "won", "lost"]:
            assert stage in d["stages"]
        assert isinstance(d["ab_variants"], list)


# ---------------- Public endpoints (no auth): unsubscribe + tracking pixel ----------------
class TestPublicEndpoints:
    def test_unsubscribe_invalid_token_returns_400(self):
        r = requests.get(f"{BASE_URL}/api/unsubscribe/not-a-real-token")
        assert r.status_code == 400

    def test_tracking_pixel_returns_gif(self):
        r = requests.get(f"{BASE_URL}/api/t/{uuid.uuid4()}.gif")
        assert r.status_code == 200
        assert r.headers.get("content-type") == "image/gif"


# ---------------- Multi-tenant isolation (two independent, unrelated tenants) ----------------
class TestTenantIsolation:
    def test_two_owners_cannot_see_each_others_leads(self):
        unique = uuid.uuid4().hex[:8]
        email_a = f"test_owner_a_{unique}@example.com"
        email_b = f"test_owner_b_{unique}@example.com"
        sa = _register_session("Owner A", email_a, "pw_test_12345")
        sb = _register_session("Owner B", email_b, "pw_test_12345")

        lead_email_a = f"test_lead_a_{unique}@example.com"
        lead_email_b = f"test_lead_b_{unique}@example.com"
        _import_one_lead(sa, lead_email_a)
        _import_one_lead(sb, lead_email_b)

        leads_a = {l["email"] for l in sa.get(f"{BASE_URL}/api/leads").json()}
        leads_b = {l["email"] for l in sb.get(f"{BASE_URL}/api/leads").json()}
        assert lead_email_a in leads_a
        assert lead_email_a not in leads_b
        assert lead_email_b in leads_b
        assert lead_email_b not in leads_a


# ---------------- Team seats ----------------
class TestTeam:
    def _owner_session(self):
        unique = uuid.uuid4().hex[:8]
        email = f"test_team_owner_{unique}@example.com"
        s = _register_session("Team Owner", email, "pw_test_12345")
        return s, unique

    def test_owner_sees_self_as_sole_member(self):
        s, _ = self._owner_session()
        members = s.get(f"{BASE_URL}/api/team/members").json()
        assert len(members) == 1
        assert members[0]["is_owner"] is True

    def test_starter_plan_blocks_second_seat(self):
        s, unique = self._owner_session()
        r = s.post(f"{BASE_URL}/api/team/members",
                   json={"name": "Teammate", "email": f"test_mate_{unique}@example.com", "password": "pw_test_12345"})
        assert r.status_code == 402

    def test_remove_unknown_member_404(self):
        s, _ = self._owner_session()
        r = s.delete(f"{BASE_URL}/api/team/members/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_remove_self_rejected(self):
        s, _ = self._owner_session()
        me = s.get(f"{BASE_URL}/api/auth/me").json()
        r = s.delete(f"{BASE_URL}/api/team/members/{me['id']}")
        assert r.status_code == 400


# ---------------- Billing ----------------
class TestBilling:
    def test_status_shape_for_fresh_owner(self):
        unique = uuid.uuid4().hex[:8]
        s = _register_session("Billing Owner", f"test_billing_{unique}@example.com", "pw_test_12345")
        r = s.get(f"{BASE_URL}/api/billing/status")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["plan"] == "starter"
        assert d["is_owner"] is True
        assert d["limits"]["max_inboxes"] == 2

    def test_checkout_without_stripe_configured_or_unknown_plan(self):
        unique = uuid.uuid4().hex[:8]
        s = _register_session("Billing Owner 2", f"test_billing2_{unique}@example.com", "pw_test_12345")
        r = s.post(f"{BASE_URL}/api/billing/checkout", json={"plan": "not_a_real_plan"})
        assert r.status_code == 400


# ---------------- Deliverability / spam-score checker ----------------
class TestSpamCheck:
    def test_clean_copy_scores_high(self):
        s = _admin_session()
        r = s.post(f"{BASE_URL}/api/emails/spam-check",
                   json={"subject": "Quick question about your CI pipeline",
                         "body": "Hi Jane, noticed your team ships fast. Worth a quick chat?\n\nAlex"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["score"] == 100
        assert d["flags"] == []

    def test_spammy_copy_scores_low_with_flags(self):
        s = _admin_session()
        r = s.post(f"{BASE_URL}/api/emails/spam-check",
                   json={"subject": "ACT NOW!!! 100% FREE CASH BONUS!!!",
                         "body": "Click here now! Guarantee! http://a.com http://b.com http://c.com http://d.com"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["score"] < 50
        assert len(d["flags"]) > 0


# ---------------- Voice-note personalization ----------------
class TestVoiceNote:
    def test_unknown_email_404(self):
        s = _admin_session()
        r = s.post(f"{BASE_URL}/api/emails/{uuid.uuid4()}/voice-note")
        assert r.status_code == 404

    def test_serving_route_404_for_missing_file(self):
        r = requests.get(f"{BASE_URL}/api/voice/{uuid.uuid4()}.mp3")
        assert r.status_code == 404


# ---------------- White-label branding ----------------
class TestBranding:
    def test_brand_fields_persist(self):
        s = _admin_session()
        cur = s.get(f"{BASE_URL}/api/settings").json()
        payload = {**{k: cur[k] for k in [
            "daily_target", "auto_enabled", "regions", "industries", "offer", "sender_name",
            "tone", "skills", "headline", "experience", "meeting_link"]},
            "brand_name": "TEST_Acme Growth", "brand_logo_url": "https://example.com/logo.png"}
        r = s.put(f"{BASE_URL}/api/settings", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["brand_name"] == "TEST_Acme Growth"
        # Restore
        payload["brand_name"] = ""
        payload["brand_logo_url"] = ""
        s.put(f"{BASE_URL}/api/settings", json=payload)


# ---------------- Referrals ----------------
class TestReferrals:
    def test_status_generates_code_and_tracks_signups(self):
        unique = uuid.uuid4().hex[:8]
        referrer = _register_session("Referrer", f"test_referrer_{unique}@example.com", "pw_test_12345")
        status = referrer.get(f"{BASE_URL}/api/referrals/status").json()
        code = status["referral_code"]
        assert code
        assert status["referred_count"] == 0

        _register_session("Referred", f"test_referred_{unique}@example.com", "pw_test_12345", ref=code)

        status2 = referrer.get(f"{BASE_URL}/api/referrals/status").json()
        assert status2["referred_count"] == 1

    def test_unknown_ref_code_is_ignored_not_rejected(self):
        unique = uuid.uuid4().hex[:8]
        s = _register_session("No Referrer", f"test_noref_{unique}@example.com", "pw_test_12345",
                              ref="NOTAREALCODE")
        me = s.get(f"{BASE_URL}/api/auth/me").json()
        assert me["email"] == f"test_noref_{unique}@example.com"


# ---------------- API keys + public API (Zapier/Make) ----------------
class TestPublicApi:
    def test_key_lifecycle_and_public_endpoints(self):
        s = _admin_session()
        r = s.post(f"{BASE_URL}/api/api-keys", json={"label": "TEST_key"})
        assert r.status_code == 200, r.text
        d = r.json()
        key = d["key"]
        assert key.startswith("op_")

        rows = s.get(f"{BASE_URL}/api/api-keys").json()
        assert any(k["id"] == d["id"] for k in rows)
        # The full key must never be listed again, only a preview
        assert all("key" not in k or k.get("key_preview") for k in rows)

        headers = {"Authorization": f"Bearer {key}"}
        unique = uuid.uuid4().hex[:8]
        lead_email = f"test_public_api_{unique}@example.com"
        r2 = requests.post(f"{BASE_URL}/api/public/v1/leads", headers=headers,
                           json={"email": lead_email, "company": "TEST_Public Co"})
        assert r2.status_code == 200, r2.text

        r3 = requests.get(f"{BASE_URL}/api/public/v1/leads", headers=headers)
        assert r3.status_code == 200
        assert any(l["email"] == lead_email for l in r3.json())

        # Duplicate create is rejected
        r4 = requests.post(f"{BASE_URL}/api/public/v1/leads", headers=headers, json={"email": lead_email})
        assert r4.status_code == 409

        s.delete(f"{BASE_URL}/api/api-keys/{d['id']}")
        r5 = requests.get(f"{BASE_URL}/api/public/v1/leads", headers=headers)
        assert r5.status_code == 401

    def test_missing_key_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/public/v1/leads")
        assert r.status_code == 401


# ---------------- LinkedIn drafting (manual copy-paste, never automated) ----------------
class TestLinkedInDraft:
    def test_unknown_lead_404(self):
        s = _admin_session()
        r = s.post(f"{BASE_URL}/api/leads/{uuid.uuid4()}/linkedin-draft")
        assert r.status_code == 404
