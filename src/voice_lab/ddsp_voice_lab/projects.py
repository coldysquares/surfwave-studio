from __future__ import annotations

from pathlib import Path
import json
import re
import time
import wave
from .paths import PROJECTS_DIR, ensure_home

VALID_AUDIO_EXTENSIONS = {".wav"}

def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower()
    return slug or f"voice-{int(time.time())}"

def project_dir(slug: str) -> Path:
    return PROJECTS_DIR / slug

def create_project(name: str) -> dict:
    ensure_home()
    slug = slugify(name)
    base = project_dir(slug)
    if base.exists():
        i = 2
        candidate = f"{slug}-{i}"
        while project_dir(candidate).exists():
            i += 1
            candidate = f"{slug}-{i}"
        slug = candidate
        base = project_dir(slug)

    for part in ("sources", "data", "model", "renders", "exports", "incoming"):
        (base / part).mkdir(parents=True, exist_ok=True)

    meta = {
        "name": name.strip() or slug,
        "slug": slug,
        "created_at": time.time(),
        "training": {
            "sample_rate": 16000,
            "frame_rate": 50,
            "example_secs": 4.0,
            "hop_secs": 1.0,
            "batch_size": 16,
            "steps": 30000,
        },
    }
    save_project(meta)
    return meta

def save_project(meta: dict) -> None:
    base = project_dir(meta["slug"])
    base.mkdir(parents=True, exist_ok=True)
    (base / "project.json").write_text(json.dumps(meta, indent=2))

def load_project(slug: str) -> dict:
    p = project_dir(slug) / "project.json"
    if not p.exists():
        raise FileNotFoundError(slug)
    return json.loads(p.read_text())

def list_projects() -> list[dict]:
    ensure_home()
    out = []
    for p in sorted(PROJECTS_DIR.glob("*/project.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            continue
    return out

def safe_filename(name: str) -> str:
    name = Path(name).name
    stem = re.sub(r"[^a-zA-Z0-9._ -]+", "_", name).strip()
    return stem or f"audio-{int(time.time())}.wav"

def inspect_wav(path: Path) -> dict:
    with wave.open(str(path), "rb") as w:
        channels = w.getnchannels()
        sample_rate = w.getframerate()
        frames = w.getnframes()
        sampwidth = w.getsampwidth()
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sample_rate": sample_rate,
        "channels": channels,
        "bit_depth": sampwidth * 8,
        "duration_sec": frames / float(sample_rate) if sample_rate else 0.0,
    }

def inspect_sources(slug: str) -> dict:
    source_dir = project_dir(slug) / "sources"
    files = []
    total = 0.0
    for p in sorted(source_dir.glob("*.wav")):
        try:
            info = inspect_wav(p)
            files.append(info)
            total += info["duration_sec"]
        except Exception as e:
            files.append({"name": p.name, "error": str(e), "duration_sec": 0})
    return {
        "files": files,
        "total_duration_sec": total,
        "total_duration_min": total / 60.0,
        "ready_10_min": total >= 600,
        "ready_15_min": total >= 900,
    }
