"""Tao tai khoan admin dau tien.

Chay mot lan khi dung he thong:

    cd web/backend
    .venv/Scripts/python scripts/create_admin.py --username admin

Mat khau duoc nhap an tren terminal, khong truyen qua tham so dong lenh de
khong luu vao history cua shell. Tai khoan tao ra chua bat 2FA; lan dang nhap
dau tien se buoc ghi danh TOTP truoc khi vao duoc API nao khac.
"""
import argparse
import getpass
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base, Role, User  # noqa: E402

MIN_PASSWORD_LENGTH = 12


def main() -> int:
    parser = argparse.ArgumentParser(description='Tao tai khoan admin dau tien')
    parser.add_argument('--username', required=True)
    parser.add_argument('--full-name', default=None)
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        if session.scalar(select(User).where(User.username == args.username)):
            print(f'Ten dang nhap "{args.username}" da ton tai.', file=sys.stderr)
            return 1

        password = getpass.getpass('Mat khau: ')
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f'Mat khau phai tu {MIN_PASSWORD_LENGTH} ky tu.', file=sys.stderr)
            return 1
        if password != getpass.getpass('Nhap lai mat khau: '):
            print('Hai lan nhap khong khop.', file=sys.stderr)
            return 1

        session.add(
            User(
                username=args.username,
                full_name=args.full_name,
                role=Role.ADMIN,
                password_hash=hash_password(password),
            )
        )
        session.commit()
    finally:
        session.close()

    print(f'Da tao admin "{args.username}".')
    print('Lan dang nhap dau tien se yeu cau ghi danh xac thuc hai lop.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
