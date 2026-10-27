import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from common.paths import DatasetPaths
from common.image_audit import audit_image
from common.vaipe_schema import parse_vaipe_label, LabelValidationError

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ['image_path','label_path','group_id','image_id','width','height','box_count','labels','is_readable','validation_errors']


def build(root=ROOT, seed=20261025):
    paths = DatasetPaths.from_project_root(root)
    errors = paths.validate()
    if errors:
        raise RuntimeError('\n'.join(errors))
    images = sorted(p for p in paths.vaipe_images.iterdir() if p.suffix.lower() in ('.jpg','.jpeg','.png'))
    labels = {p.stem: p for p in paths.vaipe_labels.glob('*.json')}
    rows, distribution, issue_counts = [], Counter(), Counter()
    for image in images:
        match = re.fullmatch(r'VAIPE_P_(\d+)_(\d+)', image.stem)
        audit = audit_image(image)
        label = labels.get(image.stem)
        issues = []
        if not match: issues.append('invalid_image_id')
        if not audit.is_readable: issues.append('unreadable_image')
        elif audit.validation_errors: issues.append(audit.validation_errors)
        if label is None: issues.append('missing_label')
        boxes = []
        if label and audit.is_readable:
            try: boxes = parse_vaipe_label(label, audit.width, audit.height)
            except LabelValidationError as exc: issues.append(str(exc))
        for issue in issues:
            category = 'invalid_label' if issue.startswith(str(paths.vaipe_labels)) else issue.split(':')[0]
            issue_counts[category] += 1
        distribution.update(b.label for b in boxes)
        rows.append(dict(image_path=str(image.relative_to(root)),label_path=str(label.relative_to(root)) if label else '',group_id=match.group(1) if match else '',image_id=image.stem,width=audit.width,height=audit.height,box_count=len(boxes),labels=json.dumps([b.label for b in boxes]),is_readable=audit.is_readable,validation_errors=' | '.join(issues)))
    orphans = sorted(set(labels) - {p.stem for p in images})
    if orphans: issue_counts['orphan_labels'] = len(orphans)
    output = root / 'data/processed/vaipe/manifest.csv'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
    report_dir=root/'model/reports';report_dir.mkdir(exist_ok=True)
    report={'seed':seed,'source':'VAIPE public_train','image_count':len(images),'label_count':len(labels),'box_count':sum(distribution.values()),'class_count':len(distribution),'issue_counts':dict(issue_counts),'orphan_label_examples':orphans[:20],'problem_images':[r['image_id'] for r in rows if r['validation_errors']][:30]}
    (report_dir/'vaipe-data-audit.json').write_text(json.dumps(report,indent=2))
    with (report_dir/'vaipe-class-distribution.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['label','box_count']);w.writerows(sorted(distribution.items()))
    print(json.dumps({k:v for k,v in report.items() if k not in ('problem_images','orphan_label_examples')},indent=2))
    return 1 if issue_counts else 0

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seed',type=int,default=20261025)
    args=parser.parse_args();sys.exit(build(seed=args.seed))
