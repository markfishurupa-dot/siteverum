"""Browser sessions and Basic authentication for SiteVerum API clients."""

import hmac
import os
import re
import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from runtime import connect

SESSION_DURATION = timedelta(hours=12)
NO_STORE = {"Cache-Control": "no-store"}
optional_basic = HTTPBasic(auto_error=False)


def session_cookie(request: Request) -> str:
    # Browsers share host cookies across ports.
    port = request.url.port
    return f"siteverum_session_{port}" if port else "siteverum_session"


def credentials_match(username: str, password: str) -> bool:
    return (hmac.compare_digest(username.encode(), b"admin")
            and hmac.compare_digest(password.encode(), os.environ["SV_ADMIN_PASSWORD"].encode()))


def session_digest(token: str | None) -> str | None:
    if token is None or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    return hmac.digest(os.environ["SV_ADMIN_PASSWORD"].encode(), token.encode(), "sha256").hex()


def signed_in(request: Request, credentials: HTTPBasicCredentials | None) -> bool:
    cookie = session_cookie(request)
    if cookie not in request.cookies:
        return credentials is not None and credentials_match(credentials.username, credentials.password)
    digest = session_digest(request.cookies[cookie])
    if digest is None:
        return False
    with connect() as db:
        return db.execute("SELECT 1 FROM portal_sessions WHERE digest=%s AND expires_at>now()",
                          (digest,)).fetchone() is not None


def require_request_header(request: Request) -> None:
    if request.method not in {"GET", "HEAD"} and request.headers.get("X-StreetView-Request") != "1":
        raise HTTPException(403, "Missing request protection header")


def authenticate(request: Request, credentials: HTTPBasicCredentials | None = Depends(optional_basic)):
    if not signed_in(request, credentials):
        headers = dict(NO_STORE)
        if session_cookie(request) not in request.cookies:
            headers["WWW-Authenticate"] = "Basic"
        raise HTTPException(401, "Sign in as admin", headers=headers)
    require_request_header(request)


def set_session_cookie(request: Request, response: Response, value: str) -> None:
    response.set_cookie(session_cookie(request), value, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https")


def start_session(request: Request, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    previous = session_digest(request.cookies.get(session_cookie(request)))
    with connect() as db:
        db.execute("DELETE FROM portal_sessions WHERE expires_at<=now() OR digest=%s", (previous,))
        db.execute("INSERT INTO portal_sessions(digest,expires_at) VALUES (%s,now()+%s)",
                   (session_digest(token), SESSION_DURATION))
    set_session_cookie(request, response, token)


def end_session(request: Request, response: Response) -> None:
    digest = session_digest(request.cookies.get(session_cookie(request)))
    if digest is not None:
        with connect() as db:
            db.execute("DELETE FROM portal_sessions WHERE digest=%s", (digest,))
    # Suppress browser-cached Basic credentials after logout.
    set_session_cookie(request, response, "signed-out")
