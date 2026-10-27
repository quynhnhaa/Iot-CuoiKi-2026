import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common.group_split import make_group_split
ROOT=Path(__file__).resolve().parents[2]


def run(seed=20261025, ratios=(.7,.15,.15), root=ROOT, exclude_invalid=False):
    source=root/'data/processed/vaipe/manifest.csv'
    with source.open(newline='') as f: rows=list(csv.DictReader(f))
    invalid=[r for r in rows if r['validation_errors'] or r['is_readable']!='True']
    if invalid and not exclude_invalid:
        raise RuntimeError(f'VAIPE manifest has {len(invalid)} invalid images; split stopped. Use --exclude-invalid only after review.')
    if exclude_invalid:
        exclusion_path=root/'data/processed/vaipe/excluded-invalid-pairs.csv'
        with exclusion_path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['image_path','label_path','image_id','validation_errors']);w.writeheader()
            w.writerows({k:r[k] for k in w.fieldnames} for r in invalid)
        rows=[r for r in rows if not r['validation_errors'] and r['is_readable']=='True']
    result=make_group_split(rows,ratios,seed)
    out=root/'data/processed/vaipe/splits';out.mkdir(parents=True,exist_ok=True)
    report={'seed':seed,'ratios':dict(zip(('train','validation','test'),ratios)),'excluded_invalid_pairs':[{'image_path':r['image_path'],'label_path':r['label_path']} for r in invalid] if exclude_invalid else [],'splits':{}}
    for name in ('train','validation','test'):
        subset=[r for r in rows if result.assignments[r['group_id']]==name]
        with (out/f'{name}.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(subset)
        labels=Counter()
        for r in subset: labels.update(json.loads(r['labels']))
        report['splits'][name]={'images':len(subset),'groups':len({r['group_id'] for r in subset}),'boxes':sum(labels.values()),'classes':dict(sorted(labels.items(),key=lambda x:int(x[0])))}
    group_locations={}
    for name in ('train','validation','test'):
        for row in rows:
            if result.assignments[row['group_id']]==name:
                group_locations.setdefault(row['group_id'],set()).add(name)
    report['group_leakage']=any(len(locations)>1 for locations in group_locations.values())
    (root/'model/reports/vaipe-split-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:{j:v for j,v in data.items() if j!='classes'} for k,data in report['splits'].items()},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=20261025);p.add_argument('--train',type=float,default=.7);p.add_argument('--validation',type=float,default=.15);p.add_argument('--test',type=float,default=.15)
    p.add_argument('--exclude-invalid',action='store_true',help='Explicitly exclude invalid images listed in audit; never changes source data')
    a=p.parse_args();run(a.seed,(a.train,a.validation,a.test),exclude_invalid=a.exclude_invalid)
