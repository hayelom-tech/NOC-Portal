import logging
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from server.config import COOKIE_NAME, allowed_hosts, app_environment
from server.database import SessionLocal
from server.models import UserRole
from server.services.security import user_from_token


request_logger = logging.getLogger("noc_portal.request")
PUBLIC_PATHS = {
    "/login.html",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/favicon.ico",
    "/healthz",
}
HTML_PATHS = {
    "/",
    "/login.html",
    "/admin.html",
    "/shift-portal.html",
}


def install_middleware(app: FastAPI) -> None:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        started_at = time.perf_counter()
        request_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith(("/api/", "/docs/")) or request.url.path in HTML_PATHS:
            response.headers["Cache-Control"] = "no-store"
        if request.url.path == "/api-docs":
            response.headers["Cache-Control"] = "no-store"
        if app_environment() == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        request_logger.info(
            "request completed request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started_at) * 1000,
        )
        return response

    @app.middleware("http")
    async def authenticate_requests(request: Request, call_next):
        path = request.url.path
        # Origin check for cookie-authenticated unsafe methods (CSRF mitigation).
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin:
                from urllib.parse import urlparse
                from server.config import allowed_hosts
                host = urlparse(origin).hostname
                if host not in allowed_hosts() and host not in {"localhost", "127.0.0.1"}:
                    return JSONResponse({"detail": "Invalid request origin"}, status_code=403)

        if path in PUBLIC_PATHS:
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        if not token:
            authorization = request.headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                token = authorization[7:].strip()
        if not token:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            return RedirectResponse("/login.html", status_code=303)

        with SessionLocal() as db:
            try:
                user = user_from_token(token, db)
            except HTTPException:
                if path.startswith("/api/"):
                    return JSONResponse({"detail": "Authentication required"}, status_code=401)
                return RedirectResponse("/login.html", status_code=303)
            if path.startswith("/docs") and user.role == UserRole.guest:
                return JSONResponse({"detail": "Guests cannot download documents"}, status_code=403)
            request.state.user = user
        return await call_next(request)
