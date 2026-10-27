"""One-shot, zero-adaptation evaluation of the locked defect checkpoint on pillQC.

Only pillQC chip and normal are in the primary metric. Dirt is deliberately
excluded to match the published structural-defect comparison. No training,
threshold selection, or test-time augmentation occurs in this script.
"""
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageOps
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model/scripts'))
from finetune_pharmavision_cpu import model_for_training  # noqa: E402

SOURCE = ROOT / 'data/external/pillQC'
IMAGES = SOURCE / 'images'
CHECKPOINT = ROOT / 'model/runs/defect/efficientnetv2s_finalblocks_cpu_20261027/best.pt'
RUN_MANIFEST = CHECKPOINT.parent / 'run-manifest.json'
PV_MANIFEST = ROOT / 'data/processed/pharmavision/manifest.csv'
OUT = ROOT / 'model/reports/defect-pillqc-cross-domain-20261027'
THRESHOLD = 0.40


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


class PillQC(Dataset):
    def __init__(self, rows):
        self.rows = rows
        self.transform = transforms.Compose([
            transforms.Resize(224), transforms.CenterCrop(224), transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(ROOT / row['image_path']) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            return self.transform(image), int(row['true_label'] == 'defective')


def audit():
    if not IMAGES.is_dir():
        raise FileNotFoundError(IMAGES)
    rows = []
    expected = {'normal': 149, 'chip': 43, 'dirt': 138}
    for label, count in expected.items():
        files = sorted((IMAGES / label).glob('*.jpg'))
        if len(files) != count:
            raise ValueError(f'pillQC {label}: expected {count}, found {len(files)}')
        for path in files:
            with Image.open(path) as image:
                image.verify()
            if label == 'dirt':
                continue
            rows.append({'image_path': str(path.relative_to(ROOT)),
                         'source_label': label,
                         'true_label': 'defective' if label == 'chip' else 'normal',
                         'sha256': sha(path)})
    if len({r['sha256'] for r in rows}) != len(rows):
        raise ValueError('duplicate images within evaluated pillQC subset')
    with PV_MANIFEST.open(newline='') as f:
        pv_hashes = {r['sha256'] for r in csv.DictReader(f)}
    overlaps = [r['image_path'] for r in rows if r['sha256'] in pv_hashes]
    if overlaps:
        raise ValueError(f'pillQC overlaps PharmaVision: {overlaps}')
    return rows


def contact_sheet(errors):
    if not errors:
        return
    columns, width, height = 6, 180, 215
    sheet = Image.new('RGB', (columns * width, ((len(errors) + columns - 1) // columns) * height), 'white')
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(errors):
        x, y = (index % columns) * width, (index // columns) * height
        with Image.open(ROOT / row['image_path']) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((170, 170))
            sheet.paste(image, (x + (width - image.width) // 2, y))
        draw.text((x + 3, y + 173), Path(row['image_path']).name, fill='black')
        draw.text((x + 3, y + 189), f"{row['source_label']} p={row['defective_probability']:.3f}", fill='black')
    sheet.save(OUT / 'errors.jpg', quality=90)


def main():
    if OUT.exists():
        raise FileExistsError(f'results already exist; refusing to rerun/overwrite: {OUT}')
    torch.set_num_threads(8)
    rows = audit()
    manifest = json.loads(RUN_MANIFEST.read_text())
    if manifest['best_epoch'] != 12 or manifest['test_used'] is not False:
        raise ValueError('unexpected checkpoint selection state')
    checkpoint = torch.load(CHECKPOINT, map_location='cpu', weights_only=False)
    if checkpoint['epoch'] != 11 or checkpoint['config']['val_threshold'] != THRESHOLD:
        raise ValueError('unexpected checkpoint epoch or threshold')
    model = model_for_training()
    model.load_state_dict(checkpoint['model'])
    model.eval()
    probabilities = []
    with torch.inference_mode():
        for images, _ in DataLoader(PillQC(rows), batch_size=8, shuffle=False, num_workers=0):
            probabilities.extend(model(images).softmax(dim=1)[:, 1].tolist())
    for row, probability in zip(rows, probabilities):
        row['defective_probability'] = probability
        row['predicted_label'] = 'defective' if probability >= THRESHOLD else 'normal'
        row['correct'] = row['predicted_label'] == row['true_label']
    tn = sum(r['true_label'] == 'normal' and r['predicted_label'] == 'normal' for r in rows)
    fp = sum(r['true_label'] == 'normal' and r['predicted_label'] == 'defective' for r in rows)
    fn = sum(r['true_label'] == 'defective' and r['predicted_label'] == 'normal' for r in rows)
    tp = sum(r['true_label'] == 'defective' and r['predicted_label'] == 'defective' for r in rows)
    result = {'source_repo': 'https://github.com/matlab-deep-learning/pillQC',
              'source_commit': subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
              'checkpoint': str(CHECKPOINT.relative_to(ROOT)), 'checkpoint_sha256': sha(CHECKPOINT),
              'best_epoch': 12, 'threshold': THRESHOLD, 'device': 'cpu',
              'preprocessing': 'EXIF transpose, RGB, resize short side 224, center crop 224, ImageNet normalize',
              'evaluated_counts': {'chip_defective': 43, 'normal': 149}, 'excluded_dirt_count': 138,
              'confusion_matrix_rows_normal_defective': [[tn, fp], [fn, tp]],
              'defective_recall': tp / (tp + fn), 'defective_precision': tp / (tp + fp) if tp + fp else 0,
              'defective_f2': 5 * tp / (5 * tp + 4 * fn + fp) if 5 * tp + 4 * fn + fp else 0,
              'normal_specificity': tn / (tn + fp), 'image_count': len(rows),
              'overlap_with_pharmavision_sha256': 0, 'threshold_tuned_on_pillqc': False}
    OUT.mkdir(parents=True)
    with (OUT / 'predictions.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    errors = [r for r in rows if not r['correct']]
    with (OUT / 'errors.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(errors)
    contact_sheet(errors)
    (OUT / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
