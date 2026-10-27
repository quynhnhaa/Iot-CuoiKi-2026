#!/usr/bin/env bash
set -euo pipefail
usage() { echo 'Usage: model/scripts/train_dino_detector.sh --run-name NAME [--device cuda|cpu] [--dry-run] | --resume RUN_DIR [--dry-run]' ; }
run_name=; resume=; device=cuda; dry=false
while (($#)); do
  case "$1" in
    --run-name) run_name=$2; shift 2;;
    --resume) resume=$2; shift 2;;
    --device) device=$2; shift 2;;
    --dry-run) dry=true; shift;;
    *) usage >&2; exit 2;;
  esac
done
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="$root/.venv/bin/python"
repo="$root/model/vendor/DINO"
config="$root/model/configs/dino_pill_4scale.py"
data="$root/data/processed/vaipe/dino_coco"
if [[ -n $resume ]]; then
  [[ -z $run_name ]] || { echo 'Do not change run name when resuming' >&2; exit 2; }
  run="$(realpath "$resume")"
  "$python_bin" "$root/model/scripts/check_dino_resume.py" "$run" "$device"
else
  [[ $run_name =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'Invalid run name' >&2; exit 2; }
  run="$root/model/runs/detector/$run_name"
  [[ ! -e $run ]] || { echo 'Run already exists' >&2; exit 2; }
  [[ -f $data/annotations/instances_train2017.json && -f $data/annotations/instances_val2017.json ]] || { echo 'Export DINO data first' >&2; exit 1; }
fi
[[ $device == cuda || $device == cpu ]] || { echo 'Invalid device' >&2; exit 2; }
if [[ $device == cuda ]]; then
  "$python_bin" -c 'import torch; assert torch.cuda.is_available()'
fi
compgen -G "$repo/models/dino/ops/MultiScaleDeformableAttention*.so" > /dev/null || {
  echo 'DINO CUDA extension is not compiled. Install CUDA 12.8 nvcc and build models/dino/ops first.' >&2; exit 1;
}
cmd=("$python_bin" main.py --config_file "$config" --dataset_file coco --coco_path "$data" --output_dir "$run" --device "$device" --num_workers 4 --amp)
if [[ -n $resume ]]; then
  cmd+=(--resume "$run/checkpoint.pth")
else
  if [[ $dry == false ]]; then
    mkdir -p "$run"
  "$python_bin" - "$run" "$config" "$data" "$device" <<'PY'
import sys,json,hashlib
from pathlib import Path
run,config,data,device=map(Path,sys.argv[1:])
(run/'run-manifest.json').write_text(json.dumps({'status':'prepared','config_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),'config':str(config),'data':str(data),'device':str(device),'dino_commit':'d84a491d41898b3befd8294d1cf2614661fc0953','epochs':12,'batch_size':1,'num_workers':4,'seed':42},indent=2)+'\n')
PY
  fi
fi
printf '%q ' "${cmd[@]}"; echo
if [[ $dry == true ]]; then exit 0; fi
export PYTHONPATH="$repo/models/dino/ops:${PYTHONPATH:-}"
cd "$repo"
exec "${cmd[@]}"
