"""Create seven-class recognition crops from YOLOv7 detections and VAIPE labels.

Detections are paired one-to-one to GT boxes at IoU >= 0.5. Unmatched images and
labels stay together in the exclusion report; only matched crops enter manifests.
No test crop is used for training or model selection.
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageOps

ROOT=Path(__file__).resolve().parents[2]
SELECTED=json.loads((ROOT/'model/configs/recognition/selected-classes.json').read_text())['class_ids']
BASE=ROOT/'data/processed/vaipe/recognition/yolov7_rois'
DETECTOR=ROOT/'model/runs/detector/yolov7_pill_baseline_20261025_v2/weights/best.pt'
PRED={
 'train':ROOT/'model/runs/detector/yolov7_pill_recognition_train/best_predictions.json',
 'validation':ROOT/'model/runs/detector/yolov7_pill_recognition_validation/best_predictions.json',
 'test':ROOT/'model/runs/detector/yolov7_pill_common_eval/best_predictions.json',
}


def iou(a,b):
 ax,ay,aw,ah=a;bx,by,bw,bh=b
 ix=max(0,min(ax+aw,bx+bw)-max(ax,bx));iy=max(0,min(ay+ah,by+bh)-max(ay,by))
 inter=ix*iy;union=aw*ah+bw*bh-inter
 return inter/union if union>0 else 0


def match(pred,labels):
 pairs=[]
 for pidx,p in enumerate(pred):
  for lidx,label in enumerate(labels):
   value=iou(p['bbox'],[label[k] for k in ('x','y','w','h')])
   if value>=0.5:pairs.append((value,pidx,lidx))
 pairs.sort(reverse=True)
 used_p,used_l=set(),set();matched={}
 for value,pidx,lidx in pairs:
  if pidx not in used_p and lidx not in used_l:
   matched[lidx]=(pred[pidx],value);used_p.add(pidx);used_l.add(lidx)
 return matched


def crop_box(box,width,height,margin=0.1):
 x,y,w,h=box
 left=max(0,int(x-w*margin));top=max(0,int(y-h*margin))
 right=min(width,int(x+w*(1+margin)+0.999));bottom=min(height,int(y+h*(1+margin)+0.999))
 if right<=left or bottom<=top:raise ValueError(f'invalid crop {box}')
 return (left,top,right,bottom)


def export():
 BASE.mkdir(parents=True,exist_ok=True)
 report={'selected_class_ids':SELECTED,'detector_sha256':hashlib.sha256(DETECTOR.read_bytes()).hexdigest(),
         'match_iou':0.5,'score_filter':'YOLOv7 export conf_thres=0.001; no extra cutoff','margin_fraction':0.1,'splits':{}}
 all_groups={}
 for split in PRED:
  with (ROOT/f'data/processed/vaipe/splits/{split}.csv').open(newline='') as f:rows=list(csv.DictReader(f))
  predictions=defaultdict(list)
  for item in json.loads(PRED[split].read_text()):predictions[item['image_id']].append(item)
  output=[];excluded=[];counts=Counter();expected=Counter()
  for row in rows:
   image_id=row['image_id'];group=row['group_id']
   if group in all_groups and all_groups[group]!=split:raise ValueError(f'group leak: {group}')
   all_groups[group]=split
   labels=json.loads((ROOT/row['label_path']).read_text())
   if len(labels)!=int(row['box_count']):raise ValueError(f'label count: {image_id}')
   matched=match(predictions[image_id],labels)
   selected_idx=[i for i,l in enumerate(labels) if l['label'] in SELECTED]
   if not selected_idx:continue
   image=None
   for idx in selected_idx:
    label=labels[idx];cls=label['label'];expected[cls]+=1
    if idx not in matched:
     excluded.append({'image_id':image_id,'annotation_index':idx,'class_id':cls,'reason':'no_detector_box_iou_0.5'})
     continue
    pred,overlap=matched[idx]
    if image is None:
     with Image.open(ROOT/row['image_path']) as raw:image=ImageOps.exif_transpose(raw).convert('RGB')
     if image.size!=(int(row['width']),int(row['height'])):raise ValueError(f'EXIF dimensions: {image_id}')
    box=crop_box(pred['bbox'],image.width,image.height)
    dst=BASE/split/str(cls)/f'{image_id}_{idx}.jpg'
    dst.parent.mkdir(parents=True,exist_ok=True)
    image.crop(box).save(dst,quality=95,subsampling=0)
    output.append({'image_id':image_id,'annotation_index':idx,'class_id':cls,'group_id':group,
                   'image_path':row['image_path'],'crop_path':str(dst.relative_to(ROOT)),
                   'detector_score':pred['score'],'match_iou':overlap,
                   'crop_left':box[0],'crop_top':box[1],'crop_right':box[2],'crop_bottom':box[3]})
    counts[cls]+=1
  fields=['image_id','annotation_index','class_id','group_id','image_path','crop_path','detector_score','match_iou','crop_left','crop_top','crop_right','crop_bottom']
  with (BASE/f'{split}.csv').open('w',newline='') as f:
   writer=csv.DictWriter(f,fields);writer.writeheader();writer.writerows(output)
  with (BASE/f'{split}-excluded.csv').open('w',newline='') as f:
   writer=csv.DictWriter(f,['image_id','annotation_index','class_id','reason']);writer.writeheader();writer.writerows(excluded)
  report['splits'][split]={'expected_known_boxes':sum(expected.values()),'matched_crops':len(output),
                           'unmatched_known_boxes':len(excluded),'class_counts':dict(sorted(counts.items())),
                           'expected_class_counts':dict(sorted(expected.items()))}
 (BASE/'export-report.json').write_text(json.dumps(report,indent=2)+'\n')
 return report

if __name__=='__main__':print(json.dumps(export(),indent=2))
