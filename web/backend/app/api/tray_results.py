"""Nhan snapshot dem theo khay tu pipeline AI."""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.batches import get_batch_or_404
from app.api.deps import require_reader, require_recorder
from app.db import get_session
from app.models import BatchStatus, TrayResult
from app.schemas.tray_result import TrayResultIn, TrayResultRead

router = APIRouter(prefix='/batches/{batch_id}/tray-results', tags=['tray-results'])


def serialize(result: TrayResult) -> dict:
    return {
        'tray_number': result.tray_number,
        'counts': json.loads(result.counts_json),
        'image_path': result.image_path,
        'created_at': result.created_at,
        'updated_at': result.updated_at,
    }


@router.get('', response_model=list[TrayResultRead], dependencies=[Depends(require_reader)])
def list_tray_results(batch_id: int, session: Session = Depends(get_session)) -> list[dict]:
    get_batch_or_404(batch_id, session)
    results = session.scalars(
        select(TrayResult)
        .where(TrayResult.batch_id == batch_id)
        .order_by(TrayResult.tray_number)
    )
    return [serialize(result) for result in results]


@router.put(
    '/{tray_number}', response_model=TrayResultRead, dependencies=[Depends(require_recorder)]
)
def replace_tray_result(
    batch_id: int,
    tray_number: int,
    payload: TrayResultIn,
    session: Session = Depends(get_session),
) -> dict:
    """Luu toan bo ket qua moi nhat cua mot khay (1--3).

    PUT giup AI retry an toan: cung mot khay khong tao them dong va ket qua cu
    khong bi cong don vao giao dien.
    """
    if not 1 <= tray_number <= 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, 'So khay phai tu 1 den 3')
    batch = get_batch_or_404(batch_id, session)
    if BatchStatus(batch.status) is not BatchStatus.RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, 'Me dem khong o trang thai running')

    result = session.scalar(
        select(TrayResult).where(
            TrayResult.batch_id == batch_id, TrayResult.tray_number == tray_number
        )
    )
    counts_json = json.dumps([item.model_dump() for item in payload.counts], ensure_ascii=False)
    if result is None:
        result = TrayResult(
            batch_id=batch_id,
            tray_number=tray_number,
            counts_json=counts_json,
            image_path=payload.image_path,
        )
        session.add(result)
    else:
        result.counts_json = counts_json
        result.image_path = payload.image_path
    session.commit()
    session.refresh(result)
    return serialize(result)
