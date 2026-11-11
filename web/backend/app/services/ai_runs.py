"""Doc ket qua cac lan chay pipeline AI tu model/runs/pipeline (chi doc)."""
import json
from pathlib import Path

from app.config import get_settings


def _read_json(path: Path) -> dict | None:
    try:
        with path.open(encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def list_runs() -> list[dict]:
    """Liet ke cac run co summary.json. Thu muc nay nam trong .gitignore."""
    runs_dir = get_settings().pipeline_runs_dir
    if not runs_dir.is_dir():
        return []
    runs = []
    for entry in sorted(runs_dir.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        runs.append(
            {
                'name': entry.name,
                'summary': _read_json(entry / 'summary.json'),
                'manifest': _read_json(entry / 'run-manifest.json'),
                'has_events': (entry / 'events.jsonl').is_file(),
            }
        )
    return runs


def read_run_events(name: str, limit: int = 200) -> list[dict]:
    """Doc events.jsonl cua mot run. Ten run duoc chot theo danh sach thuc te."""
    runs_dir = get_settings().pipeline_runs_dir
    allowed = {entry.name for entry in runs_dir.iterdir() if entry.is_dir()} if runs_dir.is_dir() else set()
    if name not in allowed:
        return []
    events_path = runs_dir / name / 'events.jsonl'
    if not events_path.is_file():
        return []
    events = []
    with events_path.open(encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(events) >= limit:
                break
    return events
