"""Inspect detector ROIs on held-out test at a fixed exploratory score cutoff.

This audit is diagnostic only; thresholds must be selected on validation before use.
"""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[2]
GT = ROOT / 'data/processed/vaipe/dino_coco/annotations/instances_test2017.json'
PRED = {'yolov7': ROOT / 'model/runs/detector/yolov7_pill_common_eval/best_predictions.json',
        'dino': ROOT / 'model/runs/detector/dino_pill_common_eval_predictions.json'}
OUT = ROOT / 'model/reports/pill-roi-audit.json'
PREVIEW = ROOT / 'model/reports/pill-roi-preview.jpg'
CUTOFF = 0.25


def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    x1, y1 = max(ax,bx), max(ay,by)
    x2, y2 = min(ax+aw,bx+bw), min(ay+ah,by+bh)
    inter = max(0,x2-x1)*max(0,y2-y1)
    return inter / (aw*ah+bw*bh-inter) if aw*ah+bw*bh-inter else 0


def audit(name, predictions, images, ground_truth):
    by_image=defaultdict(list)
    name_to_id={v['file_name'].rsplit('.',1)[0]:k for k,v in images.items()}
    for p in predictions:
        image_id=name_to_id[p['image_id']] if isinstance(p['image_id'],str) else p['image_id']
        if p['score']>=CUTOFF:
            by_image[image_id].append(p)
    result={'model':name,'score_cutoff':CUTOFF,'predictions':sum(map(len,by_image.values())),'tp50':0,'fp50':0,'fn50':0,'tp75':0,'fn75':0,'matched_iou':[],'bad_box_count':0}
    for image_id,info in images.items():
        gt=[x['bbox'] for x in ground_truth[image_id]]
        pred=sorted(by_image[image_id],key=lambda x:-x['score'])
        for p in pred:
            x,y,w,h=p['bbox']
            if x < -0.1 or y < -0.1 or w<=0 or h<=0 or x+w>info['width']+0.1 or y+h>info['height']+0.1:
                result['bad_box_count']+=1
        for threshold, field in [(0.5,'50'),(0.75,'75')]:
            used=set();tp=0
            for p in pred:
                choices=[(iou(p['bbox'],box),j) for j,box in enumerate(gt) if j not in used]
                score,j=max(choices,default=(0,-1))
                if score>=threshold:
                    tp+=1;used.add(j)
                    if threshold==0.5:result['matched_iou'].append(score)
            result['tp'+field]+=tp
            result['fn'+field]+=len(gt)-tp
            if threshold==0.5:result['fp50']+=len(pred)-tp
    result['precision50']=result['tp50']/(result['tp50']+result['fp50'])
    result['recall50']=result['tp50']/(result['tp50']+result['fn50'])
    result['recall75']=result['tp75']/(result['tp75']+result['fn75'])
    result['median_matched_iou']=float(np.median(result.pop('matched_iou')))
    return result,by_image


def preview(images, ground_truth, predictions):
    ids=sorted(images)[:12]
    canvas=Image.new('RGB',(1200,900),'white')
    draw=ImageDraw.Draw(canvas)
    for n,image_id in enumerate(ids):
        info=images[image_id]
        with Image.open(ROOT/'data/processed/vaipe/dino_coco/test2017'/info['file_name']) as raw:
            im=ImageOps.exif_transpose(raw).convert('RGB')
        im.thumbnail((280,250))
        original_w,original_h=info['width'],info['height']
        scale_x,scale_y=im.width/original_w,im.height/original_h
        d=ImageDraw.Draw(im)
        for item in ground_truth[image_id]:
            x,y,w,h=item['bbox'];d.rectangle((x*scale_x,y*scale_y,(x+w)*scale_x,(y+h)*scale_y),outline='lime',width=3)
        for item in predictions[image_id]:
            x,y,w,h=item['bbox'];d.rectangle((x*scale_x,y*scale_y,(x+w)*scale_x,(y+h)*scale_y),outline='red',width=2)
        col,row=n%4,n//4
        left,top=col*300,row*300
        canvas.paste(im,(left,top+23))
        draw.text((left+4,top+3),info['file_name'],fill='black')
    canvas.save(PREVIEW,quality=90)


def main():
    data=json.loads(GT.read_text())
    images={item['id']:item for item in data['images']}
    gt=defaultdict(list)
    for item in data['annotations']:gt[item['image_id']].append(item)
    report=[]
    for name,path in PRED.items():
        result,by_image=audit(name,json.loads(path.read_text()),images,gt)
        report.append(result)
        if name=='yolov7':preview(images,gt,by_image)
    OUT.write_text(json.dumps({'images':len(images),'gt_boxes':len(data['annotations']),'diagnostic_only':True,'results':report},indent=2)+'\n')
    print(OUT.read_text())


if __name__=='__main__':main()
