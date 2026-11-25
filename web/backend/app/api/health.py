from fastapi import APIRouter

from app.config import get_settings
from app.services.decision import DecisionSimulatorUnavailable, load_decision_simulator

router = APIRouter(tags=['health'])


@router.get('/health')
def health() -> dict:
    settings = get_settings()
    try:
        load_decision_simulator()
        decision_logic = 'ok'
    except DecisionSimulatorUnavailable as error:
        decision_logic = str(error)
    return {
        'status': 'ok',
        'app_name': settings.app_name,
        'decision_logic': decision_logic,
        'pipeline_runs_dir_exists': settings.pipeline_runs_dir.is_dir(),
    }
