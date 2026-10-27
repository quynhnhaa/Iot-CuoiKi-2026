from dataclasses import dataclass
from pathlib import Path
from PIL import Image, UnidentifiedImageError


@dataclass(frozen=True)
class ImageAuditResult:
    width: int
    height: int
    is_readable: bool
    validation_errors: str


def audit_image(path: Path) -> ImageAuditResult:
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            if image.getexif().get(274, 1) in (5, 6, 7, 8):
                width, height = height, width
            if image.mode != 'RGB':
                return ImageAuditResult(width, height, True, f'non-RGB mode: {image.mode}')
            return ImageAuditResult(width, height, True, '')
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        return ImageAuditResult(0, 0, False, str(exc))
