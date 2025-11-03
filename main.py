from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from router import dashboard_router, sample_router, user_router, system_router
from service.menu_service import fetch_menu_tree

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="FastAPI Sample App")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(sample_router)
app.include_router(dashboard_router)
app.include_router(user_router)
app.include_router(system_router)


@app.middleware("http")
async def attach_admin_menu(request: Request, call_next):
    """관리자 경로 진입 시 메뉴 트리를 미리 조회해 request.state에 저장한다."""
    request.state.menu_tree = []
    request.state.menu_error = None
    if request.url.path.startswith("/admin"):
        try:
            request.state.menu_tree = await fetch_menu_tree(current_path=request.url.path)
        except Exception as exc:  # pylint: disable=broad-except
            request.state.menu_error = str(exc)
    response = await call_next(request)
    return response


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Render the landing page using a Jinja2 template."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "FastAPI Sample", "message": "이 페이지는 FastAPI와 Jinja2 템플릿의 간단한 예시입니다."},
    )
