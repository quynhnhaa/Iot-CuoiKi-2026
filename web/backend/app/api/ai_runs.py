from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import require_reader

from app.services import ai_runs as service

router = APIRouter(prefix='/ai-runs', tags=['ai-runs'], dependencies=[Depends(require_reader)])


@router.get('')
def list_runs() -> list[dict]:
    """Cac lan chay pipeline AI tim thay trong model/runs/pipeline tren may nay."""
    return service.list_runs()


@router.get('/{name}/events')
def run_events(name: str, limit: int = Query(200, ge=1, le=5000)) -> list[dict]:
    events = service.read_run_events(name, limit=limit)
    if not events:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Khong tim thay events.jsonl cho run nay')
    return events
