"""Router 패키지 초기화 모듈."""

from .admin import dashboard_router, user_router, system_router
from .sample import router as sample_router

__all__ = ("dashboard_router", "sample_router", "user_router", "system_router")
