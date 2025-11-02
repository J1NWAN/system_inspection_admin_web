from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from setting.supabase_client import supabase


async def fetch_systems(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """등록된 점검 대상 시스템 목록을 조회한다."""

    def _query():
        query = supabase.table("inspection_systems").select("*").order("created_at", desc=True)
        if limit is not None:
            query = query.limit(limit)
        return query.execute()

    response = await asyncio.to_thread(_query)
    return response.data or []


async def fetch_system_menus(system_code: str) -> List[Dict[str, Any]]:
    """특정 시스템에 등록된 메뉴 목록을 조회한다."""

    def _query():
        return (
            supabase.table("inspection_system_menus")
            .select("*")
            .eq("system_code", system_code)
            .order("menu_name")
            .execute()
        )

    response = await asyncio.to_thread(_query)

    if getattr(response, "error", None):
        message = response.error.message if hasattr(response.error, "message") else str(response.error)
        raise ValueError(message)

    return response.data or []


async def create_system(payload: Dict[str, Any]) -> Dict[str, Any]:
    """새로운 점검 대상 시스템을 등록한다."""

    insertion = {
        "system_code": payload["system_code"],
        "system_name": payload["system_name"],
        "domain": payload["domain"],
        "created_by": payload.get("created_by") or "system",
        "updated_by": payload.get("updated_by"),
    }

    def _insert():
        return supabase.table("inspection_systems").insert(insertion).execute()

    response = await asyncio.to_thread(_insert)

    if getattr(response, "error", None):
        message = response.error.message if hasattr(response.error, "message") else str(response.error)
        raise ValueError(message)

    data = response.data or []
    return data[0] if data else insertion


async def update_system(system_code: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """기존 점검 대상 시스템 정보를 수정한다."""

    updates: Dict[str, Any] = {
        "system_name": payload.get("system_name"),
        "domain": payload.get("domain"),
        "description": payload.get("description"),
        "updated_by": payload.get("updated_by"),
    }

    # Supabase는 None 값을 업데이트 하지 않도록 필터링한다.
    updates = {key: value for key, value in updates.items() if value is not None}

    if not updates:
        raise ValueError("업데이트할 항목이 없습니다.")

    def _update():
        return (
            supabase.table("inspection_systems")
            .update(updates)
            .eq("system_code", system_code)
            .execute()
        )

    response = await asyncio.to_thread(_update)

    if getattr(response, "error", None):
        message = response.error.message if hasattr(response.error, "message") else str(response.error)
        raise ValueError(message)

    data = response.data or []
    if not data:
        raise ValueError("해당 시스템을 찾을 수 없습니다.")
    return data[0]


async def delete_system(system_code: str) -> None:
    """등록된 점검 대상 시스템 및 연결된 메뉴를 삭제한다."""

    def _delete_menus():
        return supabase.table("inspection_system_menus").delete().eq("system_code", system_code).execute()

    menu_response = await asyncio.to_thread(_delete_menus)

    if getattr(menu_response, "error", None):
        message = menu_response.error.message if hasattr(menu_response.error, "message") else str(menu_response.error)
        raise ValueError(message)

    def _delete_system():
        return supabase.table("inspection_systems").delete().eq("system_code", system_code).execute()

    system_response = await asyncio.to_thread(_delete_system)

    if getattr(system_response, "error", None):
        message = system_response.error.message if hasattr(system_response.error, "message") else str(system_response.error)
        raise ValueError(message)

    data = system_response.data or []
    if not data:
        raise ValueError("해당 시스템을 찾을 수 없습니다.")
