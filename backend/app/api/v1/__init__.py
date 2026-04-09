from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.data_service import router as data_service_router
from app.api.v1.data_service_auth import protected_router as data_service_protected_router
from app.api.v1.data_service_auth import router as data_service_auth_router


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(data_service_auth_router)
api_router.include_router(data_service_protected_router)
api_router.include_router(data_service_router)
