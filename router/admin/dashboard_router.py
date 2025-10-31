from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from setting.supabase_client import supabase
from service.user_service import fetch_weekly_login_stats

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/", include_in_schema=False)
async def redirect_to_dashboard() -> RedirectResponse:
    return RedirectResponse(url="/admin/dashboard", status_code=307)


@router.get("/dashboard", response_class=HTMLResponse, name="admin_dashboard")
async def admin_dashboard(request: Request):
    logs = []
    status_error = None
    weekly_stats = None
    weekly_stats_error = None

    try:
        response = await asyncio.to_thread(
            lambda: supabase.table("status_logs").select("*").order("created_at", desc=True).limit(5).execute()
        )
        logs = response.data
    except Exception as exc:  # pylint: disable=broad-except
        status_error = str(exc)

    try:
        weekly_stats = await fetch_weekly_login_stats()
    except Exception as exc:  # pylint: disable=broad-except
        weekly_stats_error = str(exc)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "supabase_logs": logs,
            "supabase_error": status_error,
            "weekly_login_stats": weekly_stats,
            "weekly_login_stats_error": weekly_stats_error,
        },
    )


@router.get("/sample", response_class=HTMLResponse, name="admin_sample")
async def admin_sample(request: Request):
    return templates.TemplateResponse("admin/sample.html", {"request": request})


@router.get("/dashboard/status", response_class=JSONResponse, name="admin_dashboard_status")
async def admin_dashboard_status():
    try:
        response = await asyncio.to_thread(
            lambda: supabase.table("status_logs").select("*").order("created_at", desc=True).limit(5).execute()
        )
        return JSONResponse({"ok": True, "data": response.data})
    except Exception as exc:  # pylint: disable=broad-except
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
