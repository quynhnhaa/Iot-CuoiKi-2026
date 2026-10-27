"""Eight-way feature head (seven known IDs plus unknown), class-disjoint negatives.

Select epoch and threshold on group calibration only. Exact epoch resume saves
optimizer and RNG state. Never loads VAIPE test.
"""
import argparse
import hashlib
import json
import os
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

import train_recognition_verifier as base
from benchmark_recognition_open_set import CLASSES, normalized_features, temperature

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'model/runs/recognition/open_set_features_20261026'
RUNS = ROOT / 'model/runs/recognition'
SEED = 20261027


class UnknownHead(torch.nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(dim, 256), torch.nn.ReLU(),
            torch.nn.Dropout(.2), torch.nn.Linear(256, len(CLASSES) + 1))

    def forward(self, x):
        return self.net(x)


def signals(model, data, device, temp):
    with torch.inference_mode():
        head = torch.cat([model(x.to(device)).softmax(1).cpu()
                          for x in normalized_features(data).split(1024)]).numpy()
    classifier = F.softmax(torch.tensor(data['logits'], dtype=torch.float32) / temp,
                           dim=1).numpy()
    pred = classifier.argmax(1)
    row = np.arange(len(pred))
    score = classifier[row, pred] * head[row, pred]
    return score, pred


def save(payload, path):
    temp = path.with_suffix('.tmp')
    torch.save(payload, temp)
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-name', default='unknown_head_20261027')
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--device', choices=('cuda', 'cpu'), default='cuda')
    args = parser.parse_args()
    if not all(c.isalnum() or c in '._-' for c in args.run_name):
        raise ValueError('Invalid run name')
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    device = torch.device(args.device)
    run = RUNS / args.run_name
    run.mkdir(exist_ok=True, parents=True)
    base.FEATURE_DIR = SOURCE
    kt, ut, kv, uv = (base.load(split, kind) for split, kind in
                      (('train', 'known'), ('train', 'unknown'),
                       ('validation', 'known'), ('validation', 'unknown')))
    negative_ids = sorted(set(ut['class_ids'].tolist()) - set(uv['class_ids'].tolist()))
    ut = base.subset(ut, np.isin(ut['class_ids'], negative_ids))
    km, um = base.grouped_mask('validation', 'known', 0), base.grouped_mask('validation', 'unknown', 0)
    if len(km) != len(kv['class_ids']) or len(um) != len(uv['class_ids']):
        raise ValueError('Feature and manifest rows mismatch')
    ck, cu = base.subset(kv, km), base.subset(uv, um)
    rk, ru = base.subset(kv, ~km), base.subset(uv, ~um)
    temp = temperature(ck['logits'], ck['class_ids'])
    xk, xu = normalized_features(kt).to(device), normalized_features(ut).to(device)
    yk = torch.tensor([CLASSES.index(int(x)) for x in kt['class_ids']], device=device)
    pools = [torch.where(yk == i)[0] for i in range(len(CLASSES))]
    config = {'epochs': args.epochs, 'device': args.device, 'source': str(SOURCE),
        'negative_ids': negative_ids, 'steps_per_epoch': 80, 'known_per_class': 16,
        'unknown_per_step': 112, 'learning_rate': .0003, 'seed': SEED,
        'data_hash': hashlib.sha256(xk.cpu().numpy().tobytes() + xu.cpu().numpy().tobytes() +
            kt['class_ids'].tobytes() + np.asarray(negative_ids, np.int32).tobytes()).hexdigest()}
    manifest = run / 'run-manifest.json'
    if manifest.exists() and json.loads(manifest.read_text()) != config:
        raise ValueError('Run configuration or data changed')
    manifest.write_text(json.dumps(config, indent=2) + '\n')
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    if device.type == 'cuda':
        torch.cuda.manual_seed_all(SEED)
    model = UnknownHead(xk.shape[1]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config['learning_rate'], weight_decay=.001)
    last, best_path = run / 'last.pt', run / 'best.pt'
    start, best_metric = 0, -1.0
    if last.exists():
        saved = torch.load(last, map_location='cpu', weights_only=False)
        if saved['config'] != config:
            raise ValueError('Checkpoint configuration changed')
        model.load_state_dict(saved['model']); optimizer.load_state_dict(saved['optimizer'])
        torch.set_rng_state(saved['rng_torch'])
        np.random.set_state(saved['rng_numpy']); random.setstate(saved['rng_python'])
        if device.type == 'cuda':
            torch.cuda.set_rng_state_all(saved['rng_cuda'])
        start, best_metric = saved['epoch'] + 1, saved['best_metric']
        print(f'Resuming epoch {start+1}/{args.epochs}', flush=True)
    base.CALIBRATION_KNOWN = ck
    for epoch in range(start, args.epochs):
        model.train(); losses = []
        for _ in range(config['steps_per_epoch']):
            indices = torch.cat([pool[torch.randint(len(pool),
                (config['known_per_class'],), device=device)] for pool in pools])
            unknown_indices = torch.randint(len(xu), (config['unknown_per_step'],), device=device)
            x = torch.cat([xk[indices], xu[unknown_indices]])
            y = torch.cat([yk[indices], torch.full((len(unknown_indices),),
                           len(CLASSES), dtype=torch.long, device=device)])
            loss = F.cross_entropy(model(x), y)
            optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        cks, cus = signals(model, ck, device, temp), signals(model, cu, device, temp)
        threshold = base.select_threshold(cks, cus)
        cal = base.summarize(ck, cu, cks, cus, threshold)
        metric = cal['known_correct_accept_rate']
        if metric > best_metric:
            best_metric = metric
            save({'model': model.state_dict(), 'epoch': epoch, 'threshold': threshold,
                  'calibration': cal, 'config': config}, best_path)
        save({'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
              'epoch': epoch, 'best_metric': best_metric, 'config': config,
              'rng_torch': torch.get_rng_state(), 'rng_numpy': np.random.get_state(),
              'rng_python': random.getstate(), 'rng_cuda': torch.cuda.get_rng_state_all()
              if device.type == 'cuda' else []}, last)
        print(f'epoch {epoch+1} loss={np.mean(losses):.4f} cal_correct={metric:.4f} '
              f'cal_unknown={cal["unknown_false_accept_count"]}', flush=True)
    best = torch.load(best_path, map_location='cpu', weights_only=False)
    model.load_state_dict(best['model']); model.eval()
    result = {'best_epoch': best['epoch'] + 1, 'threshold': best['threshold'],
        'calibration': best['calibration'], 'remainder': base.summarize(rk, ru,
            signals(model, rk, device, temp), signals(model, ru, device, temp),
            best['threshold']), 'test_used': False, 'remainder_is_exploratory': True,
        'negative_train_ids': negative_ids}
    (run / 'validation-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'best_epoch': result['best_epoch'], 'remainder': result['remainder']},
                     indent=2), flush=True)


if __name__ == '__main__':
    main()
