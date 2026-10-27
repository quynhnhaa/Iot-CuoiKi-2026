import json
from scripts.rank_demo_classes import rank

def test_missing_split_is_ineligible():
    rows={'train':[{'labels':json.dumps([1,2]),'group_id':'a'}], 'validation':[{'labels':json.dumps([1]),'group_id':'b'}], 'test':[{'labels':json.dumps([1]),'group_id':'c'}]}
    by_label={r['label']:r for r in rank(rows)}
    assert by_label['1']['eligible'] and not by_label['2']['eligible']
