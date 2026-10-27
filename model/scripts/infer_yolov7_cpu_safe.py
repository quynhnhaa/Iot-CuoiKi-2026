"""Persistent CPU YOLOv7 worker with restricted weights_only checkpoint load.

Protocol: print one JSON ready line, then read one JSON request per stdin line and
emit one JSON response. No image or actuator output is written by this worker.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model/vendor/yolov7'))
from models import common, yolo  # noqa: E402
from numpy._core.multiarray import _reconstruct  # noqa: E402
from utils.datasets import letterbox  # noqa: E402
from utils.general import non_max_suppression, scale_coords  # noqa: E402

CHECKPOINT = ROOT / 'model/runs/detector/yolov7_pill_baseline_20261025_v2/weights/best.pt'
CONFIDENCE = 0.25


def load_detector():
    allowed = [common.Concat, common.Conv, common.ImplicitA, common.ImplicitM,
               common.MP, common.RepConv, common.SPPCSPC, yolo.IDetect, yolo.Model,
               torch.nn.SiLU, torch.nn.BatchNorm2d, torch.nn.ModuleList,
               torch.nn.Sequential, torch.nn.Conv2d, torch.nn.MaxPool2d,
               torch.nn.Upsample, _reconstruct, np.ndarray, np.dtype,
               type(np.dtype('uint32')), type(np.dtype('float32')), type(np.dtype('float64'))]
    expected = {f'{item.__module__}.{item.__qualname__}' for item in allowed}
    unsafe = set(torch.serialization.get_unsafe_globals_in_checkpoint(CHECKPOINT))
    if not unsafe.issubset(expected):
        raise ValueError(f'unexpected checkpoint globals: {sorted(unsafe - expected)}')
    with torch.serialization.safe_globals(allowed):
        saved = torch.load(CHECKPOINT, map_location='cpu', weights_only=True)
    model = saved['model'].float().eval()
    if int(model.stride.max()) != 32:
        raise ValueError('unexpected model stride')
    return model


def detect(model, path):
    started = time.perf_counter()
    with Image.open(path) as raw:
        rgb = np.asarray(ImageOps.exif_transpose(raw).convert('RGB'))
    decoded = time.perf_counter()
    resized = letterbox(rgb, 640, stride=int(model.stride.max()))[0]
    tensor = torch.from_numpy(np.ascontiguousarray(resized.transpose(2, 0, 1))).float().unsqueeze(0) / 255
    with torch.inference_mode():
        prediction = model(tensor)[0]
    boxes = non_max_suppression(prediction, CONFIDENCE, .45)[0]
    if len(boxes):
        boxes[:, :4] = scale_coords(tensor.shape[2:], boxes[:, :4], rgb.shape).round()
    ended = time.perf_counter()
    return {'detections': [{'category_id': int(cls),
                            'bbox': [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                            'score': float(score)}
                           for x1, y1, x2, y2, score, cls in boxes.tolist()],
            'timing_ms': {'decode': (decoded - started) * 1000,
                          'preprocess_inference_nms': (ended - decoded) * 1000,
                          'total': (ended - started) * 1000}}


def main():
    torch.set_num_threads(8)
    model = load_detector()
    print(json.dumps({'ready': True, 'device': 'cpu', 'checkpoint': str(CHECKPOINT)}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        path = Path(request['image_path']).resolve()
        allowed = (path.is_relative_to(ROOT / 'data/external/vaipepill2022') or
                   path.is_relative_to(ROOT / 'model/runs/pipeline'))
        if not path.is_file() or not allowed:
            raise ValueError('worker only accepts VAIPE images or generated pipeline replay frames')
        print(json.dumps(detect(model, path)), flush=True)


if __name__ == '__main__':
    main()
