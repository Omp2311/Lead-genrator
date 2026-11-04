"""Live end-to-end smoke test. Run from backend/ with the server up:  python tests/e2e_smoke.py
Uses a throwaway user (deleted at the end). The automation step spends real Apollo/OpenAI credits."""
import os, sys, uuid, time, asyncio, json
import requests, asyncpg
from dotenv import load_dotenv
load_dotenv(".env")

B = "http://127.0.0.1:8000"
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


async def db(sql, *a, fetch=True):
    c = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        return await (c.fetch(sql, *a) if fetch else c.execute(sql, *a))
    finally:
        await c.close()


def main():
    email = f"e2e_{uuid.uuid4().hex[:8]}@example.com"
    pw = "Str0ng-Test-Pass-123"
    s = requests.Session()

    # 1 health / ready
    check("GET /health", requests.get(B + "/health").json() == {"status": "ok"})
    check("GET /ready (db reachable)", requests.get(B + "/ready").json() == {"status": "ready"})

    # 2 auth guard
    check("unauthenticated /api/auth/me -> 401", requests.get(B + "/api/auth/me").status_code == 401)
    check("unauthenticated /api/leads -> 401", requests.get(B + "/api/leads").status_code == 401)

    # 3 register / login / me
    r = s.post(B + "/api/auth/register", json={"name": "E2E", "email": email, "password": pw})
    check("register", r.status_code in (200, 201), r.status_code)
    r = s.get(B + "/api/auth/me")
    check("session cookie works (/auth/me)", r.status_code == 200 and r.json().get("email") == email, r.status_code)
    bad = requests.post(B + "/api/auth/login", json={"email": email, "password": "wrong-password-1"})
    check("wrong password rejected", bad.status_code in (400, 401), bad.status_code)

    # 4 CSRF: foreign origin blocked, tunnel origin allowed
    r = s.put(B + "/api/settings", json={"regions": ["India"]}, headers={"Origin": "https://evil.example"})
    check("CSRF: foreign Origin blocked (403)", r.status_code == 403, r.status_code)

    # 5 settings -> pharma targeting
    payload = {"daily_target": 10, "regions": ["India", "Middle East", "Philippines"], "industries": ["Pharmacy", "Pharmacy Chain"]}
    r = s.put(B + "/api/settings", json=payload, headers={"Origin": "http://localhost:3000"})
    check("PUT /api/settings", r.status_code == 200, r.status_code)
    g = s.get(B + "/api/settings").json()
    check("settings persisted", g.get("industries") == payload["industries"] and g.get("regions") == payload["regions"])
    asyncio.run(db("delete from users where email like 'e2e\_%@example.com' and email<>$1", email, fetch=False))

    # 6 inbox credential encryption at rest (resend provider => no SMTP login needed)
    secret = "re_PLAINTEXT_SENTINEL_12345"
    r = s.post(B + "/api/inboxes", json={"label": "e2e", "provider": "resend", "resend_api_key": secret,
                                          "from_email": "sender@example.com"}, headers={"Origin": "http://localhost:3000"})
    check("create inbox", r.status_code in (200, 201), f"{r.status_code} {r.text[:120]}")
    row = asyncio.run(db("select resend_api_key from inboxes i join users u on u.id=i.user_id where u.email=$1", email))
    stored = row[0]["resend_api_key"] if row else None
    check("DB stores credential ENCRYPTED (enc:v1:, no plaintext)",
          bool(stored) and stored.startswith("enc:v1:") and secret not in stored, (stored or "")[:20])
    api_view = json.dumps(s.get(B + "/api/inboxes").json())
    check("API never returns the plaintext secret", secret not in api_view and "enc:v1" not in api_view)
    import importlib.util
    sys.path.insert(0, ".")
    os.environ.setdefault("JWT_SECRET", os.environ["JWT_SECRET"])
    import server
    check("stored value decrypts back to original", server.dec_secret(stored) == secret)

    # 7 real automation run (pharma): relevance filter + sourcing
    r = s.post(B + "/api/automation/run", json={"count": 10}, headers={"Origin": "http://localhost:3000"}, timeout=240)
    check("automation run", r.status_code == 200, f"{r.status_code} {r.text[:150]}")
    if r.status_code == 200:
        print("     run result:", {k: r.json()[k] for k in list(r.json())[:5]})
    leads = s.get(B + "/api/leads").json()
    leads = leads if isinstance(leads, list) else leads.get("leads", [])
    print(f"     leads created: {len(leads)}")
    for l in leads[:8]:
        print("      -", l.get("company"), "|", l.get("industry"), "|", l.get("lead_source"), "|", l.get("email"))
    off = [l for l in leads if not any(k in (l.get("company", "") + l.get("website", "")).lower()
                                        for k in ("pharm", "medic", "chemist", "drug", "apothec", "medplus", "wellness", "healthmart"))]
    check("run produced at least 1 lead", len(leads) > 0, len(leads))
    check("no off-target (hotel/restaurant/etc.) leads", len(off) == 0, f"off-target={[o.get('company') for o in off]}")

    # 8 follow-up claim: schedule a due, NON-deliverable follow-up and process it
    uid = asyncio.run(db("select id from users where email=$1", email))[0]["id"]
    lead_id = uuid.uuid4()
    asyncio.run(db("insert into leads (id,user_id,company) values ($1,$2,'FollowupCo')", lead_id, uid, fetch=False))
    fid = uuid.uuid4()
    asyncio.run(db("""insert into emails (id,user_id,lead_id,company,to_email,subject,body,step,type,status,deliverable,scheduled_for)
                      values ($1,$2,$3,'FollowupCo','nobody@example.invalid','s','b',2,'follow_up','scheduled',false, now()-interval '1 hour')""",
                   fid, uid, lead_id, fetch=False))
    r = s.post(B + "/api/followups/process", headers={"Origin": "http://localhost:3000"})
    check("POST /followups/process works (no processed_at error)", r.status_code == 200, f"{r.status_code} {r.text[:100]}")
    st = asyncio.run(db("select status, processed_at from emails where id=$1", fid))[0]
    check("follow-up claimed (processed_at set) and status moved off 'scheduled'",
          st["processed_at"] is not None and st["status"] != "scheduled", dict(st))
    sim = asyncio.run(db("select simulated, error from emails where id=$1", fid))[0]
    check("non-deliverable follow-up was SIMULATED, not really emailed", sim["simulated"] is True, dict(sim))
    r2 = s.post(B + "/api/followups/process", headers={"Origin": "http://localhost:3000"})
    check("second process run does NOT re-send (idempotent)", r2.status_code == 200 and r2.json().get("sent") == 0, r2.text[:60])

    # 9 frontend dev-proxy path
    try:
        pr = requests.get("http://localhost:3000/api/auth/me", timeout=10)
        check("frontend proxy forwards /api (401 from backend)", pr.status_code == 401, pr.status_code)
    except Exception as e:
        check("frontend proxy reachable", False, e)

    # cleanup
    asyncio.run(db("delete from users where email=$1", email, fetch=False))
    left = asyncio.run(db("select count(*) c from users where email=$1", email))[0]["c"]
    check("cleanup: throwaway user removed", left == 0)

    bad = [n for n, ok in results if not ok]
    print(f"\n{len(results)-len(bad)}/{len(results)} passed")
    sys.exit(1 if bad else 0)


main()
