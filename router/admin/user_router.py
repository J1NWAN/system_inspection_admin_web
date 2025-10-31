from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr

from service.user_service import create_user, fetch_user_history, fetch_users

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/user", response_class=HTMLResponse, name="admin_user")
async def admin_user(request: Request):
    users: list = []
    histories: list = []
    user_error = None
    history_error = None
    total_user_count = None
    active_user_count = None

    try:
        users = await fetch_users()
        total_user_count = len(users)
        active_user_count = sum(
            1 for user in users if str(user.get("login_status") or "").lower() == "online"
        )
    except Exception as exc:  # pylint: disable=broad-except
        user_error = str(exc)

    try:
        histories = await fetch_user_history(limit=50)
    except Exception as exc:  # pylint: disable=broad-except
        history_error = str(exc)

    return templates.TemplateResponse(
        "admin/user.html",
        {
            "request": request,
            "user_list": users,
            "user_error": user_error,
            "total_user_count": total_user_count,
            "active_user_count": active_user_count,
            "history_list": histories,
            "history_error": history_error,
        },
    )


class UserCreateRequest(BaseModel):
    user_id: str
    password: str
    user_name: str
    email: EmailStr | None = None
    role: str | None = None


@router.post("/api/users", response_class=JSONResponse)
async def create_user_api(payload: UserCreateRequest):
    try:
        created = await create_user(payload.dict())
    except ValueError as exc:  # noqa: PERF203
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "user": created}
