import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from common.decision_simulator import Observation, decide  # noqa: E402


def observation(**changes):
    values = {'pill_count': 1, 'image_usable': True, 'identity_verified': True,
              'target_matches': True, 'defect_status': 'normal',
              'identity_gate_validated': False, 'hardware_ready': False}
    values.update(changes)
    return Observation(**values)


@pytest.mark.parametrize('changes,route', [
    ({'pill_count': 0}, 'EMPTY_FRAME'),
    ({'pill_count': 2}, 'MULTIPLE_PILLS'),
    ({'image_usable': False}, 'WRONG_DRUG'),
    ({'identity_verified': False}, 'WRONG_DRUG'),
    ({'target_matches': False}, 'WRONG_DRUG'),
    ({'defect_status': 'uncertain'}, 'DEFECTIVE'),
    ({'defect_status': 'defective'}, 'DEFECTIVE'),
    ({}, 'ACCEPTED'),
])
def test_default_never_releases_or_counts(changes, route):
    result = decide(observation(**changes))
    assert result.route == route
    assert not result.release_allowed
    assert result.accepted_count_increment == 0


@pytest.mark.parametrize('changes,route', [
    ({'image_usable': False}, 'WRONG_DRUG'),
    ({'identity_verified': False}, 'WRONG_DRUG'),
    ({'target_matches': False}, 'WRONG_DRUG'),
    ({'defect_status': 'uncertain'}, 'DEFECTIVE'),
    ({'pill_count': 0}, 'EMPTY_FRAME'),
    ({'pill_count': 2}, 'MULTIPLE_PILLS'),
])
def test_uncertainty_holds_even_with_simulated_readiness(changes, route):
    result = decide(observation(identity_gate_validated=True, hardware_ready=True, **changes))
    assert result.route == route
    assert not result.release_allowed
    assert result.accepted_count_increment == 0


def test_only_confident_route_can_become_eligible_and_count_waits_for_sensor():
    accepted = decide(observation(identity_gate_validated=True, hardware_ready=True))
    defective = decide(observation(identity_gate_validated=True, hardware_ready=True,
                                   defect_status='defective'))
    assert accepted.route == 'ACCEPTED' and accepted.release_allowed
    assert accepted.requires_drop_confirmation and accepted.accepted_count_increment == 0
    assert defective.route == 'DEFECTIVE' and defective.release_allowed
    assert defective.accepted_count_increment == 0


def test_invalid_values_fail_closed():
    with pytest.raises(ValueError):
        decide(observation(pill_count=-1))
    with pytest.raises(ValueError):
        decide(observation(defect_status='other'))

