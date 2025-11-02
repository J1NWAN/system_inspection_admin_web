from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from setting.supabase_client import supabase

async def fetch_weekly_login_stats() -> Dict[str, Any]:
    """이번 주와 지난 주의 로그인 성공 횟수를 비교한다."""
    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_this_week = start_today - timedelta(days=start_today.weekday())
    start_next_week = start_this_week + timedelta(days=7)
    start_last_week = start_this_week - timedelta(days=7)

    this_week = await _count_success_logins(start_this_week, start_next_week)
    last_week = await _count_success_logins(start_last_week, start_this_week)

    diff = this_week - last_week

    if last_week > 0:
        diff_percent = round((diff / last_week) * 100, 1)
    else:
        diff_percent = 100.0 if this_week > 0 else 0.0

    trend = "flat"
    if diff > 0:
        trend = "up"
    elif diff < 0:
        trend = "down"

    return {
        "this_week": this_week,
        "last_week": last_week,
        "diff": diff,
        "diff_percent": diff_percent,
        "trend": trend,
        "week_start": start_this_week.date().isoformat(),
        "week_end": (start_next_week - timedelta(seconds=1)).date().isoformat(),
    }


async def _count_success_logins(start: datetime, end: datetime) -> int:
    iso_start = start.isoformat()
    iso_end = end.isoformat()

    def _query():
        return (
            supabase
            .table("admin_user_history")
            .select("menu_code", count="exact")
            .eq("menu_code", "login")
            .eq("result_status", "success")
            .gte("created_at", iso_start)
            .lt("created_at", iso_end)
            .execute()
        )

    response = await asyncio.to_thread(_query)

    if getattr(response, "error", None):
        raise ValueError(response.error.message if hasattr(response.error, "message") else str(response.error))

    if response.count is not None:
        return response.count

    return len(response.data or [])

async def fetch_inspection_systems_count() -> int:
    """inspection_systems 테이블에 등록된 시스템 수를 반환한다."""

    def _query():
        return supabase.table("inspection_systems").select("system_code", count="exact").execute()

    response = await asyncio.to_thread(_query)

    if getattr(response, "error", None):
        message = response.error.message if hasattr(response.error, "message") else str(response.error)
        raise ValueError(message)

    if response.count is not None:
        return response.count

    return len(response.data or [])


async def fetch_inspection_system_menus_count() -> int:
    """inspection_system_menus 테이블에 등록된 메뉴 수를 반환한다."""

    def _query():
        return supabase.table("inspection_system_menus").select("menu_name", count="exact").execute()

    response = await asyncio.to_thread(_query)

    if getattr(response, "error", None):
        message = response.error.message if hasattr(response.error, "message") else str(response.error)
        raise ValueError(message)

    if response.count is not None:
        return response.count

    return len(response.data or [])


async def fetch_today_inspection_error_count() -> int:
    """오늘 날짜 기준으로 inspection_history에서 오류 수를 반환한다."""

    now = datetime.now().astimezone()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_next_day = start_of_day + timedelta(days=1)

    iso_start = start_of_day.isoformat()
    iso_end = start_of_next_day.isoformat()

    def _query():
        return (
            supabase.table("inspection_history")
            .select("inspection_result", count="exact")
            .eq("inspection_result", "error")
            .gte("inspected_at", iso_start)
            .lt("inspected_at", iso_end)
            .execute()
        )

    response = await asyncio.to_thread(_query)

    if getattr(response, "error", None):
        message = response.error.message if hasattr(response.error, "message") else str(response.error)
        raise ValueError(message)

    if response.count is not None:
        return response.count

    return len(response.data or [])
