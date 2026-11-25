"""Tao bang metadata anh mau dung cho train lai.

    cd web/backend
    .venv/Scripts/python migrations/004_create_target_images.py
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
            CREATE TABLE IF NOT EXISTS target_images (
                id INTEGER PRIMARY KEY,
                target_id INTEGER NOT NULL REFERENCES targets(id),
                stored_name VARCHAR(128) NOT NULL UNIQUE,
                original_name VARCHAR(255) NOT NULL,
                content_type VARCHAR(64) NOT NULL,
                created_at DATETIME NOT NULL
            )
        '''))
    print('Xong: da co bang target_images.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
