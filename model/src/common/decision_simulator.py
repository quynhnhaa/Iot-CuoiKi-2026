"""Pure decision simulator; never sends actuator commands.

`release_allowed` is a simulated eligibility flag. The default remains False
until identity validation and hardware readiness are explicitly supplied.
The accepted count changes only after an external drop sensor confirms routing.
"""
from dataclasses import dataclass
from typing import Literal

DefectStatus = Literal['normal', 'defective', 'uncertain']
Route = Literal['EMPTY_FRAME', 'MULTIPLE_PILLS', 'WRONG_DRUG', 'DEFECTIVE', 'ACCEPTED']


@dataclass(frozen=True)
class Observation:
    pill_count: int
    image_usable: bool
    identity_verified: bool
    target_matches: bool
    defect_status: DefectStatus
    identity_gate_validated: bool = False
    hardware_ready: bool = False


@dataclass(frozen=True)
class Decision:
    route: Route
    release_allowed: bool
    accepted_count_increment: int
    reason: str
    requires_drop_confirmation: bool = False


def decide(observation: Observation) -> Decision:
    """Route one observation conservatively without changing machine state."""
    if observation.pill_count < 0:
        raise ValueError('pill_count cannot be negative')
    if observation.defect_status not in ('normal', 'defective', 'uncertain'):
        raise ValueError('invalid defect_status')
    if observation.pill_count == 0:
        return Decision('EMPTY_FRAME', False, 0, 'no pill detected')
    if observation.pill_count > 1:
        return Decision('MULTIPLE_PILLS', False, 0, 'multiple pills detected')
    if not observation.image_usable:
        return Decision('WRONG_DRUG', False, 0, 'image is not reliable')
    if not observation.identity_verified:
        return Decision('WRONG_DRUG', False, 0, 'identity is uncertain')
    if not observation.target_matches:
        return Decision('WRONG_DRUG', False, 0, 'pill does not match selected target')
    if observation.defect_status == 'uncertain':
        return Decision('DEFECTIVE', False, 0, 'defect status is uncertain; hold for review')
    ready = observation.identity_gate_validated and observation.hardware_ready
    if observation.defect_status == 'defective':
        return Decision('DEFECTIVE', ready, 0,
                        'confirmed defective' if ready else 'routing not validated or hardware not ready')
    return Decision('ACCEPTED', ready, 0,
                    'normal pill; await drop sensor' if ready else 'routing not validated or hardware not ready',
                    requires_drop_confirmation=ready)

