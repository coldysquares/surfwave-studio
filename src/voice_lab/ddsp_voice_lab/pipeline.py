from __future__ import annotations

from pathlib import Path
import sys
from .projects import project_dir

def q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")

def module_cmd(module: str) -> list[str]:
    return [sys.executable, "-m", module]

def prepare_command(slug: str) -> list[str]:
    base = project_dir(slug)
    return module_cmd("ddsp_voice_lab.prepare_worker") + [
        f"--sources={base / 'sources'}",
        f"--output={base / 'data' / 'train.tfrecord'}",
    ]

def train_command(slug: str, steps: int = 30000, batch_size: int = 16) -> list[str]:
    base = project_dir(slug)
    model_dir = str(base / "model")
    file_pattern = str(base / "data" / "train.tfrecord*")
    return module_cmd("ddsp.training.ddsp_run") + [
        "--mode=train",
        "--alsologtostderr",
        "--allow_memory_growth=True",
        f"--save_dir={model_dir}",
        "--gin_file=models/vst/vst.gin",
        "--gin_file=datasets/tfrecord.gin",
        f"--gin_param=TFRecordProvider.file_pattern='{q(file_pattern)}'",
        "--gin_param=TFRecordProvider.centered=True",
        "--gin_param=TFRecordProvider.frame_rate=50",
        f"--gin_param=batch_size={int(batch_size)}",
        f"--gin_param=train_util.train.num_steps={int(steps)}",
        "--gin_param=train_util.train.steps_per_save=300",
        "--gin_param=trainers.Trainer.checkpoints_to_keep=3",
    ]

def export_command(slug: str) -> list[str]:
    base = project_dir(slug)
    return module_cmd("ddsp_voice_lab.export_worker") + [
        f"--project={slug}",
        f"--model-dir={base / 'model'}",
        f"--output-dir={base / 'exports' / 'tflite'}",
    ]

def render_command(
    slug: str,
    input_path: Path,
    output_path: Path,
    pitch_semitones: float = 0.0,
    harmonic_gain: float = 1.0,
    noise_gain: float = 1.0,
    reverb: bool = False,
) -> list[str]:
    return module_cmd("ddsp_voice_lab.render_worker") + [
        f"--project={slug}",
        f"--input={input_path}",
        f"--output={output_path}",
        f"--pitch_semitones={pitch_semitones}",
        f"--harmonic_gain={harmonic_gain}",
        f"--noise_gain={noise_gain}",
        f"--reverb={str(bool(reverb)).lower()}",
    ]

def dataset_ready(slug: str) -> bool:
    return any((project_dir(slug) / "data").glob("train.tfrecord*"))

def model_ready(slug: str) -> bool:
    model = project_dir(slug) / "model"
    return any(model.glob("ckpt-*.index")) or (model / "checkpoint").exists()

def latest_model_step(slug: str) -> int:
    model = project_dir(slug) / "model"
    steps = []
    for path in model.glob("ckpt-*.index"):
        try:
            steps.append(int(path.stem.split("-")[-1]))
        except (TypeError, ValueError):
            pass
    return max(steps, default=0)

def export_ready(slug: str) -> bool:
    return any((project_dir(slug) / "exports" / "tflite").rglob("*.tflite"))
