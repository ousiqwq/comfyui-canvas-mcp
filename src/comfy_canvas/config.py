import json
import os
import subprocess
from pathlib import Path


def settings():
    path = Path(os.environ.get("COMFY_CANVAS_CONFIG", "~/.config/comfyui-canvas-mcp/config.json")).expanduser()
    data = json.loads(path.read_text()) if path.exists() else {}
    data.setdefault("url", os.environ.get("COMFY_LOCAL_URL", "http://127.0.0.1:8188"))
    data.setdefault("root", "~/git/ComfyUI")
    data.setdefault("state", "~/.local/share/comfyui-canvas-mcp")
    data.setdefault("service", "comfyui.service")
    data.setdefault("hermes_service", "hermes-gateway.service")
    data.setdefault("runtime_python", "~/miniconda3/envs/ComfyUI/bin/python")
    data.setdefault("comfy_bin", os.environ.get("COMFY_BIN", "comfy"))
    for key in ("root", "state", "runtime_python"):
        data[key] = str(Path(data[key]).expanduser().resolve())
    return data


def run(args, *, cwd=None, timeout=120, env=None):
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {result.stderr[-6000:] or result.stdout[-6000:]}")
    return result.stdout.strip()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def state_dir(category):
    path = Path(settings()["state"]) / category
    path.mkdir(parents=True, exist_ok=True)
    return path
