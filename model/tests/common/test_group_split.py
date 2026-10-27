import json
from src.common.group_split import make_group_split

def test_no_leakage_and_repeatable():
    rows=[{'group_id':str(g),'labels':json.dumps([g%3])} for g in range(30) for _ in range(2)]
    a=make_group_split(rows,seed=9);b=make_group_split(rows,seed=9)
    assert a.assignments==b.assignments
    assert sum(a.counts.values())==len(rows)
    assert set(a.counts)=={'train','validation','test'}
