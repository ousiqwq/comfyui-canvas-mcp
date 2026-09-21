import os
import shutil
import tarfile
import uuid
from pathlib import Path
from typing import Literal

from . import jobs
from .config import run, settings, state_dir, write_json
from .upstream import mcp


def status(path):
    result = {"path": str(path), "symlink": path.is_symlink()}
    if (path / ".git").exists():
        result.update(commit=run(["git", "-C", path, "rev-parse", "HEAD"]),
                      changes=run(["git", "-C", path, "status", "--porcelain=v1"]))
    else:
        result["kind"] = "registry_or_plain_directory"
    return result


def package_path(package):
    if not package or Path(package).name != package or package in (".", ".."):
        raise ValueError("package must be a single custom_nodes folder name")
    return Path(settings()["root"]) / "custom_nodes" / package


def execute(action, package=None, checkpoint=None):
    config = settings()
    if action == "status":
        paths = [package_path(package)] if package else sorted((Path(config["root"]) / "custom_nodes").iterdir())
        return {"packages": [status(p) for p in paths if p.is_dir() and p.name != "__pycache__"]}
    if action == "checkpoint":
        path = package_path(package)
        folder = state_dir("node-packs") / uuid.uuid4().hex
        folder.mkdir()
        info = status(path)
        if path.is_symlink():
            # Preserve link identity; archive actual editable source too.
            info["target"] = str(path.resolve())
        with tarfile.open(folder / "package.tar", "w") as archive:
            archive.add(path.resolve(), arcname="package")
        write_json(folder / "manifest.json", info)
        return {"checkpoint": folder.name, **info}
    if action == "rollback":
        import json
        folder = state_dir("node-packs") / Path(checkpoint).name
        info = json.loads((folder / "manifest.json").read_text())
        target = Path(info.get("target", info["path"]))
        if target != package_path(package).resolve():
            raise ValueError("Checkpoint belongs to a different package")
        staging = folder / ("restore-" + uuid.uuid4().hex)
        staging.mkdir()
        with tarfile.open(folder / "package.tar") as archive:
            archive.extractall(staging, filter="data")
        previous = target.with_name(target.name + ".before-restore-" + uuid.uuid4().hex[:8])
        target.rename(previous)
        (staging / "package").rename(target)
        return {"restored": str(target), "reverse_backup": str(previous), "note": "Shared Python dependencies were NOT rolled back; use an environment snapshot for that."}
    mapped = {"repair": "fix"}.get(action, action)
    if mapped not in {"install", "update", "uninstall", "enable", "disable", "reinstall", "fix"}:
        raise ValueError(action)
    if not package:
        raise ValueError("Specify one package; this tool does not update all")
    if action in ("update", "uninstall", "reinstall", "repair"):
        # Existing folders get a code checkpoint; registry IDs/URLs may differ.
        if Path(package).name == package and package_path(package).is_dir():
            backup = execute("checkpoint", package)
        else:
            backup = {"note": "Package folder not resolved; create environment snapshot before dependency changes."}
    else:
        backup = None
    env = os.environ.copy()
    runtime = Path(config["runtime_python"]).parent.parent
    env.update(CONDA_PREFIX=str(runtime), VIRTUAL_ENV="", PATH=str(runtime / "bin") + os.pathsep + env["PATH"])
    return {"output": run([config["comfy_bin"], "--workspace", config["root"], "--skip-prompt", "node", mapped, package], cwd=config["root"], env=env, timeout=3600), "checkpoint": backup,
            "runtime_python": config["runtime_python"], "restart_required": True}


@mcp.tool()
async def node_pack_manage(action: Literal["status", "install", "update", "uninstall", "enable", "disable", "reinstall", "repair", "checkpoint", "rollback", "job", "cancel"], package: str | None = None, checkpoint: str | None = None, job_id: str | None = None) -> dict:
    """Single-package Manager/CLI operations in ComfyUI runtime, not tools Python.
    status is read-only. Changes run as independent jobs; poll job_id. Code checkpoints
    preserve dirty and untracked files; rollback keeps a reverse backup. Registry
    packages are not assumed to be Git repos. Dependency repairs may affect shared
    torch/CUDA: inspect impact and use a restorable environment snapshot as needed.
    """
    if action in ("job", "cancel"):
        return jobs.status(job_id, action == "cancel")
    if action == "status":
        return execute(action, package)
    return jobs.start("node_pack", dict(action=action, package=package, checkpoint=checkpoint))
