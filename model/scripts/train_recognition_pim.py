"""Train seven-class FGVC-PIM on group-safe YOLOv7 ROI crops with exact epoch resume.

This script uses the original PIM module and its loss terms. It selects checkpoints
by validation macro F1 and never reads the held-out test split during training.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

ROOT=Path(__file__).resolve().parents[2]
VENDOR=ROOT/'model/vendor/FGVC-PIM'
sys.path.insert(0,str(VENDOR))
from models.builder import build_resnet50  # noqa: E402

CLASSES=[64,91,89,99,51,46,10]
CLASS_TO_INDEX={value:index for index,value in enumerate(CLASSES)}
ROI=ROOT/'data/processed/vaipe/recognition/yolov7_rois'
WEIGHTS=ROOT/'model/checkpoints/resnet50_imagenet1k_v1.pth'
RUNS=ROOT/'model/runs/recognition'
CONFIG={'epochs':20,'batch_size':4,'accumulation':2,'image_size':320,'workers':4,
        'learning_rate':0.0002,'weight_decay':0.0005,'fpn_size':256,
        'num_selects':{'layer1':32,'layer2':32,'layer3':32,'layer4':32},
        'loss_weights':{'base':0.5,'select':0.0,'drop':5.0,'combiner':1.0},
        'seed':20261026,'classes':CLASSES}

class ROIDataset(Dataset):
    def __init__(self,split,image_size):
        with (ROI/f'{split}.csv').open(newline='') as f:self.rows=list(csv.DictReader(f))
        self.split=split
        normalize=transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])
        if split=='train':
            self.transform=transforms.Compose([transforms.Resize((360,360)),
                transforms.RandomCrop(image_size),transforms.RandomHorizontalFlip(),
                transforms.ColorJitter(brightness=.12,contrast=.12,saturation=.08),
                transforms.ToTensor(),normalize])
        else:
            self.transform=transforms.Compose([transforms.Resize((360,360)),
                transforms.CenterCrop(image_size),transforms.ToTensor(),normalize])
    def __len__(self):return len(self.rows)
    def __getitem__(self,index):
        row=self.rows[index]
        with Image.open(ROOT/row['crop_path']) as im:image=im.convert('RGB')
        return self.transform(image),CLASS_TO_INDEX[int(row['class_id'])]


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def build_model(config,load_imagenet):
    model=build_resnet50(pretrained='',img_size=config['image_size'],fpn_size=config['fpn_size'],
                         num_selects=config['num_selects'],num_classes=len(CLASSES))
    if load_imagenet:
        pretrained=torch.load(WEIGHTS,map_location='cpu',weights_only=True)
        state=model.state_dict()
        loaded={f'backbone.{k}':v for k,v in pretrained.items()
                if f'backbone.{k}' in state and state[f'backbone.{k}'].shape==v.shape}
        if len(loaded)<260:raise ValueError(f'only {len(loaded)} ImageNet tensors match PIM')
        state.update(loaded);model.load_state_dict(state)
        print(f'Loaded {len(loaded)} ImageNet tensors into PIM backbone',flush=True)
    return model


def pim_loss(outputs,labels,weights):
    loss=0
    for name,logits in outputs.items():
        if name.startswith('select_') and weights['select']:
            target=labels[:,None].expand(-1,logits.shape[1]).reshape(-1)
            loss=loss+weights['select']*F.cross_entropy(logits.reshape(-1,len(CLASSES)),target)
        elif name.startswith('drop_') and weights['drop']:
            loss=loss+weights['drop']*F.mse_loss(torch.tanh(logits),torch.full_like(logits,-1))
        elif name.startswith('layer'):
            loss=loss+weights['base']*F.cross_entropy(logits.mean(1),labels)
        elif name=='comb_outs':
            loss=loss+weights['combiner']*F.cross_entropy(logits,labels)
    return loss


def macro_f1(confusion):
    values=[]
    for idx in range(len(CLASSES)):
        tp=confusion[idx,idx]
        fp=confusion[:,idx].sum()-tp
        fn=confusion[idx,:].sum()-tp
        denom=2*tp+fp+fn
        values.append(float(2*tp/denom) if denom else 0.0)
    return sum(values)/len(values),values


def validate(model,loader,device):
    model.eval();confusion=np.zeros((len(CLASSES),len(CLASSES)),dtype=np.int64)
    with torch.inference_mode():
        for images,labels in loader:
            images=images.to(device,non_blocking=True)
            with torch.autocast(device_type='cuda',enabled=device.type=='cuda'):
                logits=model(images)['comb_outs']
            pred=logits.argmax(1).cpu().numpy()
            for true,guess in zip(labels.numpy(),pred):confusion[true,guess]+=1
    f1,per_class=macro_f1(confusion)
    return {'macro_f1':f1,'accuracy':float(np.trace(confusion)/confusion.sum()),
            'per_class_f1':{str(cls):per_class[idx] for idx,cls in enumerate(CLASSES)},
            'confusion_matrix':confusion.tolist()}


def save_atomic(payload,path):
    temporary=path.with_name(path.name+'.tmp')
    torch.save(payload,temporary);os.replace(temporary,path)


def parse_args():
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--run-name');group.add_argument('--resume')
    p.add_argument('--device',choices=['auto','cuda','cpu'],default='auto')
    p.add_argument('--dry-run',action='store_true')
    return p.parse_args()


def main():
    args=parse_args()
    if args.run_name:
        if not all(x.isalnum() or x in '._-' for x in args.run_name):raise ValueError('invalid run name')
        run=RUNS/args.run_name
        if run.exists():raise FileExistsError(run)
        config=CONFIG.copy()
    else:
        run=Path(args.resume).resolve()
        if run.parent!=RUNS.resolve():raise ValueError('resume run must be under model/runs/recognition')
        manifest=json.loads((run/'run-manifest.json').read_text())
        config=manifest['config']
        for split,digest in manifest['roi_manifest_sha256'].items():
            if sha(ROI/f'{split}.csv')!=digest:raise ValueError(f'{split} ROI manifest changed')
        if sha(WEIGHTS)!=manifest['backbone_sha256']:raise ValueError('ImageNet weights changed')
        pid_file=run/'pid'
        if pid_file.exists():
            try:
                pid=int(pid_file.read_text().strip())
                text=Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
                if 'train_recognition_pim.py' in text and str(run.name) in text:
                    raise RuntimeError(f'run already active, PID {pid}')
            except FileNotFoundError:pass
    device_name='cuda' if args.device=='auto' and torch.cuda.is_available() else ('cpu' if args.device=='auto' else args.device)
    if device_name=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    if args.dry_run:
        print(json.dumps({'run':str(run),'resume':bool(args.resume),'device':device_name,'config':config},indent=2));return
    device=torch.device(device_name)
    random.seed(config['seed']);np.random.seed(config['seed']);torch.manual_seed(config['seed']);torch.cuda.manual_seed_all(config['seed'])
    train_set=ROIDataset('train',config['image_size']);val_set=ROIDataset('validation',config['image_size'])
    if set(CLASS_TO_INDEX)!=set(int(r['class_id']) for r in train_set.rows):raise ValueError('class mismatch')
    train_loader=DataLoader(train_set,batch_size=config['batch_size'],shuffle=True,
                            num_workers=config['workers'],pin_memory=device.type=='cuda')
    val_loader=DataLoader(val_set,batch_size=config['batch_size'],shuffle=False,
                          num_workers=config['workers'],pin_memory=device.type=='cuda')
    model=build_model(config,load_imagenet=not args.resume).to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=config['learning_rate'],weight_decay=config['weight_decay'])
    updates_per_epoch=math.ceil(len(train_loader)/config['accumulation'])
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=config['epochs']*updates_per_epoch)
    scaler=torch.amp.GradScaler('cuda',enabled=device.type=='cuda')
    start=0;best=-1
    if args.resume:
        ckpt=torch.load(run/'last.pt',map_location='cpu',weights_only=False)
        if ckpt['config']!=config:raise ValueError('checkpoint config mismatch')
        if ckpt['epoch']+1>=config['epochs']:raise ValueError('run already complete')
        for key in ('model','optimizer','scheduler','scaler','rng_python','rng_numpy','rng_torch','rng_cuda'):
            if key not in ckpt:raise ValueError(f'missing {key}')
        model.load_state_dict(ckpt['model']);optimizer.load_state_dict(ckpt['optimizer'])
        scheduler.load_state_dict(ckpt['scheduler']);scaler.load_state_dict(ckpt['scaler'])
        if abs(optimizer.param_groups[0]['lr']-scheduler.get_last_lr()[0])>1e-12:raise ValueError('LR mismatch')
        random.setstate(ckpt['rng_python']);np.random.set_state(ckpt['rng_numpy'])
        torch.set_rng_state(ckpt['rng_torch']);torch.cuda.set_rng_state_all(ckpt['rng_cuda'])
        start=ckpt['epoch']+1;best=ckpt['best_macro_f1']
        print(f'Resuming epoch {start+1}/{config["epochs"]}, LR={optimizer.param_groups[0]["lr"]:.9g}',flush=True)
    else:
        run.mkdir(parents=True)
        manifest={'status':'running','config':config,'classes':CLASSES,
                  'roi_manifest_sha256':{s:sha(ROI/f'{s}.csv') for s in ('train','validation','test')},
                  'backbone_sha256':sha(WEIGHTS),'backbone_source':'torchvision ResNet50 IMAGENET1K_V1',
                  'pim_commit':'348edd983d0007a0cbbce65979aa2fbaade068c8','device':device_name,
                  'train_samples':len(train_set),'validation_samples':len(val_set)}
        (run/'run-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for epoch in range(start,config['epochs']):
        model.train();total_loss=0.0;optimizer.zero_grad(set_to_none=True)
        for batch,(images,labels) in enumerate(train_loader):
            images=images.to(device,non_blocking=True);labels=labels.to(device,non_blocking=True)
            with torch.autocast(device_type='cuda',enabled=device.type=='cuda'):
                outputs=model(images);loss=pim_loss(outputs,labels,config['loss_weights'])/config['accumulation']
            scaler.scale(loss).backward()
            if (batch+1)%config['accumulation']==0 or batch+1==len(train_loader):
                previous_scale=scaler.get_scale()
                scaler.step(optimizer);scaler.update()
                if scaler.get_scale()>=previous_scale:
                    scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            total_loss+=float(loss.detach())*config['accumulation']
            if (batch+1)%100==0:print(f'epoch {epoch+1}/{config["epochs"]} batch {batch+1}/{len(train_loader)} loss {total_loss/(batch+1):.4f}',flush=True)
        metrics=validate(model,val_loader,device)
        improved=metrics['macro_f1']>best
        if improved:best=metrics['macro_f1']
        checkpoint={'epoch':epoch,'config':config,'model':model.state_dict(),
                    'optimizer':optimizer.state_dict(),'scheduler':scheduler.state_dict(),
                    'scaler':scaler.state_dict(),'best_macro_f1':best,
                    'rng_python':random.getstate(),'rng_numpy':np.random.get_state(),
                    'rng_torch':torch.get_rng_state(),'rng_cuda':torch.cuda.get_rng_state_all()}
        save_atomic(checkpoint,run/'last.pt')
        if improved:save_atomic(checkpoint,run/'best.pt')
        record={'epoch':epoch+1,'train_loss':total_loss/len(train_loader),'lr':optimizer.param_groups[0]['lr'],**metrics,'best_macro_f1':best}
        with (run/'metrics.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
        print(f'epoch {epoch+1} macro_F1={metrics["macro_f1"]:.4f} acc={metrics["accuracy"]:.4f} best={best:.4f}',flush=True)
    manifest=json.loads((run/'run-manifest.json').read_text());manifest['status']='completed';manifest['best_macro_f1']=best
    (run/'run-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
