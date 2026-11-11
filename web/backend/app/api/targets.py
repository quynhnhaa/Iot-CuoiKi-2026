from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_reader
from app.db import get_session
from app.models import Target
from app.schemas.target import TargetCreate, TargetRead

router = APIRouter(prefix='/targets', tags=['targets'])


@router.get('', response_model=list[TargetRead], dependencies=[Depends(require_reader)])
def list_targets(session: Session = Depends(get_session)) -> list[Target]:
    return list(session.scalars(select(Target).order_by(Target.id)))


@router.post(
    '', response_model=TargetRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_target(payload: TargetCreate, session: Session = Depends(get_session)) -> Target:
    target = Target(**payload.model_dump())
    session.add(target)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f'Mã mẫu chuẩn "{payload.code}" đã tồn tại') from None
    session.refresh(target)
    return target


@router.get('/{target_id}', response_model=TargetRead, dependencies=[Depends(require_reader)])
def get_target(target_id: int, session: Session = Depends(get_session)) -> Target:
    target = session.get(Target, target_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Không tìm thấy mẫu chuẩn')
    return target
