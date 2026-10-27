import pytest
from scripts.export_yolov7_detection import convert_box


def test_converts_xywh_to_normalized_single_class():
    assert convert_box({'x':10,'y':20,'w':20,'h':40,'label':99},100,200) == '0 0.20000000 0.20000000 0.20000000 0.20000000'


def test_rejects_out_of_bounds_box():
    with pytest.raises(ValueError):
        convert_box({'x':90,'y':20,'w':20,'h':40,'label':1},100,200)
