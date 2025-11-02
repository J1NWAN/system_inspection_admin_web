from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from setting.supabase_client import supabase


async def fetch_users(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Supabase에서 사용자 목록을 조회한다."""

    def _query():
        query = supabase.table("admin_users").select("*").order("created_at", desc=True)
        if limit is not None:
            query = query.limit(limit)
        return query.execute()

    response = await asyncio.to_thread(_query)
    rows = response.data or []
    for row in rows:
        row["last_login_at"] = _format_timestamp(row.get("last_login_at"))
        row["created_at"] = _format_timestamp(row.get("created_at"))
        row["updated_at"] = _format_timestamp(row.get("updated_at"))
    return rows


def _format_timestamp(value: Any) -> Optional[str]:
    """ISO 문자열 또는 datetime 값을 'YYYY-MM-DD HH24:MI'로 반환한다."""
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f%z")
        except ValueError:
            return text
    return dt.strftime("%Y-%m-%d %H:%M")


async def fetch_user_history(
    *, user_id: Optional[str] = None, menu_code: Optional[str] = None, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """사용자 활동 이력을 조회한다."""

    def _query():
        query = supabase.table("admin_user_history").select("*").order("created_at", desc=True)
        if user_id:
            query = query.eq("user_id", user_id)
        if menu_code:
            query = query.eq("menu_code", menu_code)
        if limit is not None:
            query = query.limit(limit)
        return query.execute()

    response = await asyncio.to_thread(_query)
    rows = response.data or []
    if not rows:
        return rows

    menu_codes: Set[str] = {row["menu_code"] for row in rows if row.get("menu_code")}
    user_ids: Set[str] = {row["user_id"] for row in rows if row.get("user_id")}

    menu_map = await _fetch_menu_map(menu_codes) if menu_codes else {}
    user_map = await _fetch_user_map(user_ids) if user_ids else {}

    for row in rows:
        row["created_at"] = _format_timestamp(row.get("created_at"))
        code = row.get("menu_code")
        menu_info = menu_map.get(code) if code else None
        row["menu_name"] = menu_info.get("menu_name") if menu_info else None
        row["menu_path"] = menu_info.get("menu_path") if menu_info else None

        uid = row.get("user_id")
        user_info = user_map.get(uid) if uid else None
        row["user_name"] = user_info.get("user_name") if user_info else None
    return rows


async def _fetch_menu_map(codes: Set[str]) -> Dict[str, Dict[str, Any]]:
    def _query():
        query = supabase.table("admin_menus").select("menu_code, menu_name, menu_path")
        return query.in_("menu_code", list(codes)).execute()

    try:
        response = await asyncio.to_thread(_query)
        return {item["menu_code"]: item for item in (response.data or []) if item.get("menu_code")}
    except Exception:  # pylint: disable=broad-except
        return {}


async def create_user(payload: Dict[str, Any]) -> Dict[str, Any]:
    """사용자를 생성하고 생성된 레코드를 반환한다."""

    insertion = {
        "user_id": payload["user_id"],
        "password": payload["password"],
        "user_name": payload["user_name"],
        "email": payload.get("email"),
        "role": payload.get("role") or "user",
        "ip_address": payload.get("ip_address"),
        "login_status": payload.get("login_status") or "offline",
        "created_by": payload.get("created_by") or "system",
        "updated_by": payload.get("updated_by"),
    }
    
    def _insert():
        return supabase.table("admin_users").insert(insertion).execute()

    response = await asyncio.to_thread(_insert)

    if getattr(response, "error", None):
        raise ValueError(response.error.message if hasattr(response.error, "message") else str(response.error))

    data = response.data or []
    return data[0] if data else insertion


async def _fetch_user_map(user_ids: Set[str]) -> Dict[str, Dict[str, Any]]:
    def _query():
        query = supabase.table("admin_users").select("user_id, user_name")
        return query.in_("user_id", list(user_ids)).execute()

    try:
        response = await asyncio.to_thread(_query)
        return {item["user_id"]: item for item in (response.data or []) if item.get("user_id")}
    except Exception:  # pylint: disable=broad-except
        return {}