"""Fixed score fusion of original and multilayer verifier; no test access."""
import json
from pathlib import Path

import numpy as np
import torch

import train_recognition_verifier as v
from benchmark_recognition_open_set import temperature
from evaluate_recognition_unseen_ids import load, subset, unknown_id_split

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'model/runs/recognition'
OUT = RUNS / 'score_fusion_20261027'


def scores(feature_dir, run, device, km):
    known, unknown = load(feature_dir, 'validation-known'), load(feature_dir, 'validation-unknown')
    saved = torch.load(RUNS / run / 'best.pt', map_location='cpu', weights_only=False)
    model = v.Verifier(known['features'].shape[1]).to(device)
    model.load_state_dict(saved['model']); model.eval()
    temp = temperature(known['logits'][km], known['class_ids'][km])
    return known, unknown, v.predict(model, known, device, temp), \
        v.predict(model, unknown, device, temp)


def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    km = v.grouped_mask('validation', 'known', 0)
    a = scores(RUNS / 'open_set_features_20261026',
        'class_conditioned_verifier_20261027', device, km)
    b = scores(RUNS / 'pim_multilayer_features_20261027',
        'class_conditioned_verifier_multilayer_20261027', device, km)
    c = scores(RUNS / 'pim_spatial_features_20261027',
        'class_conditioned_verifier_spatial_20261027', device, km)
    known, unknown = a[:2]
    if not np.array_equal(known['image_ids'], b[0]['image_ids']) or \
            not np.array_equal(unknown['image_ids'], b[1]['image_ids']) or \
            not np.array_equal(known['annotation_indices'], b[0]['annotation_indices']) or \
            not np.array_equal(unknown['annotation_indices'], b[1]['annotation_indices']) or \
            not np.array_equal(known['image_ids'], c[0]['image_ids']) or \
            not np.array_equal(unknown['image_ids'], c[1]['image_ids']):
        raise ValueError('Input ROI order mismatch')
    if not np.array_equal(a[2][1], b[2][1]) or not np.array_equal(a[3][1], b[3][1]) or \
            not np.array_equal(a[2][1], c[2][1]) or not np.array_equal(a[3][1], c[3][1]):
        raise ValueError('PIM class prediction differs')
    um, groups, counts = unknown_id_split(unknown['class_ids'])
    ck, cu, rk, ru = subset(known, km), subset(unknown, um), \
        subset(known, ~km), subset(unknown, ~um)
    v.CALIBRATION_KNOWN = ck
    records = {}
    variants = [('original', a[2][0], a[3][0], 0.),
        ('half', .5*a[2][0]+.5*b[2][0], .5*a[3][0]+.5*b[3][0], .5),
        ('multilayer', b[2][0], b[3][0], 1.),
        ('half_spatial', .5*a[2][0]+.5*c[2][0], .5*a[3][0]+.5*c[3][0], .5),
        ('spatial', c[2][0], c[3][0], 1.)]
    for name, ks, us, weight in variants:
        kp, up = a[2][1], a[3][1]
        th = v.select_threshold((ks[km], kp[km]), (us[um], up[um]))
        cal = v.summarize(ck, cu, (ks[km], kp[km]), (us[um], up[um]), th)
        unseen = v.summarize(rk, ru, (ks[~km], kp[~km]),
            (us[~um], up[~um]), th)
        records[name] = {'weight_extra_feature_model': weight, 'threshold': th,
            'calibration': cal, 'unseen': unseen}
        print(name, 'cal', round(cal['known_correct_accept_rate'], 4),
            cal['unknown_false_accept_count'], 'unseen',
            round(unseen['known_correct_accept_rate'], 4),
            unseen['unknown_false_accept_count'], flush=True)
    selected = max(records, key=lambda name: (records[name]['calibration']
        ['known_correct_accept_rate'], -records[name]['calibration']['unknown_false_accept_count']))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'results.json').write_text(json.dumps({'candidates': records,
        'selected_on_calibration': selected, 'unknown_calibration_ids': groups[0],
        'unknown_evaluation_ids': groups[1], 'unknown_counts': counts,
        'test_used': False, 'previously_inspected_validation': True}, indent=2) + '\n')
    print('selected:', selected)


if __name__ == '__main__':
    main()
