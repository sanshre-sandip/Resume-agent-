from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import shutil
import smtplib
import ssl
import time
import uuid
from pathlib import Path
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

from ..config import settings
from ..database.file_store import create_record, delete_records, get_record, list_records, now_iso, save_record
from ..security.auth import (
    CSRF_COOKIE, OAUTH_STATE_COOKIE, clear_session, get_current_user, require_csrf,
    session_claims,
    secure_cookie_options, session_user_id, set_csrf, set_session,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["authentication"])
_attempts: dict[str, list[float]] = {}


def _smtp_ready() -> bool:
    return all((settings.smtp_host, settings.smtp_username, settings.smtp_password, settings.smtp_from_email))


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class EmailRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class PasswordReset(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=12, max_length=128)


@router.get("/options")
def auth_options():
    return {
        "google_enabled": bool(settings.google_client_id and settings.google_client_secret),
        "password_recovery_enabled": _smtp_ready(),
        "email_verification_enabled": settings.require_email_verification,
    }


def _limit(request: Request, key: str) -> None:
    now = time.monotonic()
    identity = f"{request.client.host if request.client else 'unknown'}:{key[:120]}"
    attempts = [stamp for stamp in _attempts.get(identity, []) if now - stamp < 600]
    if len(attempts) >= 8:
        raise HTTPException(status_code=429, detail="Too many attempts. Wait a few minutes and try again.")
    attempts.append(now)
    _attempts[identity] = attempts


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def _password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _send_email(to_email: str, subject: str, body: str) -> bool:
    if not _smtp_ready():
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
            client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
        return True
    except Exception:
        logger.warning("Brevo SMTP delivery failed")
        return False


def _new_user(email: str, name: str, password_hash: str | None, google_sub: str | None = None) -> dict:
    existing = get_record("users", "email", email)
    if existing:
        return existing
    user = {
        "id": str(uuid.uuid4()), "email": email, "name": name[:120],
        "password_hash": password_hash, "google_sub": google_sub,
        "session_version": 0,
        "email_verified": bool(google_sub) or not settings.require_email_verification,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    if settings.require_email_verification and not google_sub:
        token = secrets.token_urlsafe(32)
        user["verification_token_hash"] = _token_digest(token)
        user["verification_expires_at"] = int(time.time()) + 86400
        _send_email(email, "Verify your Nhyapu Craft account", f"Verify your account: {settings.public_base_url}/api/auth/verify?token={token}")
    if not create_record("users", user, ("email",)):
        return get_record("users", "email", email) or user
    return user


@router.get("/csrf")
def csrf_token(response: Response):
    return {"csrf_token": set_csrf(response)}


@router.get("/me")
def me(request: Request):
    user_id = session_user_id(request)
    user = get_record("users", "id", user_id) if user_id else None
    if not user:
        return {"authenticated": False}
    claims = session_claims(request) or {}
    if claims.get("ver", 0) != user.get("session_version", 0):
        return {"authenticated": False}
    return {"authenticated": True, "user": {"id": user["id"], "email": user["email"], "name": user.get("name", "")}}


@router.post("/register", status_code=201)
def register(payload: Credentials, request: Request, response: Response):
    require_csrf(request)
    if settings.require_email_verification and not _smtp_ready():
        raise HTTPException(status_code=503, detail="Email verification is required but email delivery is not configured.")
    email = str(payload.email).lower()
    _limit(request, email)
    if get_record("users", "email", email):
        raise HTTPException(status_code=409, detail="An account already exists for that email address.")
    user = {
        "id": str(uuid.uuid4()), "email": email, "name": (payload.display_name or email.split("@", 1)[0]).strip()[:120],
        "password_hash": _password_hash(payload.password), "google_sub": None,
        "session_version": 0,
        "email_verified": not settings.require_email_verification,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    verification_token = None
    if settings.require_email_verification:
        verification_token = secrets.token_urlsafe(32)
        user["verification_token_hash"] = _token_digest(verification_token)
        user["verification_expires_at"] = int(time.time()) + 86400
    if not create_record("users", user, ("email",)):
        raise HTTPException(status_code=409, detail="An account already exists for that email address.")
    if settings.require_email_verification:
        verification_url = f"{settings.public_base_url.rstrip('/')}/api/auth/verify?token={verification_token}"
        if not _send_email(email, "Verify your Nhyapu Craft account", f"Verify your account: {verification_url}"):
            delete_records("users", lambda row: row.get("id") == user["id"])
            raise HTTPException(status_code=502, detail="We could not send the verification email. Please try again later.")
        return {"ok": True, "verification_required": True, "message": "Check your email for a verification link before signing in."}
    set_session(response, user["id"])
    return {"ok": True, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}}


@router.post("/login")
def login(payload: Credentials, request: Request, response: Response):
    require_csrf(request)
    email = str(payload.email).lower()
    _limit(request, email)
    user = get_record("users", "email", email)
    valid = user and user.get("password_hash") and _password_matches(payload.password, user["password_hash"])
    if not valid:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    if settings.require_email_verification and not user.get("email_verified"):
        raise HTTPException(status_code=403, detail="Verify your email before signing in.")
    set_session(response, user["id"])
    return {"ok": True, "user": {"id": user["id"], "email": user["email"], "name": user.get("name", "")}}


@router.post("/logout")
def logout(request: Request, response: Response):
    require_csrf(request)
    user_id = session_user_id(request)
    user = get_record("users", "id", user_id) if user_id else None
    if user:
        user["session_version"] = int(user.get("session_version", 0)) + 1
        user["updated_at"] = now_iso()
        save_record("users", user)
    clear_session(response)
    return {"ok": True}


@router.get("/verify")
def verify_email(token: str):
    digest = _token_digest(token)
    user = next((row for row in list_records("users") if row.get("verification_token_hash") == digest), None)
    if not user or int(user.get("verification_expires_at", 0)) < int(time.time()):
        raise HTTPException(status_code=400, detail="This verification link is invalid or expired.")
    user["email_verified"] = True
    user.pop("verification_token_hash", None)
    user.pop("verification_expires_at", None)
    user["updated_at"] = now_iso()
    save_record("users", user)
    return RedirectResponse("/login?verified=1", status_code=303)


@router.post("/forgot-password")
def forgot_password(payload: EmailRequest, request: Request):
    require_csrf(request)
    email = str(payload.email).lower()
    _limit(request, email)
    user = get_record("users", "email", email)
    if user and user.get("password_hash") and _smtp_ready():
        token = secrets.token_urlsafe(32)
        user["password_reset_hash"] = _token_digest(token)
        user["password_reset_expires_at"] = int(time.time()) + 3600
        save_record("users", user)
        _send_email(email, "Reset your Nhyapu Craft password", f"Reset your password: {settings.public_base_url}/reset-password?token={token}")
    return {"ok": True, "message": "If an account can be recovered, an email will be sent with next steps."}


@router.post("/reset-password")
def reset_password(payload: PasswordReset, request: Request):
    require_csrf(request)
    digest = _token_digest(payload.token)
    user = next((row for row in list_records("users") if row.get("password_reset_hash") == digest), None)
    if not user or int(user.get("password_reset_expires_at", 0)) < int(time.time()):
        raise HTTPException(status_code=400, detail="This password reset link is invalid or expired.")
    user["password_hash"] = _password_hash(payload.password)
    user["session_version"] = int(user.get("session_version", 0)) + 1
    user.pop("password_reset_hash", None)
    user.pop("password_reset_expires_at", None)
    user["updated_at"] = now_iso()
    save_record("users", user)
    return {"ok": True, "message": "Password updated. Sign in with your new password."}


@router.get("/google/start")
def google_start():
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured for this deployment.")
    redirect_uri = settings.google_redirect_uri or f"{settings.public_base_url.rstrip('/')}/api/auth/google/callback"
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    state_payload = f"{state}.{nonce}"
    query = urlencode({
        "client_id": settings.google_client_id, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": "openid email profile", "state": state,
        "nonce": nonce, "prompt": "select_account",
    })
    response = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}", status_code=302)
    response.set_cookie(OAUTH_STATE_COOKIE, state_payload, max_age=600, **secure_cookie_options())
    return response


@router.get("/google/callback")
async def google_callback(code: str, state: str, request: Request):
    state_payload = request.cookies.get(OAUTH_STATE_COOKIE, "")
    expected_state, _, expected_nonce = state_payload.partition(".")
    if not expected_state or not hmac.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail="Google sign-in could not be verified. Start again.")
    if not all((settings.google_client_id, settings.google_client_secret)):
        raise HTTPException(status_code=503, detail="Google sign-in is not configured for this deployment.")
    redirect_uri = settings.google_redirect_uri or f"{settings.public_base_url.rstrip('/')}/api/auth/google/callback"
    async with httpx.AsyncClient(timeout=12) as client:
        token_response = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret, "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        if token_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Google sign-in could not be completed.")
        id_token = token_response.json().get("id_token")
        token_info = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token})
    claims = token_info.json() if token_info.status_code == 200 else {}
    valid_claims = (
        claims.get("aud") == settings.google_client_id
        and claims.get("iss") in {"accounts.google.com", "https://accounts.google.com"}
        and claims.get("nonce") == expected_nonce
        and claims.get("email_verified") == "true"
        and int(claims.get("exp", 0)) > int(time.time())
        and claims.get("sub")
        and claims.get("email")
    )
    if not valid_claims:
        raise HTTPException(status_code=401, detail="Google returned an invalid sign-in response.")
    email = str(claims["email"]).lower()
    user = get_record("users", "google_sub", claims["sub"]) or get_record("users", "email", email)
    if user:
        if user.get("google_sub") not in (None, claims["sub"]):
            raise HTTPException(status_code=409, detail="This account is linked to a different Google identity.")
        user.update({"google_sub": claims["sub"], "email_verified": True, "updated_at": now_iso()})
        save_record("users", user)
    else:
        user = _new_user(email, claims.get("name") or email.split("@", 1)[0], None, claims["sub"])
        user["email_verified"] = True
        save_record("users", user)
    response = RedirectResponse("/workspace", status_code=303)
    set_session(response, user["id"])
    return response


@router.get("/account")
def account(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "name": user.get("name", ""), "created_at": user.get("created_at")}


@router.delete("/account")
def delete_account(request: Request, response: Response, user: dict = Depends(get_current_user)):
    require_csrf(request)
    owner_id = user["id"]
    delete_records("resumes", lambda row: row.get("user_id") == owner_id)
    delete_records("layouts", lambda row: row.get("owner_id") == owner_id)
    delete_records("users", lambda row: row.get("id") == owner_id)
    clear_session(response)
    generated_root = Path(settings.generated_dir).resolve()
    user_generated = (generated_root / owner_id).resolve()
    if user_generated.parent == generated_root:
        shutil.rmtree(user_generated, ignore_errors=True)
    return {"ok": True}
