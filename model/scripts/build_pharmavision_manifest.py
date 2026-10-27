import csv
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common.image_audit import audit_image
ROOT=Path(__file__).resolve().parents[2]
FIELDS=['image_path','split','label','width','height','is_readable','sha256']


def run(root=ROOT):
    base=root/'data/external/pharmavision';rows=[];errors=[];hashes=defaultdict(list)
    for split in ('train','validation','test'):
        for label in ('normal','defective'):
            folder=base/split/label
            if not folder.is_dir(): errors.append(f'missing directory: {folder}');continue
            for path in sorted(folder.iterdir()):
                if path.suffix.lower() not in ('.jpg','.jpeg','.png'):continue
                audit=audit_image(path)
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                hashes[digest].append(str(path.relative_to(root)))
                rows.append(dict(image_path=str(path.relative_to(root)),split=split,label=label,width=audit.width,height=audit.height,is_readable=audit.is_readable,sha256=digest))
                if not audit.is_readable or audit.validation_errors: errors.append(f'{path}: {audit.validation_errors}')
    duplicates=[paths for paths in hashes.values() if len(paths)>1]
    counts={s:dict(Counter(r['label'] for r in rows if r['split']==s)) for s in ('train','validation','test')}
    output=root/'data/processed/pharmavision/manifest.csv';output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    report={'image_count':len(rows),'split_class_counts':counts,'duplicate_sha256_groups':duplicates,'errors':errors}
    (root/'model/reports/pharmavision-data-audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'image_count':len(rows),'split_class_counts':counts,'duplicate_group_count':len(duplicates),'error_count':len(errors)},indent=2))
    return 1 if errors or duplicates else 0

if __name__=='__main__':sys.exit(run())
