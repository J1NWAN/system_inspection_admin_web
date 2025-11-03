from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from service.system_service import (
    collect_system_menus,
    create_system,
    delete_system,
    fetch_system_menus,
    fetch_systems,
    update_system,
)

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/system", response_class=HTMLResponse, name="admin_system")
async def admin_system(request: Request):
    try:
        systems = await fetch_systems()
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return templates.TemplateResponse(
        "admin/system.html",
        {
            "request": request,
            "system_list": systems,
        },
    )


async def _parse_system_payload(request: Request) -> Dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        return await request.json()

    # 지원하지 않는 컨텐츠 타입도 폼으로 처리
    form = await request.form()
    return dict(form)


@router.post("/system", response_class=JSONResponse, name="admin_system_create")
async def admin_system_create(request: Request):
    payload = await _parse_system_payload(request)

    try:
        system = await create_system(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    accept = request.headers.get("accept", "").lower()
    if "application/json" not in accept and ("text/html" in accept or not accept):
        return RedirectResponse(url="/admin/system", status_code=status.HTTP_303_SEE_OTHER)

    return JSONResponse({"ok": True, "data": system}, status_code=status.HTTP_201_CREATED)


@router.put("/system/{system_code}", response_class=JSONResponse, name="admin_system_update")
async def admin_system_update(system_code: str, request: Request):
    payload = await _parse_system_payload(request)

    try:
        system = await update_system(system_code, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "data": system})


@router.delete("/system/{system_code}", response_class=JSONResponse, name="admin_system_delete")
async def admin_system_delete(system_code: str):
    try:
        await delete_system(system_code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return JSONResponse({"ok": True})


@router.get("/system/{system_code}/menus", response_class=JSONResponse, name="admin_system_menus")
async def admin_system_menus(system_code: str):
    try:
        menus = await fetch_system_menus(system_code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "data": menus})


@router.post("/system/{system_code}/menus/collect", response_class=JSONResponse, name="admin_system_collect_menus")
async def admin_system_collect_menus(system_code: str, request: Request):
    created_by: Optional[str] = None
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > 0:
        content_type = request.headers.get("content-type", "")
        try:
            if "application/json" in content_type:
                payload = await request.json()
            else:
                payload = dict(await request.form())
        except Exception:  # pylint: disable=broad-except
            payload = {}
        created_by = payload.get("created_by")

    try:
        result = await collect_system_menus(system_code, created_by=created_by)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return JSONResponse({"ok": True, "data": result})
