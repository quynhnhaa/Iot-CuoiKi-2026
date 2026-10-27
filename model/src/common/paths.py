from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetPaths:
    root: Path
    vaipe_images: Path
    vaipe_labels: Path
    pharma_train: Path
    pharma_test: Path
    pharma_validation: Path

    @classmethod
    def from_project_root(cls, root: Path) -> 'DatasetPaths':
        root = Path(root).resolve()
        base = root / 'data/external'
        pill = base / 'vaipepill2022/public_train/pill'
        pharma = base / 'pharmavision'
        return cls(root, pill / 'image', pill / 'label', pharma / 'train', pharma / 'test', pharma / 'validation')

    def validate(self) -> list[str]:
        return [f'Missing directory: {path}' for path in (self.vaipe_images, self.vaipe_labels, self.pharma_train, self.pharma_test, self.pharma_validation) if not path.is_dir()]
