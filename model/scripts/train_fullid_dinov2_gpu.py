"""Fine-tune DINOv2 as a classifier over all VAIPE pill IDs, then gate the 7 targets.

Idea (Vaze et al. 2022): a stronger closed-set classifier over many identities
gives a better open-set score. Negatives = train ROIs of non-target IDs,
excluding context label 107 and every ID on the unseen-evaluation side.
Same evaluation protocol as evaluate_vaipe_target_gate_cpu.py. No test access.
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from torchvision import transforms

import train_recognition_verifier as gate
from benchmark_recognition_open_set import CLASSES
from evaluate_recognition_unseen_ids import subset, unknown_id_split

ROOT = Path(__file__).resolve().parents[2]
ROI = ROOT / 'data/processed/vaipe/recognition'
CONTEXT_ONLY = 107
SIZE = 224


def load_crop(row):
    with Image.open(ROOT / row.image_path) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB')
    crop = image.crop((row.crop_left, row.crop_top, row.crop_right, row.crop_bottom))
    crop.thumbnail((288, 288))
    return crop


def load_all(frame):
    with ThreadPoolExecutor(24) as pool:
        return list(pool.map(load_crop, frame.itertuples()))


class Data(torch.utils.data.Dataset):
    def __init__(self, crops, labels, train):
        self.crops, self.labels = crops, labels
        norm = transforms.Normalize([.485, .456, .406], [.229, .224, .225])
        self.tf = transforms.Compose(([
            transforms.RandomResizedCrop(SIZE, scale=(.7, 1), ratio=(.85, 1.15)),
            transforms.RandomHorizontalFlip(), transforms.RandomVerticalFlip(),
            transforms.RandomRotation(180),
            transforms.ColorJitter(.2, .2, .05, .01)] if train else [
            transforms.Resize((SIZE, SIZE))]) + [transforms.ToTensor(), norm])

    def __len__(self):
        return len(self.crops)

    def __getitem__(self, i):
        return self.tf(self.crops[i]), self.labels[i]


class Net(torch.nn.Module):
    def __init__(self, n_class, arch):
        super().__init__()
        # Local source + official weights already used by extract_recognition_dinov2.py.
        self.backbone = torch.hub.load(str(Path.home() / '.cache/torch/hub/facebookresearch_dinov2_main'),
                                       arch, source='local', pretrained=False)
        weights = ROOT / f'model/.cache/torch/hub/checkpoints/{arch}_pretrain.pth'
        self.backbone.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True))
        self.head = torch.nn.Parameter(torch.randn(n_class, self.backbone.embed_dim) * .01)
        self.scale = 16.

    def embed(self, x):
        return F.normalize(self.backbone(x), dim=1)

    def forward(self, x):
        z = self.embed(x)
        return self.scale * z @ F.normalize(self.head, dim=1).T, z


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--arch', default='dinov2_vits14')
    p.add_argument('--epochs', type=int, default=10)
    p.add_argument('--batch', type=int, default=48)
    p.add_argument('--margin', type=float, default=.2)
    p.add_argument('--strict', action='store_true', help='exclude every validation-unknown ID from negatives')
    p.add_argument('--seed', type=int, default=20261027)
    a = p.parse_args()
    torch.manual_seed(a.seed); np.random.seed(a.seed)
    out = ROOT / f'model/runs/recognition/fullid_{a.arch}_m{a.margin}{"_strict" if a.strict else ""}_20261027'
    out.mkdir(parents=True, exist_ok=True)
    dev = torch.device('cuda')

    known_tr = pd.read_csv(ROI / 'yolov7_rois/train.csv')
    known_va = pd.read_csv(ROI / 'yolov7_rois/validation.csv')
    unk_tr = pd.read_csv(ROI / 'yolov7_unknown/train.csv')
    unk_va_all = pd.read_csv(ROI / 'yolov7_unknown/validation.csv')
    km = gate.grouped_mask('validation', 'known', 0)
    unk_va = unk_va_all[unk_va_all.class_id != CONTEXT_ONLY].reset_index(drop=True)
    um, ids, _ = unknown_id_split(unk_va.class_id.values)
    unseen_ids = set(ids[1]) | (set(ids[0]) if a.strict else set())
    neg = unk_tr[(unk_tr.class_id != CONTEXT_ONLY) & ~unk_tr.class_id.isin(unseen_ids)]
    assert not set(neg.class_id) & unseen_ids and not set(neg.class_id) & set(CLASSES)
    neg_ids = sorted(set(neg.class_id))
    all_ids = list(CLASSES) + neg_ids
    train = pd.concat([known_tr, neg], ignore_index=True)
    labels = np.array([all_ids.index(c) for c in train.class_id])
    print(f'train {len(train)} rois, {len(all_ids)} ids ({len(neg_ids)} negative); unseen ids {len(unseen_ids)}', flush=True)

    t0 = time.time()
    tr_crops, kv_crops, uv_crops = load_all(train), load_all(known_va), load_all(unk_va)
    print(f'loaded crops {time.time()-t0:.0f}s', flush=True)

    counts = np.bincount(labels)
    weights = 1 / np.sqrt(counts[labels])  # soften imbalance between IDs
    sampler = torch.utils.data.WeightedRandomSampler(weights, len(labels), replacement=True)
    loader = torch.utils.data.DataLoader(Data(tr_crops, labels, True), a.batch, sampler=sampler,
                                         num_workers=12, drop_last=True, persistent_workers=True)
    net = Net(len(all_ids), a.arch).to(dev)
    opt = torch.optim.AdamW([{'params': net.backbone.parameters(), 'lr': 1e-5},
                             {'params': [net.head], 'lr': 1e-3}], weight_decay=.05)
    steps = a.epochs * len(loader)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, [1e-5, 1e-3], total_steps=steps, pct_start=.1)
    for epoch in range(a.epochs):
        net.train(); total = 0
        for x, y in loader:
            x, y = x.to(dev, non_blocking=True), y.to(dev)
            with torch.autocast('cuda', dtype=torch.bfloat16):
                logits, _ = net(x)
            logits = logits.float() - net.scale * a.margin * F.one_hot(y, len(all_ids))  # CosFace
            loss = F.cross_entropy(logits, y, label_smoothing=.1)
            opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); sched.step()
            total += loss.item()
        print(f'epoch {epoch+1}/{a.epochs} loss {total/len(loader):.4f}', flush=True)
    torch.save({'model': net.state_dict(), 'all_ids': all_ids, 'args': vars(a)}, out / 'last.pt')

    @torch.inference_mode()
    def infer(crops):
        net.eval(); outs = []
        dl = torch.utils.data.DataLoader(Data(crops, np.zeros(len(crops), int), False), 128, num_workers=8)
        for x, _ in dl:
            with torch.autocast('cuda', dtype=torch.bfloat16):
                lg, z = net(x.to(dev))
            outs.append((lg.float().cpu(), z.float().cpu()))
        return torch.cat([o[0] for o in outs]).numpy(), torch.cat([o[1] for o in outs]).numpy()

    kl, kz = infer(kv_crops)
    ul, uz = infer(uv_crops)
    np.savez(out / 'validation-outputs.npz', known_logits=kl, known_z=kz, unknown_logits=ul, unknown_z=uz)
    n = len(CLASSES)
    known = {'class_ids': known_va.class_id.values}
    unknown = {'class_ids': unk_va.class_id.values}

    def candidates(lg, z):
        prob = torch.softmax(torch.as_tensor(lg), 1).numpy()
        pred = lg[:, :n].argmax(1)
        r = np.arange(len(lg))
        return {'p_target_all_ids': (prob[r, pred], pred),
                'cos_margin_vs_neg': ((lg[r, pred] - lg[:, n:].max(1)) / 16, pred),
                'cos_target': (lg[r, pred] / 16, pred)}
    ks, us = candidates(kl, kz), candidates(ul, uz)
    results = {}
    for name in ks:
        k, u = ks[name], us[name]
        gate.CALIBRATION_KNOWN = subset(known, km)
        t = gate.select_threshold((k[0][km], k[1][km]), (u[0][um], u[1][um]))
        r = gate.summarize(subset(known, ~km), subset(unknown, ~um),
                           (k[0][~km], k[1][~km]), (u[0][~um], u[1][~um]), t)
        r['threshold'] = float(t)
        closed = float((k[1] == np.array([CLASSES.index(c) for c in known['class_ids']])).mean())
        r['closed_set_acc_all_known_val'] = closed
        results[name] = r
        pc = ' '.join(f"{c}:{v['correct_accepted']}/{v['total']}" for c, v in r['per_class'].items())
        print(f"{name:20s} known {r['known_correct_accept_rate']:.2%} unknown "
              f"{r['unknown_false_accept_count']}/{r['unknown_count']} closed {closed:.2%} | {pc}", flush=True)
    (out / 'results.json').write_text(json.dumps({'args': vars(a), 'negative_ids': list(map(int, neg_ids)),
        'unseen_ids': sorted(map(int, unseen_ids)), 'results': results}, indent=2))


if __name__ == '__main__':
    main()
