"""Evaluate DINO and YOLOv7 predictions using one COCO protocol.

The script only reads the held-out test annotations and already-exported predictions.
It does not change thresholds, select checkpoints, or train a model.
"""
import json
from pathlib import Path

import numpy as np
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

ROOT = Path(__file__).resolve().parents[2]
GT = ROOT / 'data/processed/vaipe/dino_coco/annotations/instances_test2017.json'
YOLO = ROOT / 'model/runs/detector/yolov7_pill_common_eval/best_predictions.json'
DINO = ROOT / 'model/runs/detector/dino_pill_common_eval_predictions.json'
OUTPUT = ROOT / 'model/reports/pill-detector-common-coco.json'


def evaluate(coco, name, path, name_to_id):
    predictions = json.loads(path.read_text())
    if name == 'yolov7':
        for p in predictions:
            p['image_id'] = name_to_id[p['image_id']]
    ids = set(coco.getImgIds())
    if not predictions or any(p['image_id'] not in ids or p['category_id'] != 0 for p in predictions):
        raise ValueError(f'invalid image/category IDs in {name}')
    dt = coco.loadRes(predictions)
    ev = COCOeval(coco, dt, 'bbox')
    ev.params.imgIds = sorted(ids)
    ev.params.catIds = [0]
    ev.params.iouThrs = np.linspace(0.5, 0.95, 10)
    ev.params.maxDets = [1, 10, 100]
    ev.evaluate();ev.accumulate();ev.summarize()
    recall = ev.eval['recall'][:, 0, 0, 2]
    p_at_50 = ev.eval['precision'][0, :, 0, 0, 2]
    valid = p_at_50 >= 0
    recall_grid = ev.params.recThrs[valid]
    r_at_p99 = float(max(recall_grid[p_at_50[valid] >= 0.99], default=0.0))
    return {'name': name, 'prediction_count': len(predictions), 'ap50_95': float(ev.stats[0]),
            'ap50': float(ev.stats[1]), 'ap75': float(ev.stats[2]),
            'ar50_maxdets100': float(recall[0]), 'ar50_95_maxdets100': float(ev.stats[8]),
            'max_recall_at_precision_99_iou50': r_at_p99,
            'method': 'pycocotools COCOeval bbox; maxDets=[1,10,100]; IoU=0.50:0.95'}


def main():
    coco = COCO(str(GT))
    name_to_id = {image['file_name'].rsplit('.', 1)[0]: image['id'] for image in coco.imgs.values()}
    if len(coco.imgs) != 1422 or len(coco.anns) != 5810:
        raise ValueError('unexpected held-out test annotations')
    results = [evaluate(coco, 'yolov7', YOLO, name_to_id), evaluate(coco, 'dino', DINO, name_to_id)]
    payload = {'images':len(coco.imgs),'gt_boxes':len(coco.anns),'results':results}
    OUTPUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(payload,indent=2))


if __name__ == '__main__':
    main()
