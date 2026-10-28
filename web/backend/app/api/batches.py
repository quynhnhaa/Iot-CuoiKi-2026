from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_operator, require_reader
from app.db import get_session
from app.models import Batch, Target
from app.schemas.batch import BatchCreate, BatchDetail, BatchRead, BatchStatusUpdate
from app.services import thingsboard
from app.services.batch_state import InvalidTransition, apply_status
from app.services.counters import load_events, summarize

router = APIRouter(prefix='/batches', tags=['batches'])


def queue_batch_telemetry(background_tasks, batch, session) -> None:
    """Dung payload ngay bay gio, roi gui o nen.

    Phai dung trong luc phien DB con song; tac vu nen chi nhan dict thuan.
    """
    if not thingsboard.is_enabled():
        return
    counters = summarize(load_events(session, batch.id))
    background_tasks.add_task(thingsboard.publish, thingsboard.build_batch_telemetry(batch, counters))


def get_batch_or_404(batch_id: int, session: Session) -> Batch:
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Không tìm thấy mẻ đếm')
    return batch


@router.get('', response_model=list[BatchRead], dependencies=[Depends(require_reader)])
def list_batches(session: Session = Depends(get_session)) -> list[Batch]:
    return list(session.scalars(select(Batch).order_by(Batch.id.desc())))


@router.post(
    '', response_model=BatchRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
)
def create_batch(payload: BatchCreate, session: Session = Depends(get_session)) -> Batch:
    if session.get(Target, payload.target_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Mẫu chuẩn không tồn tại')
    batch = Batch(**payload.model_dump())
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


@router.get('/{batch_id}', response_model=BatchDetail, dependencies=[Depends(require_reader)])
def get_batch(batch_id: int, session: Session = Depends(get_session)) -> dict:
    batch = get_batch_or_404(batch_id, session)
    return {
        **BatchRead.model_validate(batch).model_dump(),
        'counters': summarize(load_events(session, batch.id)),
    }


@router.patch(
    '/{batch_id}/status', response_model=BatchRead, dependencies=[Depends(require_operator)]
)
def update_status(
    batch_id: int,
    payload: BatchStatusUpdate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> Batch:
    batch = get_batch_or_404(batch_id, session)
    try:
        batch = apply_status(batch, payload.status, session)
    except InvalidTransition as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    # Gui sau khi da tra loi: dashboard cham mot nhip khong anh huong me dem.
    queue_batch_telemetry(background_tasks, batch, session)
    return batch
