"""Them email lien he cho tai khoan nguoi dung.

    cd web/backend
    .venv/Scripts/python migrations/005_add_user_email.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402


def main() -> int:
    with engine.begin() as connection:
        if engine.dialect.name == 'sqlite':
            columns = {row[1] for row in connection.execute(text('PRAGMA table_info(users)'))}
        else:
            columns = {
                row[0] for row in connection.execute(text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"
                ))
            }
        if 'email' not in columns:
            connection.execute(text('ALTER TABLE users ADD COLUMN email VARCHAR(255)'))
    print('Xong: da them email cho tai khoan.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
