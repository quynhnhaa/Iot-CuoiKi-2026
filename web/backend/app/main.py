"""Backend quan ly me dem cho do an may dem va loai vien thuoc loi.

Backend nay chi quan ly du lieu nghiep vu va lich su. No khong gui lenh cho
dong co hay cam bien, va khong tu tinh lai logic ba nhan cua nhanh AI.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.models import Base

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Ban demo tao bang truc tiep. Khi schema on dinh thi chuyen sang Alembic.
    from app import db

    Base.metadata.create_all(db.engine)
    yield


app = FastAPI(title=settings.app_name, version='0.1.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(api_router)


@app.get('/')
def root() -> dict:
    return {'app': settings.app_name, 'docs': '/docs', 'api': '/api/health'}
