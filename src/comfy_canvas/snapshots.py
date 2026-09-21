import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from . import jobs
from .client import request
from .config import run, settings, state_dir, write_json
from .upstream import mcp


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def manifest():
    config = settings()
    root = Path(config["root"])
    def git(path):
        if not (path / ".git").exists():
            return None
        return {"commit": run(["git", "-C", path, "rev-parse", "HEAD"]),
                "changes": run(["git", "-C", path, "status", "--porcelain=v1"])}
    return {"created": datetime.now(timezone.utc).isoformat(), "url": config["url"], "root": str(root), "git": git(root),
            "node_packs": {p.name: git(p) for p in (root / "custom_nodes").iterdir() if p.is_dir()},
            "runtime_packages": run([config["runtime_python"], "-m", "pip", "freeze"], timeout=120),
            "tools_packages": run([sys.executable, "-m", "pip", "freeze"], timeout=120),
            "service": config["service"], "hermes_service": config["hermes_service"],
            "unit": run(["systemctl", "--user", "cat", config["service"]]),
            "tools_python": sys.executable, "archives": [], "restorable": False,
            "excludes": ["model weights", "input/output media", "Hermes conversation database"],
            "note": "Same host/architecture and absolute paths only. Manifest alone cannot restore installed files."}


def create(mode="manifest", scopes=None):
    config = settings()
    folder = state_dir("snapshots") / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    folder.mkdir(mode=0o700)
    data = manifest()
    write_json(folder / "manifest.json", data)
    if mode == "manifest":
        return {"snapshot": folder.name, "path": str(folder), "restorable": False}
    scopes = scopes or ["code", "runtime", "tools", "bridge"]
    root = Path(config["root"])
    targets = {"code": (root, ["models", "input", "output", ".hermes-model-intake"]),
               "runtime": (Path(config["runtime_python"]).parent.parent, []),
               "tools": (Path(sys.executable).parent.parent, []),
               "bridge": (Path(__file__).resolve().parents[2], [])}
    if any(s not in targets for s in scopes):
        raise ValueError(f"scopes must be {list(targets)}")
    queue = request("/queue")
    if queue.get("queue_running") or queue.get("queue_pending"):
        raise RuntimeError("Queue is not empty; create restorable snapshot in an idle window")
    total = 0
    for scope in scopes:
        target, exclude = targets[scope]
        if folder.resolve().is_relative_to(target.resolve()):
            raise ValueError("Snapshot storage must be outside every archived target")
        for directory, dirs, files in os.walk(target):
            if Path(directory) == target:
                dirs[:] = [d for d in dirs if d not in exclude]
            total += sum((Path(directory) / f).lstat().st_size for f in files)
    if shutil.disk_usage(folder).free < total * 1.1:
        raise RuntimeError(f"Need approximately {total} archive bytes plus 10% space")
    # The independent worker survives the gateway being stopped.
    services = [config["service"], config["hermes_service"]]
    active = [s for s in services if subprocess.run(["systemctl", "--user", "is-active", "--quiet", s]).returncode == 0]
    try:
        for service in active:
            run(["systemctl", "--user", "stop", service])
        for scope in scopes:
            target, exclude = targets[scope]
            archive = folder / f"{scope}.tar"
            def keep(member):
                relative = Path(member.name).parts
                return None if len(relative) > 1 and relative[1] in exclude else member
            with tarfile.open(archive, "w", dereference=False) as stream:
                stream.add(target, arcname="payload", filter=keep)
            data["archives"].append({"file": archive.name, "sha256": sha256(archive), "target": str(target), "preserve_children": exclude})
            write_json(folder / "manifest.json", data)
        unit_dir = folder / "user-units"
        unit_dir.mkdir()
        units = Path.home() / ".config/systemd/user"
        for name in (config["service"], config["service"] + ".d"):
            source = units / name
            if source.is_dir():
                shutil.copytree(source, unit_dir / name)
            elif source.exists():
                shutil.copy2(source, unit_dir / name)
        hermes = Path.home() / ".hermes/config.yaml"
        if hermes.exists():
            import yaml
            entry = yaml.safe_load(hermes.read_text()).get("mcp_servers", {}).get("comfyui")
            write_json(folder / "hermes-mcp.json", entry)
        # Self-contained stdlib restore program is copied outside replaced environments.
        shutil.copy2(Path(__file__).resolve().parents[2] / "scripts/restore.py", folder / "restore.py")
        data["restorable"] = True
        data["scopes"] = scopes
        write_json(folder / "manifest.json", data)
    finally:
        for service in active:
            run(["systemctl", "--user", "start", service])
    return {"snapshot": folder.name, "path": str(folder), "restorable": True, "scopes": scopes}


def restore_cli():
    import argparse
    parser = argparse.ArgumentParser(description="Restore an explicitly selected local snapshot")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    script = args.snapshot / "restore.py"
    os.execv("/usr/bin/python3", ["python3", str(script), str(args.snapshot), *( ["--apply"] if args.apply else [])])


@mcp.tool()
async def environment_snapshot(action: Literal["create", "list", "inspect", "diff", "restore_plan", "restore", "job", "cancel"], snapshot: str | None = None, mode: Literal["manifest", "restorable"] = "manifest", scopes: list[Literal["code", "runtime", "tools", "bridge"]] | None = None, job_id: str | None = None) -> dict:
    """Manifest = version inventory only. Restorable = actual tar archives of selected
    code/runtime/tools/bridge, streamed SHA-256, private units and MCP config. No model
    weights or media. Requires idle queue; stops then restarts user services during
    capture. Worker is independent. restore runs a stdlib helper outside target envs,
    preserves current trees as reverse backups and merges only Hermes's comfyui entry.
    Use restore_plan to inspect exact targets first; jobs can survive MCP restarts.
    """
    if action in ("job", "cancel"):
        return jobs.status(job_id, action == "cancel")
    folder = state_dir("snapshots")
    if action == "list":
        return {"snapshots": [p.parent.name for p in sorted(folder.glob("*/manifest.json"), reverse=True)]}
    if action == "create":
        return jobs.start("snapshot", dict(mode=mode, scopes=scopes))
    folder /= Path(snapshot).name
    saved = json.loads((folder / "manifest.json").read_text())
    if action == "inspect":
        return saved
    if action == "diff":
        current = manifest()
        return {k: {"saved": v, "current": current.get(k)} for k, v in saved.items() if k in current and v != current[k]}
    command = ["/usr/bin/python3", str(folder / "restore.py"), str(folder)]
    if action == "restore_plan":
        return {"targets": saved["archives"], "restorable": saved["restorable"], "command": command + ["--apply"]}
    if not saved["restorable"]:
        raise ValueError("This is a manifest, not a restorable archive")
    log = folder / "restore.log"
    unit = "comfy-canvas-restore-" + uuid.uuid4().hex
    run(["systemd-run", "--user", "--collect", "--unit", unit, "--property=UMask=0077",
         f"--property=StandardOutput=append:{log}", f"--property=StandardError=append:{log}", *command, "--apply"])
    return {"unit": unit, "log": str(log), "result": str(folder / "restore-result.json"), "note": "Read result file after MCP reconnects."}
