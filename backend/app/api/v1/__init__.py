from fastapi import APIRouter

from app.api.v1 import auth, users, demands, email, logs, settings as settings_api

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(demands.router)
api_router.include_router(email.router)
api_router.include_router(logs.router)
api_router.include_router(settings_api.router)
