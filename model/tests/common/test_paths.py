from pathlib import Path
from src.common.paths import DatasetPaths

def test_required_paths(tmp_path):
    paths=DatasetPaths.from_project_root(tmp_path)
    assert len(paths.validate())>=4
    for p in (paths.vaipe_images,paths.vaipe_labels,paths.pharma_train,paths.pharma_test,paths.pharma_validation):p.mkdir(parents=True)
    assert paths.validate()==[]
