#!/usr/bin/env python3
"""
README
------
Dependencies: requests, beautifulsoup4, playwright

Install:
    pip install requests beautifulsoup4 playwright
    playwright install

Usage:
    python extract_menu.py --url https://example.com --depth 1 --timeout 10 --user-agent "MyCrawler/1.0"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


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


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def normalize_url(base: str, link: str, domain: str) -> Optional[str]:
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


def clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def text_is_forbidden(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in FORBIDDEN_TEXT)


def derive_path(link: Tag) -> List[str]:
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
            label = clean_text(str(label))
            if label and label not in path:
                path.append(label)
    return list(reversed(path))


def extract_candidates_from_soup(
    soup: BeautifulSoup,
    base_url: str,
    domain: str,
) -> Dict[str, Dict[str, object]]:
    candidates: Dict[str, Dict[str, object]] = {}

    def consider_link(tag: Tag) -> None:
        text = clean_text(tag.get_text(separator=" ", strip=True))
        if not text or text_is_forbidden(text):
            return
        href = tag.get("href")
        normalized = normalize_url(base_url, href or "", domain)
        if not normalized:
            return
        if normalized not in candidates:
            candidates[normalized] = {
                "text": text,
                "url": normalized,
                "path": derive_path(tag),
            }

    # Focus on likely menu containers first
    for selector in ("nav", "header", "[role='navigation']"):
        for container in soup.select(selector):
            for link in container.find_all("a", href=True):
                consider_link(link)

    # Any elements with menu-like classes
    hints = ",".join(f".{hint}" for hint in MENU_CLASS_HINTS)
    for container in soup.select(hints):
        for link in container.find_all("a", href=True):
            consider_link(link)

    # Fallback to all anchors
    for link in soup.find_all("a", href=True):
        consider_link(link)

    return candidates


def fetch_with_requests(
    url: str,
    domain: str,
    depth: int,
    timeout: float,
    headers: Dict[str, str],
) -> Dict[str, Dict[str, object]]:
    visited: Set[str] = set()
    results: Dict[str, Dict[str, object]] = {}
    queue: deque[Tuple[str, int]] = deque([(url, 0)])

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
            log(f"[requests] status={resp.status_code} url={current_url} time={elapsed:.2f}s")
        except requests.RequestException as exc:
            log(f"[requests] error url={current_url} error={exc}")
            continue

        if resp.status_code >= 400:
            continue

        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type.lower():
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        page_candidates = extract_candidates_from_soup(soup, current_url, domain)
        for key, value in page_candidates.items():
            if key not in results:
                results[key] = value

        if current_depth + 1 <= depth:
            for link in soup.find_all("a", href=True):
                normalized = normalize_url(current_url, link.get("href", ""), domain)
                if normalized and normalized not in visited:
                    queue.append((normalized, current_depth + 1))

        if len(results) > 50:
            break

    return results


def fetch_with_playwright(url: str, domain: str, timeout: float, user_agent: Optional[str]) -> Dict[str, Dict[str, object]]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        log("[playwright] playwright is not installed. Skipping step.")
        return {}

    candidates: Dict[str, Dict[str, object]] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=user_agent)
        page = context.new_page()
        start = time.time()
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            elapsed = time.time() - start
            log(f"[playwright] loaded url={url} time={elapsed:.2f}s")
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            candidates = extract_candidates_from_soup(soup, url, domain)
        except Exception as exc:  # pylint: disable=broad-except
            log(f"[playwright] error navigating url={url} error={exc}")
        finally:
            context.close()
            browser.close()

    return candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract menu candidates from a website.")
    parser.add_argument("--url", required=True, help="Root URL to crawl (e.g. https://example.com)")
    parser.add_argument("--depth", type=int, default=1, help="Link depth for requests-based crawl (default: 1)")
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout in seconds for HTTP requests (default: 10)")
    parser.add_argument("--user-agent", default="MenuExtractor/1.0", help="User-Agent header value")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parsed = urlparse(args.url)
    if not parsed.scheme or not parsed.netloc:
        log("[error] --url must include scheme, e.g., https://example.com")
        sys.exit(1)

    domain = parsed.netloc
    headers = DEFAULT_HEADERS.copy()
    headers["user-agent"] = args.user_agent

    log(f"[info] Starting requests-based extraction url={args.url} depth={args.depth}")
    start = time.time()
    request_candidates = fetch_with_requests(args.url, domain, max(args.depth, 0), args.timeout, headers)
    request_time = time.time() - start
    log(f"[info] Requests extraction found {len(request_candidates)} candidates in {request_time:.2f}s")

    source = "requests"
    candidates = request_candidates

    if len(request_candidates) < 4:
        log("[info] Fewer than 4 candidates found. Attempting Playwright rendering.")
        start = time.time()
        playwright_candidates = fetch_with_playwright(args.url, domain, args.timeout, args.user_agent)
        playwright_time = time.time() - start
        log(f"[info] Playwright extraction found {len(playwright_candidates)} candidates in {playwright_time:.2f}s")
        if playwright_candidates:
            source = "playwright"
            candidates = playwright_candidates

    menu_list = sorted(
        candidates.values(),
        key=lambda item: (item["text"].lower(), item["url"]),
    )

    payload = {
        "source": source,
        "domain": domain,
        "menus": menu_list,
    }

    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
