"""Unit tests for production-hardening helpers (no running server or DB required)."""
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost:5432/x")
os.environ.setdefault("JWT_SECRET", "unit-test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402


def test_secret_roundtrip_and_prefix():
    token = server.enc_secret("s3cret-app-password")
    assert token.startswith("enc:v1:") and "s3cret" not in token
    assert server.dec_secret(token) == "s3cret-app-password"


def test_enc_secret_is_idempotent_and_handles_empty():
    token = server.enc_secret("abc")
    assert server.enc_secret(token) == token
    assert server.enc_secret("") == "" and server.dec_secret("") == ""


def test_legacy_plaintext_still_readable():
    assert server.dec_secret("plain-old-password") == "plain-old-password"


def test_tampered_ciphertext_does_not_crash():
    assert server.dec_secret("enc:v1:not-a-valid-token") == ""


def test_log_filter_redacts_api_keys():
    f = server._RedactSecrets()
    rec = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1,
        'HTTP Request: GET https://api.hunter.io/v2/domain-search?domain=a.com&api_key=SUPERSECRET&limit=5',
        None, None)
    f.filter(rec)
    out = rec.getMessage()
    assert "SUPERSECRET" not in out and "api_key=***" in out and "domain=a.com" in out


def test_relevance_filter_keeps_pharmacy_drops_others():
    leads = [
        {"company": "Care Pharmacy", "industry": "Pharmacy"},
        {"company": "Grand Hotel", "industry": "Hotel"},
        {"company": "Taco House", "industry": "Mexican Restaurant"},
        {"company": "MedPlus", "industry": "", "website": "https://medplus-pharma.in"},
        # sources stamp the campaign industry onto unrelated results - must be ignored
        {"company": "The Algorithms", "industry": "Pharmacy", "website": "https://the-algorithms.com"},
        {"company": "Rohtak Chain Company", "industry": "Pharmacy Chain"},
    ]
    kept = server.filter_relevant_leads(leads, ["Pharmacy", "Pharmacy Chain"])
    assert [l["company"] for l in kept] == ["Care Pharmacy", "MedPlus"]


def test_relevance_filter_noop_without_targets():
    leads = [{"company": "X", "industry": "Y"}]
    assert server.filter_relevant_leads(leads, []) == leads


def test_source_flags_reset():
    server._apollo_ok = False
    server._github_ok = True
    server._reset_source_flags()
    assert server._apollo_ok is None and server._github_ok is True
