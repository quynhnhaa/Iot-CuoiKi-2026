"""Them so khay (1-3) cho ket qua soi.

    cd web/backend
    .venv/Scripts/python migrations/002_add_tray_number.py

Cot cho phep NULL de giu nguyen lich su cu, khi thiet bi chua gui `tray_number`.
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
            columns = {row[1] for row in connection.execute(text('PRAGMA table_info(pill_events)'))}
        else:
            columns = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'pill_events'"
                    )
                )
            }
        if not columns:
            print('Chua co bang pill_events; khong can chuyen doi.')
            return 0
        if 'tray_number' in columns:
            print('tray_number da ton tai; khong lam gi them.')
            return 0
        connection.execute(text('ALTER TABLE pill_events ADD COLUMN tray_number INTEGER'))

    print('Xong: pill_events da co tray_number (1-3).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
