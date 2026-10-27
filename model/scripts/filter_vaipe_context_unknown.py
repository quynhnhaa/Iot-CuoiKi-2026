"""Create development-only identity-unknown manifests/features without VAIPE 107.

VAIPE class 107 is 'out of prescription' in a contextual task; it can contain
known pill appearances. Keep the historical files untouched for audit.
"""
import csv
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = ROOT / 'data/processed/vaipe/recognition/yolov7_unknown'
SOURCE_FEATURES = ROOT / 'model/runs/recognition/open_set_features_20261026'
OUT_CSV = ROOT / 'data/processed/vaipe/recognition/yolov7_unknown_identity'
OUT_FEATURES = ROOT / 'model/runs/recognition/open_set_identity_features_20261027'
CONTEXT_LABEL = 107


def main():
    OUT_CSV.mkdir(parents=True, exist_ok=True)
    OUT_FEATURES.mkdir(parents=True, exist_ok=True)
    summary = {'excluded_context_label': CONTEXT_LABEL, 'test_used': False,
               'source_manifest': str(SOURCE_CSV.relative_to(ROOT)), 'splits': {}}
    for split in ('train', 'validation'):
        source = SOURCE_CSV / f'{split}.csv'
        with source.open(newline='') as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames
            rows = list(reader)
        with np.load(SOURCE_FEATURES / f'{split}-unknown.npz') as handle:
            data = {key: handle[key].copy() for key in handle.files}
        if len(rows) != len(data['class_ids']):
            raise ValueError(f'{split}: manifest and feature length differ')
        for index, row in enumerate(rows):
            if int(row['class_id']) != int(data['class_ids'][index]) or \
                    row['image_id'] != data['image_ids'][index] or \
                    int(row['annotation_index']) != int(data['annotation_indices'][index]):
                raise ValueError(f'{split}: identity mismatch at {index}')
        keep = data['class_ids'] != CONTEXT_LABEL
        filtered = [row for row, allowed in zip(rows, keep) if allowed]
        target_csv = OUT_CSV / f'{split}.csv'
        temp_csv = target_csv.with_suffix('.tmp')
        with temp_csv.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fields)
            writer.writeheader(); writer.writerows(filtered)
        os.replace(temp_csv, target_csv)
        target_npz = OUT_FEATURES / f'{split}-unknown.npz'
        temp_npz = target_npz.with_suffix('.tmp')
        with temp_npz.open('wb') as handle:
            np.savez_compressed(handle, **{key: value[keep] for key, value in data.items()})
        os.replace(temp_npz, target_npz)
        summary['splits'][split] = {'input_roi': len(rows),
            'excluded_107_roi': int((~keep).sum()), 'identity_unknown_roi': int(keep.sum()),
            'identity_unknown_ids': sorted(set(map(int, data['class_ids'][keep])))}
        print(split, summary['splits'][split], flush=True)
    (OUT_CSV / 'report.json').write_text(json.dumps(summary, indent=2) + '\n')
    (OUT_FEATURES / 'manifest.json').write_text(json.dumps({**summary,
        'source_features': str(SOURCE_FEATURES.relative_to(ROOT))}, indent=2) + '\n')


if __name__ == '__main__':
    main()
