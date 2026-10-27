from dataclasses import dataclass
from pathlib import Path
import json


class LabelValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PillBox:
    x: int
    y: int
    w: int
    h: int
    label: int


def parse_vaipe_label(path: Path, image_width: int, image_height: int) -> list[PillBox]:
    try:
        payload = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabelValidationError(f'{path}: cannot read JSON: {exc}') from exc
    if not isinstance(payload, list):
        raise LabelValidationError(f'{path}: expected a list')
    boxes = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict) or any(k not in entry for k in ('x', 'y', 'w', 'h', 'label')):
            raise LabelValidationError(f'{path}: box {index}: missing fields')
        values = [entry[k] for k in ('x', 'y', 'w', 'h', 'label')]
        if any(type(v) is not int for v in values):
            raise LabelValidationError(f'{path}: box {index}: fields must be integers')
        box = PillBox(*values)
        if box.x < 0 or box.y < 0 or box.w <= 0 or box.h <= 0 or box.x + box.w > image_width or box.y + box.h > image_height or not 0 <= box.label <= 107:
            raise LabelValidationError(f'{path}: box {index}: invalid bounds or label: {box}')
        boxes.append(box)
    return boxes
