"""Nap logic quyet dinh tu nhanh AI thay vi viet lai.

Logic ba nhan nam o model/src/common/decision_simulator.py va da co kiem thu
ben do. Viet lai o backend se tao ban thu hai co the lech nhau, nen o day chi
nap dung file goc theo duong dan va goi `decide`.
"""
import importlib.util
import sys
from functools import lru_cache
from types import ModuleType

from app.config import get_settings


class DecisionSimulatorUnavailable(RuntimeError):
    """Khong tim thay decision_simulator cua nhanh AI."""


@lru_cache
def load_decision_simulator() -> ModuleType:
    path = get_settings().decision_simulator_path
    if not path.is_file():
        raise DecisionSimulatorUnavailable(
            f'Khong tim thay {path}. Kiem tra bien moi truong WEB_MODEL_DIR.'
        )
    spec = importlib.util.spec_from_file_location('ai_decision_simulator', path)
    if spec is None or spec.loader is None:
        raise DecisionSimulatorUnavailable(f'Khong nap duoc module tu {path}.')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def decide(
    *,
    pill_count: int,
    image_usable: bool,
    identity_verified: bool,
    target_matches: bool,
    defect_status: str,
    identity_gate_validated: bool = False,
    hardware_ready: bool = False,
) -> dict:
    """Tra ve quyet dinh dang dict de luu va tra ra API."""
    simulator = load_decision_simulator()
    observation = simulator.Observation(
        pill_count=pill_count,
        image_usable=image_usable,
        identity_verified=identity_verified,
        target_matches=target_matches,
        defect_status=defect_status,
        identity_gate_validated=identity_gate_validated,
        hardware_ready=hardware_ready,
    )
    decision = simulator.decide(observation)
    return {
        'route': decision.route,
        'release_allowed': decision.release_allowed,
        'accepted_count_increment': decision.accepted_count_increment,
        'reason': decision.reason,
        'requires_drop_confirmation': decision.requires_drop_confirmation,
    }
