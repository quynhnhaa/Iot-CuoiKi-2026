from PIL import Image
from src.common.image_audit import audit_image

def test_readable_and_corrupt(tmp_path):
    good=tmp_path/'good.png';Image.new('RGB',(10,20)).save(good)
    assert audit_image(good).is_readable and audit_image(good).width==10
    bad=tmp_path/'bad.png';bad.write_bytes(b'broken')
    assert not audit_image(bad).is_readable

def test_exif_orientation_dimensions(tmp_path):
    image=Image.new('RGB',(20,10))
    exif=image.getexif();exif[274]=6
    path=tmp_path/'rotated.jpg';image.save(path,exif=exif)
    result=audit_image(path)
    assert (result.width,result.height)==(10,20)
