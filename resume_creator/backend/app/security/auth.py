"""Signed, short-lived browser sessions and CSRF helpers for the same-origin app."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import HTTPException, Request, Response, status

from ..config import settings
from ..database.file_store import get_record

SESSION_COOKIE = settings.session_cookie_name
CSRF_COOKIE = "nhyapu_csrf"
OAUTH_STATE_COOKIE = "nhyapu_oauth_state"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _signature(payload: str) -> str:
    return _b64(hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).digest())


def set_session(response: Response, user_id: str) -> None:
    user = get_record("users", "id", user_id) or {}
    payload = _b64(json.dumps({"sub": user_id, "ver": user.get("session_version", 0), "exp": int(time.time()) + settings.session_max_age_seconds}, separators=(",", ":")).encode())
    response.set_cookie(
        SESSION_COOKIE, f"{payload}.{_signature(payload)}", max_age=settings.session_max_age_seconds,
        httponly=True, secure=settings.app_env.lower() == "production", samesite="lax", path="/",
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def session_claims(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(SESSION_COOKIE, "")
    try:
        payload, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, _signature(payload)):
            return None
        claims = json.loads(_unb64(payload))
        if not isinstance(claims.get("sub"), str) or int(claims.get("exp", 0)) <= int(time.time()):
            return None
        return claims
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def session_user_id(request: Request) -> str | None:
    claims = session_claims(request)
    return claims.get("sub") if claims else None


def get_current_user(request: Request) -> dict[str, Any]:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_csrf(request)
    user_id = session_user_id(request)
    user = get_record("users", "id", user_id) if user_id else None
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.")
    if settings.require_email_verification and not user.get("email_verified", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verify your email before continuing.")
    claims = session_claims(request) or {}
    if claims.get("ver", 0) != user.get("session_version", 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Sign in again.")
    return user


def require_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="This request could not be verified. Refresh the page and try again.")


def set_csrf(response: Response, token: str | None = None) -> str:
    token = token or secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE, token, max_age=settings.session_max_age_seconds,
        httponly=False, secure=settings.app_env.lower() == "production", samesite="lax", path="/",
    )
    return token


def secure_cookie_options() -> dict[str, Any]:
    return {"secure": settings.app_env.lower() == "production", "httponly": True, "samesite": "lax", "path": "/"}
