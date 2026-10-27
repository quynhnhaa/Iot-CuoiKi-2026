import json
import pytest
from src.common.vaipe_schema import parse_vaipe_label,LabelValidationError,PillBox

@pytest.mark.parametrize('value',[[{'x':1,'y':2,'w':3,'h':4,'label':0}],[{'x':1,'y':2,'w':3,'h':4,'label':107}]])
def test_valid(tmp_path,value):
    p=tmp_path/'a.json';p.write_text(json.dumps(value))
    assert len(parse_vaipe_label(p,10,10))==1

@pytest.mark.parametrize('value',[[{'x':1,'y':2,'w':3,'h':4}],[{'x':9,'y':2,'w':3,'h':4,'label':1}],[{'x':0,'y':0,'w':1,'h':1,'label':108}]])
def test_invalid(tmp_path,value):
    p=tmp_path/'a.json';p.write_text(json.dumps(value))
    with pytest.raises(LabelValidationError):parse_vaipe_label(p,10,10)
