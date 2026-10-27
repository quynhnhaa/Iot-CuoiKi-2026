from fastapi import APIRouter

from app.api import ai_runs, auth, batches, health, pill_events, targets, thingsboard, users

api_router = APIRouter(prefix='/api')
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(targets.router)
api_router.include_router(batches.router)
api_router.include_router(pill_events.router)
api_router.include_router(ai_runs.router)
api_router.include_router(thingsboard.router)

__all__ = ['api_router']
