"""Export validation mistakes from the frozen CPU baselines; never reads test."""
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'model/runs/defect'
OUT = ROOT / 'model/reports/defect-validation-audit'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for name in ('resnet50_frozen_cpu_20261027', 'efficientnetv2s_frozen_cpu_20261027'):
        run = RUNS / name
        result = json.loads((run / 'result.json').read_text())
        with np.load(run / 'validation-features.npz') as data:
            x, paths, y = data['features'], data['paths'], data['labels']
        c = result['classifier']
        logits = ((x - np.asarray(c['mean'])) / np.asarray(c['std'])) @ np.asarray(c['weight']) + c['bias']
        prob = 1 / (1 + np.exp(-np.clip(logits, -80, 80)))
        threshold = result['validation']['threshold']
        for path, label, score in zip(paths, y, prob):
            pred = int(score >= threshold)
            if pred != int(label):
                all_rows.append({'model': name, 'image_path': str(path),
                                 'true_label': 'defective' if label else 'normal',
                                 'predicted_label': 'defective' if pred else 'normal',
                                 'defective_probability': float(score), 'threshold': threshold})
    with (OUT / 'errors.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    for name in ('resnet50_frozen_cpu_20261027', 'efficientnetv2s_frozen_cpu_20261027'):
        rows = [r for r in all_rows if r['model'] == name]
        width, height = 6 * 190, ((len(rows) + 5) // 6) * 220
        sheet = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(sheet)
        for i, row in enumerate(rows):
            with Image.open(ROOT / row['image_path']) as image:
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((176, 176))
                x, y = (i % 6) * 190, (i // 6) * 220
                sheet.paste(image, (x + (190 - image.width) // 2, y))
            draw.text((x + 4, y + 180), f"{Path(row['image_path']).name} {row['true_label'][:3]}", fill='black')
            draw.text((x + 4, y + 196), f"p={row['defective_probability']:.3f} t={row['threshold']:.3f}", fill='black')
        sheet.save(OUT / f'{name}.jpg', quality=90)
    print(json.dumps({'errors': len(all_rows), 'by_model': {name: sum(r['model'] == name for r in all_rows)
                                                    for name in ('resnet50_frozen_cpu_20261027', 'efficientnetv2s_frozen_cpu_20261027')}}, indent=2))


if __name__ == '__main__':
    main()
