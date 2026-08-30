"""Bật Firebase Auth email/password + tạo user demo trên project Firebase.

Dùng google.auth (ADC — application_default_credentials.json của gcloud) — không cần
`gcloud services enable` (gcloud có thể treo). Chạy:
    python scripts/enable_firebase_auth.py --project ba-assistant-portal \
        --user demo@ba-assistant.local --password 'Demo@12345'
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

import google.auth
from google.auth.transport.requests import Request


def api(project: str) -> tuple[str, str]:
    """(base_url admin config, api_key) — api_key từ Identity Toolkit admin API."""
    import google.auth.transport.requests

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    base = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{project}/config"
    # lấy API key (config.keys) để dùng accounts:signUp
    req = urllib.request.Request(base, headers={"Authorization": f"Bearer {creds.token}"})
    with urllib.request.urlopen(req) as resp:
        cfg = json.loads(resp.read())
    keys = cfg.get("keys", {})
    api_key = keys.get("androidKey", {}).get("current", {}) or keys.get("iosKey", {}) or {}
    return base, (api_key.get("current") if isinstance(api_key, dict) else None)


def enable_email_password(project: str) -> None:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    base, _ = api(project)
    body = {
        "signIn": {"email": {"enabled": True, "passwordPolicy": {"enforceStrengthEnabled": False}}},
        "signUp": {"allowDuplicateEmails": False},
    }
    req = urllib.request.Request(
        base,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            cfg = json.loads(resp.read())
        print("email/password enabled:", cfg.get("signIn", {}).get("email", {}).get("enabled"))
    except urllib.error.HTTPError as exc:
        print("PATCH failed:", exc.code, exc.read().decode()[:200])
        raise


def create_user(project: str, email: str, password: str) -> None:
    """Tạo user demo qua accounts:signUp — API key tách từ project config."""
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    base = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{project}/config"
    req = urllib.request.Request(base, headers={"Authorization": f"Bearer {creds.token}"})
    with urllib.request.urlopen(req) as resp:
        cfg = json.loads(resp.read())
    key = cfg.get("keys", {}).get("androidKey", {})
    api_key = key.get("current") if isinstance(key, dict) else None
    if not api_key:
        raise SystemExit("không lấy được API key từ config")
    body = {"email": email, "password": password, "returnSecureToken": True}
    req = urllib.request.Request(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={api_key}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            d = json.loads(resp.read())
        print("user OK:", d.get("email"), "uid:", d.get("localId"))
    except urllib.error.HTTPError as exc:
        print("signUp failed:", exc.code, exc.read().decode()[:200])
        raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="ba-assistant-portal")
    ap.add_argument("--user", default="demo@ba-assistant.local")
    ap.add_argument("--password", default="Demo@12345")
    args = ap.parse_args()
    enable_email_password(args.project)
    create_user(args.project, args.user, args.password)


if __name__ == "__main__":
    main()
