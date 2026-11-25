from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.batches import get_batch_or_404, queue_batch_telemetry
from app.api.deps import require_reader, require_recorder
from app.db import get_session
from app.models import BatchStatus, PillEvent
from app.schemas.pill_event import DropConfirmation, PillEventRead, PillObservationIn
from app.services.decision import DecisionSimulatorUnavailable, decide

router = APIRouter(prefix='/batches/{batch_id}/events', tags=['pill-events'])


@router.get('', response_model=list[PillEventRead], dependencies=[Depends(require_reader)])
def list_events(batch_id: int, session: Session = Depends(get_session)) -> list[PillEvent]:
    return list(get_batch_or_404(batch_id, session).events)


@router.post(
    '', response_model=PillEventRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recorder)],
)
def create_event(
    batch_id: int,
    payload: PillObservationIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> PillEvent:
    """Ghi mot quan sat; quyet dinh do decision_simulator cua nhanh AI tra ve."""
    batch = get_batch_or_404(batch_id, session)
    if BatchStatus(batch.status) is not BatchStatus.RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, 'Mẻ đếm không ở trạng thái running')

    observation = payload.model_dump(exclude={'image_path'})
    try:
        decision = decide(**observation)
    except DecisionSimulatorUnavailable as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

    event = PillEvent(
        batch_id=batch.id,
        sequence=len(batch.events) + 1,
        image_path=payload.image_path,
        route=decision['route'],
        release_allowed=decision['release_allowed'],
        requires_drop_confirmation=decision['requires_drop_confirmation'],
        reason=decision['reason'],
        **observation,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    queue_batch_telemetry(background_tasks, batch, session)
    return event


@router.patch(
    '/{event_id}/drop', response_model=PillEventRead, dependencies=[Depends(require_recorder)]
)
def confirm_drop(
    batch_id: int,
    event_id: int,
    payload: DropConfirmation,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> PillEvent:
    """Cam bien duong roi xac nhan vien da roi; chi khi do bo dem moi tang."""
    event = session.get(PillEvent, event_id)
    if event is None or event.batch_id != batch_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Không tìm thấy sự kiện')
    if payload.drop_confirmed and not event.release_allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            'Sự kiện này chưa được phép thả viên, không thể xác nhận đã rơi',
        )
    event.drop_confirmed = payload.drop_confirmed
    session.commit()
    session.refresh(event)
    # Bo dem vua doi, nen dashboard can so moi.
    queue_batch_telemetry(background_tasks, event.batch, session)
    return event
