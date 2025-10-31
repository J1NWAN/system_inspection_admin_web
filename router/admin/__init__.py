"""Admin 라우터 패키지."""

from .dashboard_router import router as dashboard_router
from .user_router import router as user_router


__all__ = ("dashboard_router", "user_router")
