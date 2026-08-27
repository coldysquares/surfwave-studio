from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from collections import deque

class Job:
    def __init__(self, kind: str, command: list[str], cwd: str | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.command = command
        self.cwd = cwd
        self.status = "queued"
        self.returncode = None
        self.created_at = time.time()
        self.started_at = None
        self.ended_at = None
        self.lines = deque(maxlen=1200)
        self.process = None
        self._thread = None

    def as_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "returncode": self.returncode,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "log": "\n".join(self.lines),
        }

    def start(self):
        def target():
            self.status = "running"
            self.started_at = time.time()
            env = os.environ.copy()
            env.setdefault("PYTHONUNBUFFERED", "1")
            try:
                self.process = subprocess.Popen(
                    self.command,
                    cwd=self.cwd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert self.process.stdout is not None
                for line in self.process.stdout:
                    self.lines.append(line.rstrip())
                self.returncode = self.process.wait()
                self.status = "done" if self.returncode == 0 else "failed"
            except Exception as e:
                self.lines.append(f"[launcher error] {e}")
                self.returncode = -1
                self.status = "failed"
            self.ended_at = time.time()

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self):
        if self.process and self.status == "running":
            self.lines.append("[requested stop]")
            self.process.terminate()
            self.status = "stopping"

class JobManager:
    def __init__(self):
        self.jobs = {}
        self.lock = threading.Lock()

    def launch(self, kind: str, command: list[str], cwd: str | None = None) -> Job:
        job = Job(kind, command, cwd)
        with self.lock:
            self.jobs[job.id] = job
        job.start()
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

JOBS = JobManager()
