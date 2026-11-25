import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_reader
from app.db import get_session
from app.config import get_settings
from app.models import Role, Target, TargetImage, User
from app.schemas.target import TargetCreate, TargetRead
from app.services.training_notifications import TrainingEmailUnavailable, request_retraining

router = APIRouter(prefix='/targets', tags=['targets'])

IMAGE_TYPES = {
    'image/jpeg': ('.jpg', b'\xff\xd8\xff'),
    'image/png': ('.png', b'\x89PNG\r\n\x1a\n'),
    'image/webp': ('.webp', b'RIFF'),
}


def validate_image(upload: UploadFile, content: bytes) -> str:
    content_type = upload.content_type or ''
    specification = IMAGE_TYPES.get(content_type)
    if specification is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, 'Chi nhan anh JPG, PNG hoac WebP')
    extension, signature = specification
    if not content.startswith(signature) or (content_type == 'image/webp' and content[8:12] != b'WEBP'):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, 'Noi dung tep khong dung dinh dang anh da khai bao')
    return extension


@router.get('', response_model=list[TargetRead], dependencies=[Depends(require_reader)])
def list_targets(session: Session = Depends(get_session)) -> list[Target]:
    return list(session.scalars(select(Target).order_by(Target.id)))


@router.post(
    '', response_model=TargetRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_target(payload: TargetCreate, session: Session = Depends(get_session)) -> Target:
    target = Target(**payload.model_dump())
    session.add(target)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f'Mã mẫu chuẩn "{payload.code}" đã tồn tại') from None
    session.refresh(target)
    return target


@router.post(
    '/with-images', response_model=TargetRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_target_with_images(
    code: str = Form(),
    name: str = Form(),
    recognition_label: str | None = Form(default=None),
    note: str | None = Form(default=None),
    images: list[UploadFile] = File(),
    session: Session = Depends(get_session),
) -> Target:
    """Tao mau va luu nhieu anh mau trong mot request nguyen tu."""
    settings = get_settings()
    if len(images) < settings.min_target_images:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f'Can dinh kem it nhat {settings.min_target_images} anh mau de train lai',
        )
    if len(images) > 50:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, 'Chi nhan toi da 50 anh moi lan')

    prepared: list[tuple[UploadFile, bytes, str]] = []
    for image in images:
        content = await image.read(settings.max_target_image_bytes + 1)
        if len(content) > settings.max_target_image_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, 'Moi anh toi da 10 MB')
        prepared.append((image, content, validate_image(image, content)))

    target = Target(code=code, name=name, recognition_label=recognition_label, note=note)
    session.add(target)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f'Ma mau chuan "{code}" da ton tai') from None

    directory = settings.target_images_dir / str(target.id)
    try:
        directory.mkdir(parents=True, exist_ok=False)
        for image, content, extension in prepared:
            stored_name = f'{uuid4().hex}{extension}'
            (directory / stored_name).write_bytes(content)
            session.add(TargetImage(
                target_id=target.id,
                stored_name=stored_name,
                original_name=Path(image.filename or 'anh-mau').name[:255],
                content_type=image.content_type or '',
            ))
        session.commit()
    except Exception:
        session.rollback()
        shutil.rmtree(directory, ignore_errors=True)
        raise
    session.refresh(target)
    return target


@router.post('/train-request', dependencies=[Depends(require_admin)])
def send_train_request(session: Session = Depends(get_session)) -> dict:
    """Gui email yeu cau train lai toan bo du lieu, khong tu dong chay model."""
    target_count = session.scalar(select(func.count(Target.id))) or 0
    image_count = session.scalar(select(func.count(TargetImage.id))) or 0
    recipients = list(session.scalars(
        select(User.email).where(User.role == Role.ADMIN, User.is_active.is_(True), User.email.is_not(None))
    ))
    minimum = get_settings().min_target_images
    if image_count < minimum:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f'Can co it nhat {minimum} anh mau truoc khi yeu cau train lai',
        )
    try:
        request_retraining(target_count=target_count, image_count=image_count, recipients=recipients)
    except TrainingEmailUnavailable as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    except OSError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f'Khong gui duoc email: {error}') from error
    return {'message': 'Da gui email yeu cau train lai toan bo du lieu cho nguoi quan ly'}


@router.get('/{target_id}', response_model=TargetRead, dependencies=[Depends(require_reader)])
def get_target(target_id: int, session: Session = Depends(get_session)) -> Target:
    target = session.get(Target, target_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Không tìm thấy mẫu chuẩn')
    return target
