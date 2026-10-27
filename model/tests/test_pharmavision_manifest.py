from scripts.build_pharmavision_manifest import FIELDS

def test_manifest_schema():
    assert {'image_path','split','label','sha256','is_readable'} <= set(FIELDS)
