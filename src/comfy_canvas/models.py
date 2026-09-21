import hashlib
import importlib.util
import json
import os
import struct
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from . import jobs
from .config import settings, write_json
from .upstream import mcp

EXTENSIONS = {".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".bin"}


def catalog_path():
    return Path(settings().get("model_catalog", "~/.local/share/hermes-comfyui-models/catalog.jsonl")).expanduser()


def records():
    path = catalog_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def model_path(value):
    root = Path(settings()["root"]) / "models"
    path = Path(value).expanduser()
    path = path if path.is_absolute() else root / path
    path.resolve().relative_to(root.resolve())
    return path


def inspect(path, hash_file=False):
    path = model_path(path)
    result = {"path": str(path), "bytes": path.stat().st_size}
    if path.suffix == ".safetensors":
        with path.open("rb") as stream:
            size = struct.unpack("<Q", stream.read(8))[0]
            if size > min(path.stat().st_size - 8, 100 * 1024 * 1024):
                raise ValueError("Invalid/oversized Safetensors header")
            header = json.loads(stream.read(size))
        result.update(metadata=header.pop("__metadata__", {}), tensor_count=len(header),
                      tensor_sample=dict(list(header.items())[:40]))
    if hash_file:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        result["sha256"] = digest.hexdigest()
    sidecar = path.parent / "_hermes" / (path.name + ".json")
    if sidecar.exists():
        result["record"] = json.loads(sidecar.read_text())
    return result


def record(path, metadata):
    info = inspect(path)
    previous = info.get("record", {})
    value = {**previous, **metadata, "final_path": str(model_path(path)), "bytes": info["bytes"],
             "recorded_at": datetime.now(timezone.utc).isoformat()}
    destination = model_path(path)
    write_json(destination.parent / "_hermes" / (destination.name + ".json"), value)
    target = catalog_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
    return value


def execute(action, path=None, destination=None, metadata=None, query="", expected=None):
    root = Path(settings()["root"]) / "models"
    if action == "hash":
        data = inspect(path, True)
        record(path, {"sha256": data["sha256"]})
        return data
    if action == "inspect":
        return inspect(path)
    if action == "scan":
        files = [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size} for p in root.rglob("*")
                 if p.is_file() and p.suffix.lower() in EXTENSIONS and query.lower() in str(p).lower()]
        return {"categories": sorted(p.name for p in root.iterdir() if p.is_dir()), "files": files}
    if action == "catalog":
        return {"path": str(catalog_path()), "records": [r for r in records() if query.lower() in json.dumps(r, ensure_ascii=False).lower()]}
    if action in ("write_metadata", "classify"):
        if not metadata or not metadata.get("evidence"):
            raise ValueError("Research unknown models first; supply evidence, family, author and component metadata")
        return record(path, metadata)
    if action in ("move", "rename"):
        source, target = model_path(path), model_path(destination)
        category = target.relative_to(root).parts[0]
        if not (root / category).is_dir():
            raise ValueError("Use an existing ComfyUI top-level model category")
        if target.exists():
            raise FileExistsError(str(target))
        original = inspect(source).get("record", {})
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        value = record(target, {**original, **(metadata or {}), "previous_path": str(source), "event": action})
        return {"record": value, "warning": "Saved workflow filenames were NOT rewritten. Update their references using this rename map."}
    if action == "find_duplicates":
        latest = {r.get("final_path"): r for r in records()}
        by_hash = defaultdict(list)
        for filename, item in latest.items():
            if filename and item.get("sha256") and Path(filename).is_file():
                by_hash[item["sha256"]].append(filename)
        sizes = defaultdict(list)
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in EXTENSIONS:
                sizes[p.stat().st_size].append(str(p))
        return {"recorded_hash_matches": [v for v in by_hash.values() if len(v) > 1],
                "size_candidates_unverified": [v for v in sizes.values() if len(v) > 1],
                "note": "Rehash candidates before any deletion. This action deletes nothing."}
    if action == "verify_family":
        return {"components": [{"path": item, "present": model_path(item).is_file()} for item in (expected or [])],
                "note": "Expected components come from researched model/workflow documentation, not filename guesses."}
    raise ValueError(action)


@mcp.tool()
async def model_catalog(action: Literal["scan", "catalog", "inspect", "hash", "classify", "rename", "move", "write_metadata", "find_duplicates", "verify_family", "job", "cancel"], path: str | None = None, destination: str | None = None, metadata: dict | None = None, query: str = "", expected: list[str] | None = None, job_id: str | None = None) -> dict:
    """Manage models in existing ComfyUI categories; reuse Hermes _hermes sidecars
    and catalog.jsonl, not a second database. Paths relative to models or absolute.
    metadata: family, author, component, version, precision, evidence, description,
    source_ref, license, compatible_families. Unknown models MUST be researched online
    before classification/renaming. hash runs in an independent worker; poll job.
    Downloads use the official download_model tool, including direct URLs.
    Renames never silently change saved workflows.
    """
    if action in ("job", "cancel"):
        return jobs.status(job_id, action == "cancel")
    args = dict(action=action, path=path, destination=destination, metadata=metadata, query=query, expected=expected)
    if action == "hash":
        return jobs.start("model", args)
    return execute(**args)
