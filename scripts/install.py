#!/usr/bin/env python3
"""Install the bridge link and optionally merge Hermes's one MCP entry."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-python", type=Path, required=True)
    parser.add_argument("--comfy-bin", type=Path, default=Path(sys.executable).parent / "comfy")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--service", default="comfyui.service")
    parser.add_argument("--hermes", action="store_true")
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    runtime = args.runtime_python.expanduser().absolute()
    project = Path(__file__).resolve().parent.parent
    if not (root / "main.py").is_file() or not runtime.is_file():
        raise ValueError("Check ComfyUI root and runtime Python")
    target = root / "custom_nodes/ComfyUI-Local-Canvas-Bridge"
    source = project / "comfyui_bridge"
    if target.exists() or target.is_symlink():
        if target.resolve() != source:
            raise FileExistsError(f"Existing different extension: {target}")
    else:
        target.symlink_to(source, target_is_directory=True)
    config = Path.home() / ".config/comfyui-canvas-mcp/config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if config.exists():
        shutil.copy2(config, config.with_name(config.name + ".before-" + stamp))
        data = json.loads(config.read_text())
    else:
        data = {}
    data.update(root=str(root), runtime_python=str(runtime), comfy_bin=str(args.comfy_bin.absolute()), url=args.url, service=args.service)
    config.write_text(json.dumps(data, indent=2))
    config.chmod(0o600)
    if args.hermes:
        path = Path.home() / ".hermes/config.yaml"
        backup = path.with_name("config.yaml.before-canvas-" + stamp)
        shutil.copy2(path, backup)
        backup.chmod(0o600)
        hermes = yaml.safe_load(path.read_text())
        entry = hermes.setdefault("mcp_servers", {}).setdefault("comfyui", {})
        entry.update(command=str(Path(sys.executable).parent / "comfy-mcp-local"), enabled=True, connect_timeout=120)
        entry.setdefault("env", {}).update(COMFY_BIN=data["comfy_bin"], COMFY_LOCAL_URL=args.url,
                                            CONDA_PREFIX=str(runtime.parent.parent), VIRTUAL_ENV="", COMFY_CANVAS_CONFIG=str(config))
        path.write_text(yaml.safe_dump(hermes, sort_keys=False, allow_unicode=True))
        print(f"Hermes entry merged; original config: {backup}")
    if args.restart:
        subprocess.run(["systemctl", "--user", "restart", args.service], check=True)
        if args.hermes:
            subprocess.run(["systemctl", "--user", "restart", "hermes-gateway.service"], check=True)
    print(f"Bridge: {target} -> {source}\nConfig: {config}\nReload the ComfyUI browser page once.")


if __name__ == "__main__":
    main()
