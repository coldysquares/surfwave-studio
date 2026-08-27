from pathlib import Path
import os

APP_HOME = Path(os.environ.get("DDSP_VOICE_LAB_HOME", Path.home() / "DDSPVoiceLab")).expanduser()
PROJECTS_DIR = APP_HOME / "projects"

def ensure_home():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return APP_HOME
