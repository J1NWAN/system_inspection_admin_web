from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"
SAMPLE_DIR = TEMPLATE_DIR / "sample"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
router = APIRouter(prefix="/sample", tags=["sample"])

_slug_pattern = re.compile(r"^[a-z0-9-]+$")
_sample_templates: Dict[str, str] = {
    page.stem: str(page.relative_to(TEMPLATE_DIR)).replace("\\", "/")
    for page in SAMPLE_DIR.glob("*.html")
}


@router.get("/", response_class=HTMLResponse, summary="샘플 대시보드 페이지")
async def render_sample_index(request: Request):
    if "index" not in _sample_templates:
        raise HTTPException(status_code=404, detail="index 템플릿을 찾을 수 없습니다.")
    return templates.TemplateResponse(_sample_templates["index"], {"request": request})


@router.get("/{page_slug}", response_class=HTMLResponse, summary="샘플 HTML 렌더링")
async def render_sample_page(page_slug: str, request: Request):
    if not _slug_pattern.fullmatch(page_slug):
        raise HTTPException(status_code=400, detail="허용되지 않는 페이지 식별자입니다.")

    template_path = _sample_templates.get(page_slug)
    if not template_path:
        raise HTTPException(status_code=404, detail="요청한 샘플 페이지를 찾을 수 없습니다.")

    return templates.TemplateResponse(template_path, {"request": request})
