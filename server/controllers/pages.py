import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from server.database import SessionLocal
from server.services.static_data import read_csv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = PROJECT_ROOT / "ui" / "pages"
router = APIRouter()


def _read_page(filename: str) -> str:
    try:
        return (UI_DIR / filename).read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Portal page is unavailable") from exc


def _inject_data(html_file: str, variable_name: str, data: object) -> HTMLResponse:
    html = _read_page(html_file)
    safe_json = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    script_tag = f"<script>window.{variable_name} = {safe_json};</script>"
    return HTMLResponse(content=html.replace("</head>", script_tag + "\n</head>", 1))


@router.get("/healthz/live", include_in_schema=False)
def liveness() -> dict[str, str]:
    """Process is alive (no dependency checks)."""
    return {"status": "ok"}


@router.get("/healthz/ready", include_in_schema=False)
def readiness() -> dict[str, str]:
    """Dependencies (database) are reachable."""
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}

@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    """Minimal readiness probe; intentionally returns no dependency details."""
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/shift-portal.html")


@router.get("/login.html", response_class=HTMLResponse, include_in_schema=False)
def login_page() -> HTMLResponse:
    return HTMLResponse(_read_page("login.html"))


@router.get("/shift-portal.html", response_class=HTMLResponse, include_in_schema=False)
def shift_portal_page() -> HTMLResponse:
    return HTMLResponse(_read_page("shift-portal.html"), headers={"Cache-Control": "no-store"})
@router.get("/admin.html", response_class=HTMLResponse, include_in_schema=False)
def admin_page() -> HTMLResponse:
    return HTMLResponse(_read_page("admin.html"))
@router.get("/handover.html", include_in_schema=False)
def handover_page() -> RedirectResponse:
    return RedirectResponse("/shift-portal.html")
