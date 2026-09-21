"""Disk-backed, independent workers for downloads, hashing and environment archives."""
import json
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path

from .config import state_dir, write_json


def start(kind, args):
    job_id = uuid.uuid4().hex
    folder = state_dir("jobs") / job_id
    folder.mkdir(mode=0o700)
    write_json(folder / "request.json", {"kind": kind, "args": args})
    unit = "comfy-canvas-job-" + job_id
    arguments = ["systemd-run", "--user", "--collect", "--unit", unit,
                 "--property=UMask=0077", f"--property=StandardOutput=append:{folder / 'log.txt'}",
                 f"--property=StandardError=append:{folder / 'log.txt'}"]
    for key in ("COMFY_CANVAS_CONFIG", "COMFY_BIN", "COMFY_LOCAL_URL"):
        if key in os.environ:
            arguments.append(f"--setenv={key}={os.environ[key]}")
    subprocess.run(arguments + [sys.executable, "-m", "comfy_canvas.jobs", str(folder)], check=True, capture_output=True)
    write_json(folder / "process.json", {"unit": unit})
    return {"job_id": job_id, "status": "started", "log": str(folder / "log.txt")}


def status(job_id, cancel=False):
    folder = state_dir("jobs") / Path(job_id).name
    if (folder / "result.json").exists():
        return json.loads((folder / "result.json").read_text())
    if cancel:
        unit = json.loads((folder / "process.json").read_text())["unit"]
        if unit != "comfy-canvas-job-" + job_id:
            raise ValueError("Invalid job identity")
        subprocess.run(["systemctl", "--user", "stop", unit], check=True)
        write_json(folder / "result.json", {"status": "cancelled", "note": "Completed external side effects remain; inspect before retrying."})
        return {"status": "cancelled"}
    process = json.loads((folder / "process.json").read_text())
    alive = subprocess.run(["systemctl", "--user", "is-active", "--quiet", process["unit"]]).returncode == 0
    log = folder / "log.txt"
    return {"job_id": job_id, "status": "running" if alive else "interrupted", "log": log.read_text()[-8000:] if log.exists() else ""}


def worker(folder):
    def cancelled(signum, frame):
        raise InterruptedError("Job cancelled; completed side effects are not undone")
    signal.signal(signal.SIGTERM, cancelled)
    data = json.loads((folder / "request.json").read_text())
    try:
        if data["kind"] == "model":
            from .models import execute
        elif data["kind"] == "node_pack":
            from .nodepacks import execute
        elif data["kind"] == "snapshot":
            from .snapshots import create
            execute = create
        else:
            raise ValueError("Unknown worker kind")
        result = execute(**data["args"])
        write_json(folder / "result.json", {"status": "success", "result": result})
    except Exception as exc:
        write_json(folder / "result.json", {"status": "failed", "error": str(exc)})
        raise


if __name__ == "__main__":
    worker(Path(sys.argv[1]))
