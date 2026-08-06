"""
API v1 router — aggregates all endpoint sub-routers.
All routes are prefixed with /api/v1 (set in main.py).
"""

from fastapi import APIRouter

from app.api.v1.endpoints.tokens import router as tokens_router
from app.api.v1.endpoints.wallets import router as wallets_router
from app.api.v1.endpoints.events import router as events_router
from app.api.v1.endpoints.analysis import router as analysis_router
from app.api.v1.endpoints.alerts import router as alerts_router
from app.api.v1.endpoints.whales import router as whales_router

api_router = APIRouter()

api_router.include_router(tokens_router)
api_router.include_router(wallets_router)
api_router.include_router(events_router)
api_router.include_router(analysis_router)
api_router.include_router(alerts_router)
api_router.include_router(whales_router)
