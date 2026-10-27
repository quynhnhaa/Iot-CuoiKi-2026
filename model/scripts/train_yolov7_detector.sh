#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: model/scripts/train_yolov7_detector.sh [options]
  --device auto|cuda|cpu   auto uses CUDA when available (default: auto)
  --epochs N               positive epoch count (default: 30)
  --batch-size N           default: 8 on CUDA, 1 on CPU
  --workers N              default: 4 on CUDA, 0 on CPU
  --img-size N             default: 640
  --run-name NAME          unique output directory name (default: timestamp + device)
  --resume RUN_DIR         resume from RUN_DIR/weights/last.pt with saved training settings
  --dry-run                print the resolved command without training
  --help                   show this help
HELP
}

requested_device=auto
epochs=30
batch_size=
workers=
img_size=640
run_name=
dry_run=false
resume_run=
train_option_supplied=false
while (($#)); do
  case "$1" in
    --device|--epochs|--batch-size|--workers|--img-size|--run-name|--resume)
      if (($# < 2)); then echo "Missing value for $1" >&2; exit 2; fi
      case "$1" in
        --device) requested_device=$2 ;;
        --epochs) epochs=$2; train_option_supplied=true ;;
        --batch-size) batch_size=$2; train_option_supplied=true ;;
        --workers) workers=$2; train_option_supplied=true ;;
        --img-size) img_size=$2; train_option_supplied=true ;;
        --run-name) run_name=$2; train_option_supplied=true ;;
        --resume) resume_run=$2 ;;
      esac
      shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$requested_device" in auto|cuda|cpu) ;; *) echo "Invalid device: $requested_device" >&2; exit 2 ;; esac
for value in "$epochs" "$img_size"; do
  if [[ ! $value =~ ^[0-9]+$ ]] || ((value < 1)); then echo "epochs and img-size must be positive integers" >&2; exit 2; fi
done
for value in "$batch_size" "$workers"; do
  if [[ -n $value && ! $value =~ ^[0-9]+$ ]]; then echo "batch-size and workers must be integers" >&2; exit 2; fi
done
if [[ -n $batch_size ]] && ((batch_size < 1)); then echo "batch-size must be positive" >&2; exit 2; fi
if [[ -n $run_name && ! $run_name =~ ^[A-Za-z0-9._-]+$ ]]; then echo "run-name may contain letters, digits, dots, underscores and hyphens" >&2; exit 2; fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="$project_root/.venv/bin/python"
yolov7_root="$project_root/model/vendor/yolov7"
data_yaml="$project_root/data/processed/vaipe/yolov7/pill.yaml"
weights="$project_root/model/checkpoints/yolov7_training.pt"
for required in "$python_bin" "$yolov7_root/train.py" "$data_yaml" "$weights"; do
  if [[ ! -f $required ]]; then echo "Missing required file: $required" >&2; exit 1; fi
done
cuda_available=$($python_bin -c 'import torch; print(int(torch.cuda.is_available()))')
case "$requested_device" in
  auto) if [[ $cuda_available == 1 ]]; then device=0; device_name=cuda; else device=cpu; device_name=cpu; fi ;;
  cuda) if [[ $cuda_available != 1 ]]; then echo "CUDA was requested but PyTorch cannot use it" >&2; exit 1; fi; device=0; device_name=cuda ;;
  cpu) device=cpu; device_name=cpu ;;
esac
if [[ -z $batch_size ]]; then if [[ $device_name == cuda ]]; then batch_size=8; else batch_size=1; fi; fi
if [[ -z $workers ]]; then if [[ $device_name == cuda ]]; then workers=4; else workers=0; fi; fi
if [[ -n $resume_run ]]; then
  if [[ $train_option_supplied == true ]]; then
    echo "Resume keeps epochs, batch size, workers, image size and run name from opt.yaml; remove those overrides" >&2
    exit 2
  fi
  if [[ ! -d $resume_run ]]; then echo "Run directory does not exist: $resume_run" >&2; exit 1; fi
  run_root="$(realpath "$resume_run")"
  case "$run_root/" in
    "$project_root/model/runs/detector/"*) ;;
    *) echo "Resume directory must be under model/runs/detector/: $run_root" >&2; exit 1 ;;
  esac
  if [[ -f $run_root/pid ]]; then
    existing_pid="$(cat "$run_root/pid")"
    if [[ $existing_pid =~ ^[0-9]+$ ]] && kill -0 "$existing_pid" 2>/dev/null &&
       ps -p "$existing_pid" -o args= | grep -q 'train.py'; then
      echo "This run is still active (PID $existing_pid); do not resume concurrently" >&2
      exit 1
    fi
  fi
  "$python_bin" "$project_root/model/scripts/check_yolov7_resume.py" "$run_root"
  cmd=("$python_bin" train.py --resume "$run_root/weights/last.pt" --device "$device")
  printf 'Resume device: %s\nRun directory: %s\nCommand:' "$device_name" "$run_root"
else
  if [[ -z $run_name ]]; then run_name="yolov7_pill_$(date +%Y%m%d_%H%M%S)_$device_name"; fi
  run_root="$project_root/model/runs/detector/$run_name"
  if [[ -e $run_root ]]; then echo "Run directory already exists: $run_root" >&2; exit 1; fi
  cmd=("$python_bin" train.py --workers "$workers" --device "$device" --batch-size "$batch_size"
    --data "$data_yaml" --img-size "$img_size" "$img_size" --cfg cfg/training/yolov7.yaml
    --weights "$weights" --name "$run_name" --project "$project_root/model/runs/detector"
    --hyp data/hyp.scratch.custom.yaml --epochs "$epochs")
  printf 'Resolved device: %s\nRun directory: %s\nCommand:' "$device_name" "$run_root"
fi
printf ' %q' "${cmd[@]}"
printf '\n'
if [[ $dry_run == true ]]; then exit 0; fi
cd "$yolov7_root"
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export MPLBACKEND=Agg
exec "${cmd[@]}"
