#!/usr/bin/env python3
"""Standalone, stdlib-only, same-path restore. Run outside replaced environments."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import time
import uuid
from pathlib import Path
from urllib.request import urlopen


def run(args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def restore(folder, apply=False):
    data = json.loads((folder / "manifest.json").read_text())
    if not data.get("restorable"):
        raise ValueError("Manifest only: no restorable archive")
    entries = data["archives"]
    for entry in entries:
        target = Path(entry["target"])
        if not target.is_absolute() or target in (Path("/"), Path.home(), Path("/home")):
            raise ValueError(f"Invalid broad restore target: {target}")
        archive = folder / Path(entry["file"]).name
        if digest(archive) != entry["sha256"]:
            raise ValueError(f"Archive checksum mismatch: {archive}")
    if not apply:
        return {"verified": True, "targets": entries, "apply": False}
    suffix = uuid.uuid4().hex[:8]
    staged, swapped = [], []
    for entry in entries:
        target = Path(entry["target"])
        staging = target.with_name(target.name + ".staged-restore-" + suffix)
        staging.mkdir()
        # Only local, verified archives made by this package. Preserve Conda symlinks.
        with tarfile.open(folder / entry["file"]) as archive:
            for member in archive.getmembers():
                relative = Path(member.name)
                if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "payload":
                    raise ValueError("Invalid archive member")
            archive.extractall(staging, filter="fully_trusted")
        staged.append((entry, staging / "payload"))
    services = [s for s in [data.get("service"), data.get("hermes_service")] if s]
    active = [s for s in services if subprocess.run(["systemctl", "--user", "is-active", "--quiet", s]).returncode == 0]
    try:
        for service in active:
            run(["systemctl", "--user", "stop", service])
        for entry, payload in staged:
            target = Path(entry["target"])
            previous = target.with_name(target.name + ".before-restore-" + suffix)
            moved = []
            for name in entry.get("preserve_children", []):
                if (target / name).exists() or (target / name).is_symlink():
                    (target / name).rename(payload / name)
                    moved.append(name)
            try:
                target.rename(previous)
                payload.rename(target)
            except Exception:
                if previous.exists() and not target.exists():
                    previous.rename(target)
                for name in moved:
                    if (payload / name).exists():
                        (payload / name).rename(target / name)
                raise
            swapped.append((entry, previous))
        units = folder / "user-units"
        if units.exists():
            destination = Path.home() / ".config/systemd/user"
            for source in units.iterdir():
                target = destination / source.name
                if target.exists():
                    target.rename(target.with_name(target.name + ".before-restore-" + suffix))
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
            run(["systemctl", "--user", "daemon-reload"])
        hermes_entry = folder / "hermes-mcp.json"
        if hermes_entry.exists():
            # Merge exactly one entry; never overwrite newer platform/provider settings.
            code = "import json,yaml,sys,shutil;from pathlib import Path;p=Path.home()/'.hermes/config.yaml';shutil.copy2(p,str(p)+'.before-canvas-restore');d=yaml.safe_load(p.read_text());d.setdefault('mcp_servers',{})['comfyui']=json.loads(Path(sys.argv[1]).read_text());p.write_text(yaml.safe_dump(d,sort_keys=False,allow_unicode=True))"
            run([data["tools_python"], "-c", code, str(hermes_entry)])
    except Exception:
        # Reverse tree swaps; previous data is retained even if a later health check fails.
        for entry, previous in reversed(swapped):
            target = Path(entry["target"])
            for name in entry.get("preserve_children", []):
                if (target / name).exists():
                    (target / name).rename(previous / name)
            target.rename(target.with_name(target.name + ".failed-restore-" + suffix))
            previous.rename(target)
        raise
    finally:
        for service in active:
            run(["systemctl", "--user", "start", service])
    health={}
    for service in active:
        health[service]=subprocess.run(["systemctl","--user","is-active","--quiet",service]).returncode==0
    if data.get('url') and data.get('service') in active:
        for _ in range(60):
            try:
                with urlopen(data['url'].rstrip('/')+'/system_stats',timeout=3) as response:
                    health['api']=response.status==200
                break
            except OSError:
                time.sleep(1)
        else:
            health['api']=False
    return {"status": "restored" if all(health.values()) else "restored_health_check_failed", "health":health,
            "reverse_backups": [str(p) for _, p in swapped], "services_restarted": active,
            "note": "Verify MCP handshake and intended workflows before deleting reverse backups."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = restore(args.snapshot.resolve(), args.apply)
    except Exception as error:
        result = {"status": "failed", "error": str(error)}
        (args.snapshot / "restore-result.json").write_text(json.dumps(result, indent=2))
        raise
    (args.snapshot / "restore-result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
