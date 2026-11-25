"""Tao bang snapshot ket qua AI theo khay.

    cd web/backend
    .venv/Scripts/python migrations/003_create_tray_results.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402


def main() -> int:
    with engine.begin() as connection:
        connection.execute(text('''
            CREATE TABLE IF NOT EXISTS tray_results (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER NOT NULL REFERENCES batches(id),
                tray_number INTEGER NOT NULL,
                counts_json TEXT NOT NULL,
                image_path VARCHAR(512),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT uq_tray_result_batch_tray UNIQUE (batch_id, tray_number)
            )
        '''))
    print('Xong: da co bang tray_results.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
