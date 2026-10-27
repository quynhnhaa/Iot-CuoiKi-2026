"""Extract frozen FGVC-PIM logits and penultimate features for open-set study."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

from train_recognition_pim import ROOT, ROI, build_model

UNKNOWN = ROOT / 'data/processed/vaipe/recognition/yolov7_unknown'
RUN = ROOT / 'model/runs/recognition/pim_resnet50_7class_20261026_v2'
OUT = ROOT / 'model/runs/recognition/open_set_features_20261026'


class FeatureDataset(Dataset):
    def __init__(self, path, unknown, allowed_ids=None):
        self.rows = list(csv.DictReader(path.open(newline='')))
        if allowed_ids is not None:
            self.rows = [row for row in self.rows if int(row['class_id']) in allowed_ids]
        self.unknown = unknown
        self.transform = transforms.Compose([
            transforms.Resize((360, 360)), transforms.CenterCrop(320),
            transforms.ToTensor(),
            transforms.Normalize([.485, .456, .406], [.229, .224, .225])])

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        path = ROOT / (row['image_path'] if self.unknown else row['crop_path'])
        with Image.open(path) as raw:
            image = ImageOps.exif_transpose(raw).convert('RGB') if self.unknown else raw.convert('RGB')
            if self.unknown:
                coords = [int(row[f'crop_{name}']) for name in ('left', 'top', 'right', 'bottom')]
                image = image.crop(tuple(coords))
        return self.transform(image), index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--checkpoint', type=Path, default=RUN / 'best.pt')
    parser.add_argument('--output-dir', type=Path, default=OUT)
    parser.add_argument('--development-only', action='store_true',
                        help='Extract train and validation features, never test')
    parser.add_argument('--class-disjoint-unknown-train', action='store_true',
                        help='Use only unknown train IDs absent from unknown validation')
    parser.add_argument('--extra-layer4', action='store_true',
                        help='Also export pooled ResNet layer4 feature before PIM FPN')
    parser.add_argument('--extra-layer4-std', action='store_true',
                        help='Also export spatial channel std of ResNet layer4')
    args = parser.parse_args()
    if args.extra_layer4_std and not args.extra_layer4:
        raise ValueError('--extra-layer4-std requires --extra-layer4')
    device = torch.device('cuda' if args.device == 'auto' and torch.cuda.is_available() else
                          'cpu' if args.device == 'auto' else args.device)
    checkpoint_path = args.checkpoint.resolve()
    output_dir = args.output_dir.resolve()
    digest = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    previous_manifest = output_dir / 'manifest.json'
    if previous_manifest.exists():
        previous = json.loads(previous_manifest.read_text())
        if previous.get('source_checkpoint_sha256') not in (None, digest):
            raise ValueError(f'Output features belong to another checkpoint: {output_dir}')
    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
    model_config = checkpoint.get('model_config', checkpoint['config'])
    if 'fpn_size' not in model_config:
        model_config = torch.load(RUN / 'best.pt', map_location='cpu', weights_only=False)['config']
    model = build_model(model_config, load_imagenet=False).to(device)
    model.load_state_dict(checkpoint['model'])
    model.eval()
    hook_features = []
    hook = model.combiner.dropout.register_forward_hook(
        lambda _module, _inputs, output: hook_features.append(output.detach().flatten(1)))
    backbone_features = []
    backbone_std_features = []
    backbone_hook = None
    if args.extra_layer4:
        backbone_hook = model.backbone.register_forward_hook(
            lambda _module, _inputs, output: backbone_features.append(
                F.adaptive_avg_pool2d(output['layer4'].detach(), 1).flatten(1)))
    backbone_std_hook = None
    if args.extra_layer4_std:
        backbone_std_hook = model.backbone.register_forward_hook(
            lambda _module, _inputs, output: backbone_std_features.append(
                output['layer4'].detach().flatten(2).std(2)))
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = [('train', False), ('train', True), ('validation', False), ('validation', True)]
    if not args.development_only:
        entries += [('test', False), ('test', True)]
    allowed_unknown_train = None
    if args.class_disjoint_unknown_train:
        with (UNKNOWN / 'validation.csv').open(newline='') as f:
            validation_ids = {int(row['class_id']) for row in csv.DictReader(f)}
        with (UNKNOWN / 'train.csv').open(newline='') as f:
            train_ids = {int(row['class_id']) for row in csv.DictReader(f)}
        allowed_unknown_train = train_ids - validation_ids
    for split, unknown in entries:
        source = (UNKNOWN if unknown else ROI) / f'{split}.csv'
        target = output_dir / f'{split}-{"unknown" if unknown else "known"}.npz'
        if target.exists():
            print(f'Existing: {target}', flush=True)
            continue
        dataset = FeatureDataset(source, unknown,
            allowed_unknown_train if split == 'train' and unknown else None)
        loader = DataLoader(dataset, batch_size=args.batch_size, num_workers=args.workers,
                            pin_memory=device.type == 'cuda', shuffle=False)
        embeddings, logits_list, indices, backbone_list, backbone_std_list = [], [], [], [], []
        with torch.inference_mode():
            for batch, batch_indices in loader:
                hook_features.clear()
                backbone_features.clear()
                backbone_std_features.clear()
                with torch.autocast(device_type='cuda', enabled=device.type == 'cuda'):
                    logits = model(batch.to(device, non_blocking=True))['comb_outs']
                if len(hook_features) != 1:
                    raise RuntimeError('PIM feature hook did not fire exactly once')
                embeddings.append(hook_features[0].float().cpu().numpy())
                if args.extra_layer4:
                    if len(backbone_features) != 1:
                        raise RuntimeError('Backbone feature hook did not fire exactly once')
                    backbone_list.append(backbone_features[0].float().cpu().numpy())
                if args.extra_layer4_std:
                    if len(backbone_std_features) != 1:
                        raise RuntimeError('Backbone std hook did not fire exactly once')
                    backbone_std_list.append(backbone_std_features[0].float().cpu().numpy())
                logits_list.append(logits.float().cpu().numpy())
                indices.extend(batch_indices.tolist())
        if indices != list(range(len(dataset))):
            raise ValueError('Inference row order changed')
        temporary = target.with_suffix('.tmp')
        with temporary.open('wb') as handle:
            payload = dict(features=np.concatenate(embeddings), logits=np.concatenate(logits_list),
                class_ids=np.array([int(r['class_id']) for r in dataset.rows]),
                image_ids=np.array([r['image_id'] for r in dataset.rows]),
                annotation_indices=np.array([int(r['annotation_index']) for r in dataset.rows]))
            if args.extra_layer4:
                payload['backbone_features'] = np.concatenate(backbone_list)
            if args.extra_layer4_std:
                payload['backbone_std_features'] = np.concatenate(backbone_std_list)
            np.savez_compressed(handle, **payload)
        os.replace(temporary, target)
        print(f'Saved {target}: {len(dataset)} ROIs', flush=True)
    hook.remove()
    if backbone_hook is not None:
        backbone_hook.remove()
    if backbone_std_hook is not None:
        backbone_std_hook.remove()
    (output_dir / 'manifest.json').write_text(json.dumps({
        'source_checkpoint': str(checkpoint_path.relative_to(ROOT)),
        'source_checkpoint_sha256': digest,
        'checkpoint_epoch': checkpoint['epoch'] + 1,
        'feature_layer': 'combiner.dropout', 'feature_policy': 'frozen PIM',
        'transform': 'Resize(360,360), CenterCrop(320), ImageNet normalization',
        'unknown_source': str(UNKNOWN.relative_to(ROOT)),
        'development_only': args.development_only,
        'unknown_train_ids': sorted(allowed_unknown_train) if allowed_unknown_train is not None else 'all',
        'extra_layer4': args.extra_layer4, 'extra_layer4_std': args.extra_layer4_std},
        indent=2) + '\n')


if __name__ == '__main__':
    main()
