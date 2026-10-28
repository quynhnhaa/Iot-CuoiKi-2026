"""Nap du lieu mau de xem giao dien khi da co du lieu.

    cd web/backend
    .venv/Scripts/python scripts/seed_demo.py          # them vao du lieu dang co
    .venv/Scripts/python scripts/seed_demo.py --reset  # xoa me/mau chuan cu truoc

Day **khong phai** du lieu that: nhan va ma mau chuan chi de xem giao dien.
Nhung quyet dinh tung vien thi khong bia: moi quan sat deu di qua dung
`decision_simulator.decide()` ben nhanh AI, nen nhan va ly do hien ra giong
het luc may chay that. Neu logic ba nhan doi, du lieu mau doi theo.

Mac dinh script khong cham vao tai khoan nao. Co `--with-demo-account` thi tao
them mot tai khoan van hanh de xem giao dien tren may dev: mat khau sinh ngau
nhien va in ra mot lan. **Khong dung co nay tren may chay that** — do la mot
tai khoan co quyen ghi ket qua dem.
"""
import argparse
import random
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base, Batch, BatchStatus, PillEvent, Role, Target, User  # noqa: E402
from app.services.decision import DecisionSimulatorUnavailable, decide  # noqa: E402

# Mau chuan mau. `recognition_label` la ID nhan anh cua nhanh AI, khong phai
# hoat chat thuoc that.
TARGETS = [
    {
        'code': 'MC-064',
        'name': 'Viên tròn trắng, vạch giữa',
        'recognition_label': '64',
        'note': 'Mẫu chuẩn dùng cho phần lớn mẻ demo.',
    },
    {
        'code': 'MC-091',
        'name': 'Viên nang hai màu',
        'recognition_label': '91',
        'note': 'Để thử trường hợp sai thuốc: rất dễ lẫn với MC-064.',
    },
    {
        'code': 'MC-107',
        'name': 'Viên bao phim hồng',
        'recognition_label': '107',
        'note': None,
    },
]

# Cac dang quan sat. Ten o day la mo ta cho nguoi doc script; nhan thuc su do
# decision_simulator quyet dinh.
GOOD = {
    'pill_count': 1,
    'image_usable': True,
    'identity_verified': True,
    'target_matches': True,
    'defect_status': 'normal',
    'identity_gate_validated': True,
    'hardware_ready': True,
}
CHIPPED = {**GOOD, 'defect_status': 'defective'}
WRONG_PILL = {**GOOD, 'target_matches': False}
TWO_PILLS = {**GOOD, 'pill_count': 2}
EMPTY = {**GOOD, 'pill_count': 0}
BLURRY = {**GOOD, 'image_usable': False}
UNSURE = {**GOOD, 'defect_status': 'uncertain'}


def pattern(total: int, specials: dict[int, dict]) -> list[dict]:
    """`total` lan soi, mac dinh la vien dat; `specials` ghi de theo chi so."""
    return [dict(specials.get(index, GOOD)) for index in range(total)]


# Moi me ke mot tinh huong van hanh khac nhau, de xem giao dien o du cac trang
# thai chu khong chi mot trang thai dep.
SCENARIOS = [
    {
        'target': 'MC-064',
        'status': BatchStatus.RUNNING,
        'operator': 'Thu Hà',
        'note': 'Mẻ đang chạy — viên vừa soi chưa có tín hiệu cảm biến rơi.',
        'started_minutes_ago': 12,
        'observations': pattern(
            19, {4: CHIPPED, 9: TWO_PILLS, 13: EMPTY, 16: CHIPPED}
        ),
        # Vien cuoi da duoc phep tha nhung cam bien chua bao: day la luc hai bo
        # dem lech nhau 1, va do la binh thuong.
        'leave_last_unconfirmed': True,
    },
    {
        'target': 'MC-064',
        'status': BatchStatus.DONE,
        'operator': 'Thu Hà',
        'note': 'Mẻ kết thúc bình thường khi người vận hành bấm xong.',
        'started_minutes_ago': 180,
        'finished_minutes_ago': 148,
        # 25 lan soi, 5 lan khong ra vien dat => 20 vien dat.
        'observations': pattern(
            25, {3: CHIPPED, 7: BLURRY, 11: CHIPPED, 15: UNSURE, 20: EMPTY}
        ),
    },
    {
        'target': 'MC-091',
        'status': BatchStatus.PAUSED,
        'operator': 'Minh Quân',
        'note': 'Tạm dừng: ba viên sai thuốc liên tiếp, cần kiểm tra lại khay nạp.',
        'started_minutes_ago': 46,
        'observations': pattern(11, {7: WRONG_PILL, 8: WRONG_PILL, 9: WRONG_PILL}),
    },
    {
        'target': 'MC-107',
        'status': BatchStatus.ABORTED,
        'operator': 'Minh Quân',
        'note': 'Huỷ mẻ: ảnh mờ liên tục, nghi ống kính bị mờ sương.',
        'started_minutes_ago': 320,
        'finished_minutes_ago': 311,
        'observations': pattern(6, {2: BLURRY, 3: BLURRY, 4: BLURRY, 5: BLURRY}),
    },
    {
        'target': 'MC-107',
        'status': BatchStatus.PENDING,
        'operator': None,
        'note': 'Mẻ vừa tạo, chưa bấm bắt đầu.',
        'observations': [],
    },
]


DEMO_USERNAME = 'demo-vanhanh'


def ensure_demo_account(session) -> None:
    """Tai khoan van hanh de xem giao dien. Chua bat 2FA: lan dang nhap dau
    tien se buoc ghi danh TOTP, giong moi tai khoan khac."""
    if session.scalar(select(User).where(User.username == DEMO_USERNAME)):
        print(f'Tai khoan "{DEMO_USERNAME}" da ton tai; khong doi mat khau.')
        return
    password = secrets.token_urlsafe(12)
    session.add(
        User(
            username=DEMO_USERNAME,
            full_name='Người vận hành (demo)',
            role=Role.OPERATOR,
            password_hash=hash_password(password),
            note='Tài khoản xem giao diện. Xoá trước khi chạy thật.',
        )
    )
    session.commit()
    print(f'Da tao tai khoan demo: {DEMO_USERNAME} / {password}')
    print('Mat khau nay chi in mot lan. Lan dang nhap dau se yeu cau ghi danh TOTP.')


def reset(session) -> None:
    """Xoa me, su kien va mau chuan. Khong cham vao tai khoan."""
    session.execute(delete(PillEvent))
    session.execute(delete(Batch))
    session.execute(delete(Target))
    session.commit()


def seed(session, rng: random.Random) -> None:
    now = datetime.now(timezone.utc)

    targets: dict[str, Target] = {}
    for spec in TARGETS:
        existing = session.scalar(select(Target).where(Target.code == spec['code']))
        if existing is None:
            existing = Target(**spec)
            session.add(existing)
        targets[spec['code']] = existing
    session.commit()

    for scenario in SCENARIOS:
        started = (
            now - timedelta(minutes=scenario['started_minutes_ago'])
            if 'started_minutes_ago' in scenario
            else None
        )
        finished = (
            now - timedelta(minutes=scenario['finished_minutes_ago'])
            if 'finished_minutes_ago' in scenario
            else None
        )
        created = (started or now) - timedelta(minutes=rng.randint(1, 4))

        batch = Batch(
            target_id=targets[scenario['target']].id,
            status=scenario['status'],
            operator=scenario['operator'],
            note=scenario['note'],
            created_at=created,
            started_at=started,
            finished_at=finished,
        )
        session.add(batch)
        session.flush()

        observations = scenario['observations']
        leave_last = scenario.get('leave_last_unconfirmed', False)
        at = started or now
        for index, observation in enumerate(observations, start=1):
            decision = decide(**observation)
            # May soi moi vien cach nhau vai giay; con so chi de truc thoi gian
            # tren giao dien doc duoc.
            at = at + timedelta(seconds=rng.randint(6, 20))
            is_last = index == len(observations)
            # Thiet bi se ghi duong dan anh soi; web chua nhan anh nen day chi
            # la mot duong dan tuong trung tren vai vien dau.
            image_path = f'runs/pipeline/me-{batch.id}/vien-{index:03d}.jpg' if index <= 3 else None
            session.add(
                PillEvent(
                    batch_id=batch.id,
                    sequence=index,
                    route=decision['route'],
                    release_allowed=decision['release_allowed'],
                    requires_drop_confirmation=decision['requires_drop_confirmation'],
                    reason=decision['reason'],
                    # Cam bien chi xac nhan nhung vien da duoc phep tha.
                    drop_confirmed=(
                        decision['release_allowed'] and not (leave_last and is_last)
                    ),
                    created_at=at,
                    image_path=image_path,
                    **observation,
                )
            )
        session.commit()
        print(
            f'Me #{batch.id} [{scenario["status"].value}] {scenario["target"]}'
            f' — {len(observations)} lan soi'
        )


def main() -> int:
    parser = argparse.ArgumentParser(description='Nap du lieu mau cho giao dien')
    parser.add_argument(
        '--reset', action='store_true', help='Xoa me/su kien/mau chuan cu truoc khi nap'
    )
    parser.add_argument(
        '--with-demo-account',
        action='store_true',
        help='Tao them tai khoan van hanh de xem giao dien (chi dung tren may dev)',
    )
    parser.add_argument('--seed', type=int, default=20261028, help='Hat ngau nhien cho moc thoi gian')
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        if args.reset:
            reset(session)
            print('Da xoa du lieu me cu.')
        if args.with_demo_account:
            ensure_demo_account(session)
        try:
            seed(session, random.Random(args.seed))
        except DecisionSimulatorUnavailable as error:
            # Khong bia nhan thay the: thieu nhanh AI thi dung han.
            print(f'Khong nap duoc: {error}', file=sys.stderr)
            return 1
    finally:
        session.close()

    print('Xong. Mo trang "Me dem" tren web de xem.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
