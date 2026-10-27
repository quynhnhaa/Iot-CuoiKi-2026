"""Diagnose why IDs 46 and 10 are rejected by the frozen verifier (CPU only)."""
import csv
import json
from collections import Counter

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps

from train_recognition_verifier import (CLASSES, OUT, ROI, ROOT, UNKNOWN,
    Verifier, grouped_mask, load, predict, subset)

REPORT = ROOT / 'model/reports/recognition-id46-id10-audit'


def manifest_rows(kind):
    path = (ROI if kind == 'known' else UNKNOWN) / 'validation.csv'
    with path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    mask = grouped_mask('validation', kind, 1)
    return [row for row, keep in zip(rows, mask) if keep]


def crop(row, kind):
    path = ROOT / (row['crop_path'] if kind == 'known' else row['image_path'])
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB') if kind == 'unknown' else raw.convert('RGB')
        if kind == 'unknown':
            box = tuple(int(row[f'crop_{key}']) for key in ('left', 'top', 'right', 'bottom'))
            image = image.crop(box)
    return image


def contact_sheet(rows_by_category):
    width, image_height, caption_height, columns = 190, 176, 48, 8
    canvas = Image.new('RGB', (width * columns,
                              (image_height + caption_height) * len(rows_by_category)), 'white')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)
    for row_index, (_, records) in enumerate(rows_by_category):
        for column, record in enumerate(records[:columns]):
            image = crop(record['manifest'], record['kind'])
            image.thumbnail((width - 8, image_height - 8), Image.Resampling.LANCZOS)
            left = column * width
            top = row_index * (image_height + caption_height)
            canvas.paste(image, (left + (width - image.width) // 2,
                                 top + (image_height - image.height) // 2))
            caption = (f"{record['kind']} {record['true_id']}→{record['predicted_id']}\n"
                       f"{record['image_id']} score={record['score']:.3f}")
            draw.multiline_text((left + 3, top + image_height), caption,
                                fill='black', font=font, spacing=1)
    destination = REPORT / 'hard-cases.jpg'
    canvas.save(destination, quality=92)
    return destination


def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    run = ROOT / 'model/runs/recognition/class_conditioned_verifier_20261027'
    metrics = json.loads((run / 'validation-results.json').read_text())
    checkpoint = torch.load(run / 'best.pt', map_location='cpu', weights_only=False)
    model = Verifier()
    model.load_state_dict(checkpoint['model'])
    model.eval()
    all_rows, summary, categories = [], {}, []
    for kind in ('known', 'unknown'):
        data = load('validation', kind)
        data = subset(data, grouped_mask('validation', kind, 1))
        source_rows = manifest_rows(kind)
        if len(source_rows) != len(data['class_ids']):
            raise ValueError(f'Feature/manifest row mismatch: {kind}')
        score, predicted, classifier_probability, verifier_probability = predict(
            model, data, torch.device('cpu'), metrics['temperature'])
        for index in range(len(score)):
            row = source_rows[index]
            if row['image_id'] != data['image_ids'][index] or int(row['annotation_index']) != int(data['annotation_indices'][index]):
                raise ValueError(f'Feature/manifest identity mismatch: {kind} row {index}')
            class_id = int(CLASSES[predicted[index]])
            true_id = int(data['class_ids'][index])
            if (kind == 'known' and true_id not in (46, 10)) or (kind == 'unknown' and class_id not in (46, 10)):
                continue
            all_rows.append({'kind': kind, 'image_id': row['image_id'],
                'annotation_index': int(row['annotation_index']), 'group_id': row['group_id'],
                'true_id': true_id, 'predicted_id': class_id,
                'classifier_probability': float(classifier_probability[index]),
                'verifier_probability': float(verifier_probability[index]),
                'score': float(score[index]),
                'accepted_at_current_threshold': bool(score[index] >= metrics['threshold']),
                'manifest': row})
    fields = [key for key in all_rows[0] if key != 'manifest']
    with (REPORT / 'scores.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows([{key: row[key] for key in fields} for row in all_rows])
    for class_id in (46, 10):
        known = [row for row in all_rows if row['kind'] == 'known' and row['true_id'] == class_id]
        unknown = [row for row in all_rows if row['kind'] == 'unknown' and row['predicted_id'] == class_id]
        for name, rows in (('known', known), ('unknown', unknown)):
            ordered = sorted(rows, key=lambda row: row['score'], reverse=True)
            categories.append((f'{name} {class_id}', ordered[:8]))
            values = np.array([row['score'] for row in rows])
            summary[f'{name}_{class_id}'] = {
                'count': len(rows), 'accepted_at_current_threshold': sum(row['accepted_at_current_threshold'] for row in rows),
                'score_quantiles': {str(q): float(np.quantile(values, q)) for q in (0,.25,.5,.75,.9,1)},
                'top_true_ids': dict(Counter(row['true_id'] for row in rows).most_common(10))}
    contact_sheet(categories)
    summary['threshold'] = metrics['threshold']
    summary['split'] = 'validation group-hash parity 1 only'
    summary['test_used'] = False
    (REPORT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
