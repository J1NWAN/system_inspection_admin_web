from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from setting.supabase_client import supabase

logger = logging.getLogger(__name__)

DEFAULT_UA = "MenuExtractor/1.0"
EXTRACT_MENU_SCRIPT = Path(__file__).resolve().parents[1] / "extract_menu.py"
FORBIDDEN_TEXT = ("privacy", "terms", "copyright", "contact-us", "contact us", "이메일무단수집")
MENU_CLASS_HINTS = (
    "menu",
    "nav",
    "navbar",
    "gnb",
    "lnb",
    "main-nav",
    "site-nav",
    "sidebar",
    "drawer",
    "topbar",
)
DEFAULT_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

MenuCandidate = Dict[str, Any]
CandidateMap = Dict[str, MenuCandidate]


def _normalize_url(base: str, link: str, domain: str) -> Optional[str]:
    if not link:
        return None
    if link.startswith(("mailto:", "tel:", "javascript:")):
        return None

    absolute = urljoin(base, link)
    parsed = urlparse(absolute)

    if parsed.scheme not in ("http", "https"):
        return None

    if parsed.netloc and parsed.netloc.lower() != domain.lower():
        return None

    normalized = parsed._replace(fragment="").geturl()
    return normalized


def _clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def _text_is_forbidden(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in FORBIDDEN_TEXT)


def _derive_path(link: Tag) -> List[str]:
    path: List[str] = []
    for ancestor in link.parents:
        if not isinstance(ancestor, Tag):
            continue
        label = None
        if ancestor.name in {"nav", "header"}:
            label = ancestor.get("aria-label") or ancestor.get("title") or ancestor.get("id")
        elif ancestor.name in {"ul", "ol"}:
            label = ancestor.get("aria-label") or ancestor.get("class")
        elif ancestor.name in {"section", "div"}:
            classes = ancestor.get("class") or []
            if any(hint in " ".join(classes).lower() for hint in MENU_CLASS_HINTS):
                label = " ".join(classes)
        if label:
            if isinstance(label, list):
                label = " ".join(label)
            label = _clean_text(str(label))
            if label and label not in path:
                path.append(label)
    return list(reversed(path))


def _extract_candidates_from_soup(
    soup: BeautifulSoup,
    base_url: str,
    domain: str,
) -> CandidateMap:
    candidates: CandidateMap = {}

    def consider_link(tag: Tag) -> None:
        text = _clean_text(tag.get_text(separator=" ", strip=True))
        if not text or _text_is_forbidden(text):
            return
        href = tag.get("href")
        normalized = _normalize_url(base_url, href or "", domain)
        if not normalized:
            return
        if normalized not in candidates:
            candidates[normalized] = {
                "text": text,
                "url": normalized,
                "path": _derive_path(tag),
            }

    for selector in ("nav", "header", "[role='navigation']"):
        for container in soup.select(selector):
            for link in container.find_all("a", href=True):
                consider_link(link)

    hints = ",".join(f".{hint}" for hint in MENU_CLASS_HINTS)
    for container in soup.select(hints):
        for link in container.find_all("a", href=True):
            consider_link(link)

    for link in soup.find_all("a", href=True):
        consider_link(link)

    return candidates


def _fetch_with_requests(
    url: str,
    domain: str,
    depth: int,
    timeout: float,
    headers: Dict[str, str],
) -> CandidateMap:
    visited: Set[str] = set()
    results: CandidateMap = {}
    queue: Deque[Tuple[str, int]] = deque([(url, 0)])

    session = requests.Session()
    session.headers.update(headers)

    while queue:
        current_url, current_depth = queue.popleft()
        if current_url in visited:
            continue
        visited.add(current_url)

        try:
            start = time.time()
            resp = session.get(current_url, timeout=timeout)
            elapsed = time.time() - start
            logger.debug("[requests] status=%s url=%s time=%.2fs", resp.status_code, current_url, elapsed)
        except requests.RequestException as exc:
            logger.warning("[requests] error url=%s error=%s", current_url, exc)
            continue

        if resp.status_code >= 400:
            continue

        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type.lower():
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        page_candidates = _extract_candidates_from_soup(soup, current_url, domain)
        for key, value in page_candidates.items():
            if key not in results:
                results[key] = value

        if current_depth + 1 <= depth:
            for link in soup.find_all("a", href=True):
                normalized = _normalize_url(current_url, link.get("href", ""), domain)
                if normalized and normalized not in visited:
                    queue.append((normalized, current_depth + 1))

        if len(results) > 50:
            break

    return results


def _fetch_with_playwright(
    url: str,
    domain: str,
    timeout: float,
    user_agent: Optional[str],
) -> CandidateMap:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        logger.info("playwright is not installed. skipping playwright extraction.")
        return {}

    candidates: CandidateMap = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=user_agent)
        page = context.new_page()
        start = time.time()
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            elapsed = time.time() - start
            logger.debug("[playwright] loaded url=%s time=%.2fs", url, elapsed)
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            candidates = _extract_candidates_from_soup(soup, url, domain)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("[playwright] error navigating url=%s error=%s", url, exc)
        finally:
            context.close()
            browser.close()

    return candidates


def _collect_menu_candidates_internal(
    url: str,
    depth: int,
    timeout: float,
    user_agent: str,
) -> Dict[str, Any]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("유효한 도메인 주소가 필요합니다.")

    domain = parsed.netloc
    headers = DEFAULT_HEADERS.copy()
    headers["user-agent"] = user_agent

    logger.info("starting requests-based extraction url=%s depth=%s", url, depth)
    start = time.time()
    request_candidates = _fetch_with_requests(url, domain, max(depth, 0), timeout, headers)
    request_time = time.time() - start
    logger.info("requests extraction found %s candidates in %.2fs", len(request_candidates), request_time)

    source = "requests"
    candidates = request_candidates
    used_playwright = False
    playwright_time = 0.0

    if len(request_candidates) < 4:
        logger.info("fewer than 4 candidates found via requests. attempting playwright.")
        start = time.time()
        playwright_candidates = _fetch_with_playwright(url, domain, timeout, user_agent)
        playwright_time = time.time() - start
        logger.info("playwright extraction found %s candidates in %.2fs", len(playwright_candidates), playwright_time)
        if playwright_candidates:
            source = "playwright"
            candidates = playwright_candidates
            used_playwright = True

    menu_list = sorted(
        candidates.values(),
        key=lambda item: (item["text"].lower(), item["url"]),
    )

    total_elapsed = request_time + (playwright_time if used_playwright else 0.0)

    summary = {
        "source": source,
        "domain": domain,
        "count": len(menu_list),
        "elapsed": round(total_elapsed, 2),
        "used_playwright": used_playwright,
    }

    return {"summary": summary, "menus": menu_list}


def _collect_menu_candidates_via_script(
    url: str,
    depth: int,
    timeout: float,
    user_agent: str,
) -> Dict[str, Any]:

    interpreter = _resolve_python_interpreter()
    if not EXTRACT_MENU_SCRIPT.exists():
        raise FileNotFoundError("extract_menu.py 파일을 찾을 수 없습니다.")

    command = [
        interpreter,
        str(EXTRACT_MENU_SCRIPT),
        "--url",
        url,
        "--depth",
        str(depth),
        "--timeout",
        str(timeout),
        "--user-agent",
        user_agent,
    ]

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    stderr_text = (completed.stderr or "").strip()
    if stderr_text:
        logger.info("extract_menu.py stderr: %s", stderr_text)

    if completed.returncode != 0:
        message = stderr_text or "extract_menu.py 실행 중 오류가 발생했습니다."
        raise ValueError(message)

    stdout_text = (completed.stdout or "").strip()
    if not stdout_text:
        raise ValueError("extract_menu.py 결과가 비어 있습니다.")

    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError as exc:
        raise ValueError("extract_menu.py 결과를 파싱할 수 없습니다.") from exc

    menus: List[Dict[str, Any]] = list(payload.get("menus") or [])
    summary = {
        "source": payload.get("source") or "extract_menu.py",
        "domain": payload.get("domain"),
        "count": len(menus),
        "elapsed": payload.get("elapsed"),
        "used_playwright": (payload.get("source") or "").lower() == "playwright",
        "script": True,
    }

    return {"summary": summary, "menus": menus}


def _collect_menu_candidates(
    url: str,
    depth: int,
    timeout: float,
    user_agent: str,
) -> Dict[str, Any]:
    logger.debug(
        "execute extract_menu.py using interpreter=%s script=%s",
        _resolve_python_interpreter(),
        EXTRACT_MENU_SCRIPT,
    )
    try:
        result = _collect_menu_candidates_via_script(url, depth, timeout, user_agent)
        logger.info(
            "extract_menu.py를 사용해 %s개의 메뉴를 수집했습니다.",
            result.get("summary", {}).get("count"),
        )
        return result
    except FileNotFoundError:
        logger.info("extract_menu.py 파일을 찾을 수 없어 내부 수집 로직을 사용합니다.")
    except ValueError as exc:
        logger.warning("extract_menu.py 실행 실패: %s", exc)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("extract_menu.py 실행 중 예기치 못한 오류가 발생했습니다: %s", exc)

    return _collect_menu_candidates_internal(url, depth, timeout, user_agent)


def _resolve_python_interpreter() -> str:
    venv_path = os.environ.get("VIRTUAL_ENV")
    if venv_path:
        candidate = Path(venv_path) / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if sys.platform == "win32" else "python")
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _ensure_absolute_url(domain: str) -> str:
    parsed = urlparse(domain)
    if parsed.scheme and parsed.netloc:
        return domain
    if not parsed.netloc and parsed.path:
        return f"https://{parsed.path}"
    if parsed.netloc and not parsed.scheme:
        return f"https://{domain}"
    return f"https://{domain}"


async def _fetch_system_record(system_code: str) -> Optional[Dict[str, Any]]:
    def _query():
        return (
            supabase.table("inspection_systems")
            .select("*")
            .eq("system_code", system_code)
            .limit(1)
            .execute()
        )

    response = await asyncio.to_thread(_query)
    if getattr(response, "error", None):
        message = response.error.message if hasattr(response.error, "message") else str(response.error)
        raise ValueError(message)

    rows = response.data or []
    return rows[0] if rows else None


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


async def _replace_system_menus(system_code: str, menus: List[Dict[str, Any]], created_by: str) -> None:
    """기존 메뉴를 삭제하고 새 메뉴를 저장한다."""

    def _delete():
        return supabase.table("inspection_system_menus").delete().eq("system_code", system_code).execute()

    delete_response = await asyncio.to_thread(_delete)
    if getattr(delete_response, "error", None):
        message = delete_response.error.message if hasattr(delete_response.error, "message") else str(delete_response.error)
        raise ValueError(message)

    if not menus:
        return

    payloads: List[Dict[str, Any]] = []
    for item in menus:
        payloads.append(
            {
                "system_code": system_code,
                "menu_name": item.get("menu_name"),
                "path": item.get("path"),
                "created_by": created_by,
            }
        )

    def _insert():
        return supabase.table("inspection_system_menus").insert(payloads).execute()

    insert_response = await asyncio.to_thread(_insert)
    if getattr(insert_response, "error", None):
        message = insert_response.error.message if hasattr(insert_response.error, "message") else str(insert_response.error)
        raise ValueError(message)


async def collect_system_menus(
    system_code: str,
    *,
    depth: int = 1,
    timeout: float = 10.0,
    user_agent: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """등록된 시스템의 도메인을 기준으로 메뉴를 수집한다."""

    record = await _fetch_system_record(system_code)
    if not record:
        raise ValueError("해당 시스템을 찾을 수 없습니다.")

    domain = record.get("domain")
    if not domain:
        raise ValueError("도메인 정보가 등록되어 있지 않습니다.")

    target_url = _ensure_absolute_url(domain)
    agent = user_agent or DEFAULT_UA

    result = await asyncio.to_thread(_collect_menu_candidates, target_url, depth, timeout, agent)

    summary: Dict[str, Any] = dict(result.get("summary") or {})
    summary.update(
        {
            "system_code": system_code,
            "url": target_url,
        }
    )

    menus_raw: List[MenuCandidate] = list(result.get("menus") or [])
    menus: List[Dict[str, Any]] = []
    for item in menus_raw:
        parsed_url = urlparse(item.get("url") or "")
        path_value = parsed_url.path or "/"
        if parsed_url.query:
            path_value = f"{path_value}?{parsed_url.query}"
        breadcrumbs = " > ".join(item.get("path") or [])

        menus.append(
            {
                "system_code": system_code,
                "menu_name": item.get("text"),
                "menu_path": path_value,
                "path": path_value,
                "breadcrumbs": breadcrumbs,
                "raw": item,
            }
        )

    summary["count"] = len(menus)

    creator = (created_by or record.get("updated_by") or record.get("created_by") or "system").strip() or "system"

    await _replace_system_menus(system_code, menus, creator)

    return {"summary": summary, "menus": menus}
