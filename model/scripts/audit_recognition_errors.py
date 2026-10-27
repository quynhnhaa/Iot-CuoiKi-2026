"""Export reproducible error lists and contact sheets for the frozen open-set run."""
import csv
import json

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps

from benchmark_recognition_open_set import (BASE, OUT, Projection, CLASSES,
    embed, load, normalized_features, signals)
from extract_recognition_features import ROOT, ROI, UNKNOWN

REPORT = ROOT / 'model/reports/recognition-error-audit'


def source_rows(split, kind):
    with ((UNKNOWN if kind == 'unknown' else ROI) / f'{split}.csv').open(newline='') as f:
        return list(csv.DictReader(f))


def crop(row, kind):
    with Image.open(ROOT / row['image_path'] if kind == 'unknown' else ROOT / row['crop_path']) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB') if kind == 'unknown' else raw.convert('RGB')
        if kind == 'unknown':
            coords = [int(row[f'crop_{key}']) for key in ('left', 'top', 'right', 'bottom')]
            image = image.crop(tuple(coords))
    return image


def sheet(records, split, kind, path):
    size, caption, columns = 192, 57, 6
    rows = (len(records) + columns - 1) // columns
    canvas = Image.new('RGB', (columns * size, rows * (size + caption)), 'white')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)
    source = source_rows(split, kind)
    for j, record in enumerate(records):
        img = crop(source[record['row_index']], kind)
        img.thumbnail((size - 8, size - 8), Image.Resampling.LANCZOS)
        x, y = j % columns * size, j // columns * (size + caption)
        canvas.paste(img, (x + (size - img.width) // 2, y + (size - img.height) // 2))
        text = f"{record['image_id']} #{record['annotation_index']}\n{record['true_id']} → {record['predicted_id']}\np={record['probability']:.3f} cos={record['cosine']:.3f}"
        draw.multiline_text((x + 4, y + size), text, fill='black', font=font, spacing=2)
    canvas.save(path, quality=92)


def export(split, kind, model, prototypes, temperature, threshold):
    data = load(split, kind)
    p, s, pred = signals(data, embed(model, data, torch.device('cpu')), prototypes, temperature)
    accept = (p >= threshold['probability_min']) & (s >= threshold['cosine_min'])
    true = data['class_ids']
    guess = np.array(CLASSES)[pred]
    if kind == 'known':
        selected = np.where(true != guess)[0]
    else:
        selected = np.where(accept)[0]
    records = []
    for i in selected:
        records.append({'row_index': int(i), 'image_id': str(data['image_ids'][i]),
            'annotation_index': int(data['annotation_indices'][i]),
            'true_id': int(true[i]), 'predicted_id': int(guess[i]),
            'probability': float(p[i]), 'cosine': float(s[i]), 'accepted': bool(accept[i])})
    name = f'{split}-{kind}-{"misclassified" if kind == "known" else "false-accepted"}'
    with (REPORT / f'{name}.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]) if records else [])
        if records:
            writer.writeheader(); writer.writerows(records)
    if records:
        sheet(records, split, kind, REPORT / f'{name}.jpg')
    return {'name': name, 'count': len(records), 'total': len(true)}


def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    selection = json.loads((OUT / 'selection-validation.json').read_text())
    winner = selection['winner']
    checkpoint = torch.load(OUT / f'{winner}.pt', map_location='cpu', weights_only=False)
    model = Projection(normalized_features(load('train', 'known')).shape[1])
    model.load_state_dict(checkpoint['projection']); model.eval()
    threshold = selection['candidate_results'][winner]['threshold']
    summary = [export(split, kind, model, checkpoint['prototypes'], selection['temperature'], threshold)
               for split, kind in [('validation', 'known'), ('validation', 'unknown'),
                                   ('test', 'known'), ('test', 'unknown')]]
    (REPORT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
