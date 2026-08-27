from __future__ import annotations

from pathlib import Path
import json
import os
import platform
import sys
import time
import webbrowser
import zipfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from .jobs import JOBS
from .paths import ensure_home
from .projects import (
    create_project,
    inspect_sources,
    list_projects,
    load_project,
    project_dir,
    safe_filename,
)
from .pipeline import (
    dataset_ready,
    export_command,
    export_ready,
    model_ready,
    latest_model_step,
    prepare_command,
    render_command,
    train_command,
)

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
STATIC = PACKAGE_ROOT / "static"

app = FastAPI(title="Surfwave Voice Lab")

class ProjectCreate(BaseModel):
    name: str

class TrainRequest(BaseModel):
    project: str
    steps: int = 30000
    batch_size: int = 16

class ProjectRequest(BaseModel):
    project: str

class RenderRequest(BaseModel):
    project: str
    filename: str
    pitch_semitones: float = 0.0
    harmonic_gain: float = 1.0
    noise_gain: float = 1.0
    reverb: bool = False

def environment_info():
    result = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "ddsp": None,
        "tensorflow": None,
        "gpu": [],
        "ready": False,
        "issues": [],
    }
    if sys.version_info[:2] != (3, 10):
        result["issues"].append("Voice Lab expects Python 3.10")
    try:
        import ddsp
        result["ddsp"] = getattr(ddsp, "__version__", "installed")
    except Exception as e:
        result["ddsp_error"] = str(e)
        result["issues"].append("DDSP import failed")
    try:
        import tensorflow as tf
        result["tensorflow"] = tf.__version__
        result["gpu"] = [d.name for d in tf.config.list_physical_devices("GPU")]
        if not str(tf.__version__).startswith("2.11"):
            result["issues"].append(f"TensorFlow 2.11.x expected; found {tf.__version__}")
    except Exception as e:
        result["tensorflow_error"] = str(e)
        result["issues"].append("TensorFlow import failed")
    try:
        import ddsp.training  # noqa: F401
    except Exception as e:
        result["training_error"] = str(e)
        result["issues"].append("DDSP training stack import failed")
    result["ready"] = not result["issues"]
    return result

@app.get("/api/state")
def state():
    projects = []
    for meta in list_projects():
        slug = meta["slug"]
        projects.append({
            **meta,
            "sources": inspect_sources(slug),
            "dataset_ready": dataset_ready(slug),
            "model_ready": model_ready(slug),
            "latest_step": latest_model_step(slug),
            "export_ready": export_ready(slug),
        })
    return {
        "environment": environment_info(),
        "projects": projects,
    }

@app.post("/api/projects")
def new_project(req: ProjectCreate):
    if not req.name.strip():
        raise HTTPException(400, "Project name is required")
    return create_project(req.name)

@app.get("/api/projects/{slug}")
def get_project(slug: str):
    try:
        meta = load_project(slug)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")
    return {
        **meta,
        "sources": inspect_sources(slug),
        "dataset_ready": dataset_ready(slug),
        "model_ready": model_ready(slug),
        "latest_step": latest_model_step(slug),
        "export_ready": export_ready(slug),
    }

@app.post("/api/projects/{slug}/upload")
async def upload_sources(slug: str, files: list[UploadFile] = File(...)):
    try:
        load_project(slug)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")

    target_dir = project_dir(slug) / "sources"
    saved = []
    for upload in files:
        name = safe_filename(upload.filename or "audio.wav")
        if not name.lower().endswith(".wav"):
            raise HTTPException(400, f"{name}: only WAV is accepted in v1")
        target = target_dir / name
        base_stem = target.stem
        suffix = target.suffix
        i = 2
        while target.exists():
            target = target_dir / f"{base_stem}-{i}{suffix}"
            i += 1
        with target.open("wb") as f:
            while chunk := await upload.read(1024 * 1024):
                f.write(chunk)
        saved.append(target.name)
    return {"saved": saved, "sources": inspect_sources(slug)}

@app.post("/api/projects/{slug}/render-upload")
async def upload_render_source(slug: str, file: UploadFile = File(...)):
    try:
        load_project(slug)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")
    name = safe_filename(file.filename or "render-source.wav")
    if not name.lower().endswith(".wav"):
        raise HTTPException(400, "Render input must be WAV")
    target = project_dir(slug) / "incoming" / name
    with target.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    return {"filename": target.name}

@app.post("/api/prepare")
def prepare(req: ProjectRequest):
    if not inspect_sources(req.project)["files"]:
        raise HTTPException(400, "Add WAV files first")
    job = JOBS.launch("prepare", prepare_command(req.project))
    return job.as_dict()

@app.post("/api/train")
def train(req: TrainRequest):
    if not dataset_ready(req.project):
        raise HTTPException(400, "Prepare the dataset first")
    steps = min(max(int(req.steps), 1000), 500000)
    batch_size = min(max(int(req.batch_size), 1), 128)
    job = JOBS.launch("train", train_command(req.project, steps, batch_size))
    return job.as_dict()

@app.post("/api/export")
def export(req: ProjectRequest):
    if not model_ready(req.project):
        raise HTTPException(400, "Train a checkpoint first")
    job = JOBS.launch("export", export_command(req.project))
    return job.as_dict()

@app.post("/api/render")
def render(req: RenderRequest):
    if not model_ready(req.project):
        raise HTTPException(400, "Train a checkpoint first")
    incoming = project_dir(req.project) / "incoming" / Path(req.filename).name
    if not incoming.exists():
        raise HTTPException(404, "Render source not found")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output = project_dir(req.project) / "renders" / f"{incoming.stem}-ddsp-{stamp}.wav"
    cmd = render_command(
        req.project,
        incoming,
        output,
        pitch_semitones=req.pitch_semitones,
        harmonic_gain=req.harmonic_gain,
        noise_gain=req.noise_gain,
        reverb=req.reverb,
    )
    job = JOBS.launch("render", cmd)
    job.lines.append(f"[output] {output}")
    return {**job.as_dict(), "output_name": output.name}

@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.as_dict()

@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.stop()
    return job.as_dict()

@app.get("/api/projects/{slug}/incoming")
def list_incoming(slug: str):
    try:
        load_project(slug)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")
    base = project_dir(slug) / "incoming"
    base.mkdir(parents=True, exist_ok=True)
    return [{"name": p.name, "size_bytes": p.stat().st_size} for p in sorted(base.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)]

@app.get("/api/projects/{slug}/renders")
def list_renders(slug: str):
    base = project_dir(slug) / "renders"
    return [{"name": p.name, "size_bytes": p.stat().st_size} for p in sorted(base.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)]

@app.get("/api/projects/{slug}/renders/{name}")
def get_render(slug: str, name: str):
    path = project_dir(slug) / "renders" / Path(name).name
    if not path.exists():
        raise HTTPException(404, "Render not found")
    return FileResponse(path, media_type="audio/wav", filename=path.name)

@app.get("/api/projects/{slug}/source/{name}")
def get_source(slug: str, name: str):
    path = project_dir(slug) / "sources" / Path(name).name
    if not path.exists():
        raise HTTPException(404, "Source not found")
    return FileResponse(path, media_type="audio/wav")

@app.get("/api/projects/{slug}/export.zip")
def get_export(slug: str):
    base = project_dir(slug)
    export_dir = base / "exports" / "tflite"
    if not export_dir.exists() or not any(export_dir.rglob("*.tflite")):
        raise HTTPException(404, "No completed TFLite export")
    zip_path = base / "exports" / f"{slug}-experimental-tflite.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in export_dir.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(Path(slug) / p.relative_to(export_dir)))
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)

@app.get("/api/projects/{slug}/model-bundle.zip")
def get_model_bundle(slug: str):
    try:
        meta = load_project(slug)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")
    if not model_ready(slug):
        raise HTTPException(404, "No trained checkpoint yet")
    base = project_dir(slug)
    zip_path = base / "exports" / f"{slug}-voice-model-checkpoints.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        project_json = base / "project.json"
        if project_json.exists():
            z.write(project_json, arcname=str(Path(slug) / "project.json"))
        model_dir = base / "model"
        for p in model_dir.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(Path(slug) / "model" / p.relative_to(model_dir)))
        manifest = {
            "project": meta.get("name", slug),
            "slug": slug,
            "contains": "DDSP checkpoints + operative gin config",
            "training_audio_included": False,
        }
        z.writestr(str(Path(slug) / "BUNDLE_MANIFEST.json"), json.dumps(manifest, indent=2))
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)

app.mount("/static", StaticFiles(directory=STATIC), name="static")

@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")

def run():
    ensure_home()
    host = "127.0.0.1"
    port = int(os.environ.get("DDSP_VOICE_LAB_PORT", "8766"))
    print(f"Surfwave Voice Lab: http://{host}:{port}")
    if os.environ.get("SURFWAVE_EMBEDDED") != "1":
        try:
            import threading
            threading.Timer(0.8, lambda: webbrowser.open(f"http://{host}:{port}")).start()
        except Exception:
            pass
    uvicorn.run(app, host=host, port=port, log_level="warning")
