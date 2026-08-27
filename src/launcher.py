from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView

STUDIO_URL = "http://127.0.0.1:8765"
VOICE_URL = "http://127.0.0.1:8766"


def reachable(url: str, timeout: float = 0.35) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def wait_for(url: str, seconds: float = 25.0) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if reachable(url):
            return True
        time.sleep(0.25)
    return False


class SurfwaveView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        page = self.page()
        try:
            page.featurePermissionRequested.connect(self._permission_requested)
        except Exception:
            pass

    def _permission_requested(self, origin, feature):
        try:
            audio = QWebEnginePage.Feature.MediaAudioCapture
            if feature == audio:
                self.page().setFeaturePermission(origin, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)
            else:
                self.page().setFeaturePermission(origin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser)
        except Exception:
            pass


class MainWindow(QMainWindow):
    def __init__(self, suite_root: Path, owned_processes: list[subprocess.Popen]):
        super().__init__()
        self.suite_root = suite_root
        self.owned_processes = owned_processes
        self.setWindowTitle("Surfwave Studio")
        self.resize(1480, 940)
        self.setMinimumSize(1050, 700)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setMovable(False)

        self.studio = SurfwaveView()
        self.voice = SurfwaveView()
        self.studio.setUrl(QUrl(STUDIO_URL))
        self.voice.setUrl(QUrl(VOICE_URL))
        tabs.addTab(self.studio, "STUDIO")
        tabs.addTab(self.voice, "VOICE LAB")
        tabs.setTabToolTip(0, "Record, edit, mix, transform, and export project audio")
        tabs.setTabToolTip(1, "Train and use reusable DDSP timbre models")
        self.setCentralWidget(tabs)

        file_menu = self.menuBar().addMenu("File")
        open_songs = QAction("Open Song Projects", self)
        open_songs.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path.home() / "Music" / "SURFWAVE_STUDIO"))))
        file_menu.addAction(open_songs)
        open_models = QAction("Open Voice Models", self)
        open_models.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path.home() / "DDSPVoiceLab" / "projects"))))
        file_menu.addAction(open_models)
        open_logs = QAction("Open Surfwave Logs", self)
        open_logs.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path.home() / "Library" / "Application Support" / "Surfwave Studio" / "logs"))))
        file_menu.addAction(open_logs)
        file_menu.addSeparator()
        quit_action = QAction("Quit Surfwave Studio", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        self.statusBar().showMessage("SURFwave  •  Studio ready  •  Voice Lab ready")

    def closeEvent(self, event):
        if self.owned_processes:
            box = QMessageBox(self)
            box.setWindowTitle("Quit Surfwave Studio?")
            box.setText("Closing Surfwave Studio also stops its local audio services.")
            box.setInformativeText("If Voice Lab is actively training or rendering, leave Surfwave open until that job finishes.")
            stay = box.addButton("Keep Surfwave Open", QMessageBox.ButtonRole.RejectRole)
            quit_btn = box.addButton("Quit Surfwave", QMessageBox.ButtonRole.AcceptRole)
            box.setDefaultButton(stay)
            box.exec()
            if box.clickedButton() is not quit_btn:
                event.ignore()
                return
        event.accept()


def start_backend(cmd: list[str], cwd: Path, log_path: Path, env: dict[str, str]) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "a", buffering=1)
    kwargs = dict(cwd=str(cwd), env=env, stdout=log, stderr=subprocess.STDOUT)
    if hasattr(os, "setsid"):
        kwargs["preexec_fn"] = os.setsid
    return subprocess.Popen(cmd, **kwargs)


def stop_process(p: subprocess.Popen):
    if p.poll() is not None:
        return
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        else:
            p.terminate()
        p.wait(timeout=5)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Missing Surfwave runtime path")
    suite_root = Path(sys.argv[1]).expanduser().resolve()
    support = Path.home() / "Library" / "Application Support" / "Surfwave Studio"
    logs = support / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    studio_py = suite_root / "Studio" / ".venv" / "bin" / "python"
    voice_py = suite_root / "Voice Lab" / ".venv" / "bin" / "python"
    if not studio_py.exists() or not voice_py.exists():
        raise SystemExit("Surfwave runtime is not installed")

    env = os.environ.copy()
    env["SURFWAVE_EMBEDDED"] = "1"
    env["TF_ADDONS_PY_OPS"] = "1"
    env["TF_CPP_MIN_LOG_LEVEL"] = "1"

    owned: list[subprocess.Popen] = []
    if not reachable(STUDIO_URL):
        owned.append(start_backend([str(studio_py), "server.py"], suite_root / "Studio", logs / "studio.log", env))
    if not reachable(VOICE_URL):
        owned.append(start_backend([str(voice_py), "app.py"], suite_root / "Voice Lab", logs / "voice_lab.log", env))

    if not wait_for(STUDIO_URL) or not wait_for(VOICE_URL):
        for p in owned:
            stop_process(p)
        raise SystemExit(f"Surfwave services did not start. Check {logs}")

    app = QApplication(sys.argv)
    app.setApplicationName("Surfwave Studio")
    app.setOrganizationName("Surfwave")
    app.setQuitOnLastWindowClosed(True)
    app_icon = Path(__file__).resolve().parent / "Brand" / "icons" / "surfwave-app-icon-512.png"
    if app_icon.exists():
        app.setWindowIcon(QIcon(str(app_icon)))
    app.setStyleSheet("""
        QMainWindow, QTabWidget::pane { background: #141116; border: 0; }
        QTabWidget::pane { border-top: 1px solid #403742; }
        QTabBar { background: #18151a; }
        QTabBar::tab { background: #18151a; color: #918899; padding: 12px 24px 11px; border: 0; border-bottom: 2px solid transparent; font-weight: 700; letter-spacing: 1px; }
        QTabBar::tab:selected { background: #201b23; color: #f7f3f8; border-bottom: 2px solid #89b5cc; }
        QTabBar::tab:hover { color: #e2dce8; background: #211d24; }
        QStatusBar { background: #18151a; color: #8f8597; border-top: 1px solid #403742; }
    """)

    profile = QWebEngineProfile.defaultProfile()
    profile.setCachePath(str(support / "web-cache"))
    profile.setPersistentStoragePath(str(support / "web-data"))
    try:
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    except Exception:
        pass

    window = MainWindow(suite_root, owned)
    window.show()
    code = app.exec()
    for p in owned:
        stop_process(p)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
