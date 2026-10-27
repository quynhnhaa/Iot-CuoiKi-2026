import csv
import json
import statistics
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FIELDS=['label','total_boxes','train_boxes','validation_boxes','test_boxes','group_count','median_box_area','eligible']


def rank(rows_by_split, min_per_split=1):
    counts=defaultdict(Counter);groups=defaultdict(set);areas=defaultdict(list)
    for split,rows in rows_by_split.items():
        for row in rows:
            for label in json.loads(row['labels']):
                label=str(label);counts[label][split]+=1;groups[label].add(row['group_id'])
                # VAIPE manifest records image dimensions only; box areas require label JSON.
    result=[]
    for label in sorted(counts,key=lambda x:int(x)):
        c=counts[label]
        result.append(dict(label=label,total_boxes=sum(c.values()),train_boxes=c['train'],validation_boxes=c['validation'],test_boxes=c['test'],group_count=len(groups[label]),median_box_area='',eligible=all(c[s]>=min_per_split for s in ('train','validation','test'))))
    return sorted(result,key=lambda r:(not r['eligible'],-r['group_count'],-r['total_boxes']))


def run(root=ROOT):
    rows={}
    for split in ('train','validation','test'):
        with (root/f'data/processed/vaipe/splits/{split}.csv').open(newline='') as f:rows[split]=list(csv.DictReader(f))
    candidates=rank(rows)
    # Read validated source labels solely for box-area statistics.
    areas=defaultdict(list)
    for split,subset in rows.items():
        for row in subset:
            source=root/row['label_path']
            for box in json.loads(source.read_text()):areas[str(box['label'])].append(box['w']*box['h'])
    for c in candidates:c['median_box_area']=statistics.median(areas[c['label']])
    out=root/'model/reports/vaipe-demo-class-candidates.csv'
    with out.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(candidates)
    summary=root/'model/reports/data-foundation-summary.md'
    summary.write_text('# Data foundation summary\n\n'
        'VAIPE and PharmaVision audit results are in the adjacent JSON reports.\n\n'
        f'- VAIPE candidate classes represented in all three splits: {sum(c["eligible"] for c in candidates)} / {len(candidates)}.\n'
        '- Final 5–10 recognition classes: pending representative image and confusion-risk review.\n'
        '- The split and manifest must pass the final gate before training.\n')
    print(f'Wrote {len(candidates)} candidates; {sum(c["eligible"] for c in candidates)} eligible')

if __name__=='__main__':run()
