from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from setting.supabase_client import supabase


async def fetch_menu_tree(
    active_menu_code: Optional[str] = None, current_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Supabase에서 관리자 메뉴를 조회해 트리 형태로 반환한다."""
    result = await asyncio.to_thread(
        lambda: supabase.table("admin_menus")
        .select("*")
        .order("sort_order")
        .order("menu_code")
        .execute()
    )

    rows: List[Dict[str, Any]] = result.data or []
    tree = _build_tree(rows)
    if active_menu_code or current_path:
        _mark_active_branch(tree, active_menu_code, current_path)
    return tree


def _build_tree(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tree: List[Dict[str, Any]] = []
    lookup: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        node = {
            "menu_seq": row.get("menu_seq"),
            "parent_menu_code": row.get("parent_menu_code"),
            "menu_code": row.get("menu_code"),
            "menu_name": row.get("menu_name"),
            "menu_path": row.get("menu_path"),
            "icon_class": row.get("icon_class"),
            "sort_order": row.get("sort_order", 0),
            "children": [],
            "is_active": False,
            "has_active_child": False,
            "raw": row,
        }
        lookup[node["menu_code"]] = node

    for node in lookup.values():
        parent_code: Optional[str] = node["parent_menu_code"]
        if parent_code and parent_code in lookup:
            lookup[parent_code]["children"].append(node)
        else:
            tree.append(node)

    def sort_children(items: List[Dict[str, Any]]):
        items.sort(key=lambda item: item.get("sort_order", 0))
        for child in items:
            if child["children"]:
                sort_children(child["children"])

    sort_children(tree)
    return tree


def _mark_active_branch(
    nodes: List[Dict[str, Any]], active_menu_code: Optional[str], current_path: Optional[str]
) -> bool:
    """활성 메뉴 코드 또는 현재 경로를 기준으로 트리 노드에 활성 상태를 표시한다."""
    has_active_descendant = False

    for node in nodes:
        children: List[Dict[str, Any]] = node.get("children", [])
        child_active = _mark_active_branch(children, active_menu_code, current_path) if children else False

        node_active = False
        if active_menu_code and node.get("menu_code") == active_menu_code:
            node_active = True
        if current_path and node.get("menu_path") == current_path:
            node_active = True

        node["is_active"] = node_active
        node["has_active_child"] = child_active

        if node_active or child_active:
            has_active_descendant = True

    return has_active_descendant
