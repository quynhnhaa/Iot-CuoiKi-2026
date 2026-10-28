"""Cho phep `batches.requested_count` de trong (me dem mo).

    cd web/backend
    .venv/Scripts/python migrations/001_requested_count_optional.py

SQLite khong bo duoc rang buoc NOT NULL bang ALTER TABLE, nen phai dung lai
bang: tao bang moi, chep du lieu sang, xoa bang cu, doi ten. Chi bang `batches`
bi dung lai; `users`, `targets` va `pill_events` khong bi dung toi, nen tai
khoan va ma TOTP van con nguyen.

Chay lai nhieu lan khong sao: script tu nhan ra schema da doi roi thi thoi.

Khi schema on dinh thi chuyen han sang Alembic; day la mot buoc le vi du an
con dang tao bang bang `Base.metadata.create_all`.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402

NEW_TABLE = """
CREATE TABLE batches_new (
    id INTEGER NOT NULL PRIMARY KEY,
    target_id INTEGER NOT NULL REFERENCES targets (id),
    requested_count INTEGER,
    status VARCHAR(16) NOT NULL,
    operator VARCHAR(128),
    note TEXT,
    created_at DATETIME NOT NULL,
    started_at DATETIME,
    finished_at DATETIME
)
"""

COPY = """
INSERT INTO batches_new (
    id, target_id, requested_count, status, operator, note,
    created_at, started_at, finished_at
)
SELECT id, target_id, requested_count, status, operator, note,
       created_at, started_at, finished_at
FROM batches
"""


def already_optional(connection) -> bool:
    for row in connection.execute(text('PRAGMA table_info(batches)')):
        if row[1] == 'requested_count':
            return not row[3]  # cot notnull
    raise SystemExit('Khong tim thay cot requested_count; CSDL khong nhu mong doi.')


def main() -> int:
    if engine.dialect.name != 'sqlite':
        print(
            'Script nay chi viet cho SQLite. Tren CSDL khac, dung ALTER TABLE'
            ' batches ALTER COLUMN requested_count DROP NOT NULL.',
            file=sys.stderr,
        )
        return 1

    with engine.begin() as connection:
        tables = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='batches'")
        ).first()
        if tables is None:
            print('Chua co bang batches; khong can chuyen doi.')
            return 0
        if already_optional(connection):
            print('requested_count da cho phep de trong; khong lam gi them.')
            return 0

        # Tat kiem tra khoa ngoai trong luc doi ten; pill_events tro toi
        # `batches` theo ten bang nen sau khi doi ten van tro dung.
        connection.execute(text('PRAGMA foreign_keys=OFF'))
        connection.execute(text(NEW_TABLE))
        connection.execute(text(COPY))
        connection.execute(text('DROP TABLE batches'))
        connection.execute(text('ALTER TABLE batches_new RENAME TO batches'))
        connection.execute(text('PRAGMA foreign_keys=ON'))

    print('Xong: requested_count gio co the de trong.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
