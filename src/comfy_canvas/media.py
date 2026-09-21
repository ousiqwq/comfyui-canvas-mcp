import json
from pathlib import Path
from typing import Literal

from PIL import Image

from .config import run, write_json
from .upstream import mcp


def extract(path):
    path = Path(path).expanduser()
    tags = {}
    if path.suffix.lower() in (".png", ".webp", ".jpg", ".jpeg", ".tiff"):
        with Image.open(path) as image:
            tags.update({k: v for k, v in image.info.items() if isinstance(v, (str, bytes))})
            tags.update({str(k): v for k, v in image.getexif().items() if isinstance(v, (str, bytes))})
    else:
        probe = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "format_tags:stream_tags", "-of", "json", path]))
        tags.update(probe.get("format", {}).get("tags", {}))
        for stream in probe.get("streams", []):
            tags.update(stream.get("tags", {}))
    found = {}
    for key, value in tags.items():
        if isinstance(value, bytes):
            if value.startswith(b"UNICODE\0"):
                value=value[8:].decode("utf-16",errors="replace")
            else:
                value=value.removeprefix(b"ASCII\0\0\0").decode("utf-8",errors="replace").lstrip("\x00")
        for prefix in ("workflow:", "prompt:"):
            if value.startswith(prefix):
                value=value[len(prefix):].strip()
        try:
            data = json.loads(value)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        if "nodes" in data:
            found["workflow"] = data
        elif any(isinstance(v, dict) and "class_type" in v for v in data.values()):
            found["prompt"] = data
        for name in ("workflow", "prompt"):
            embedded = data.get(name)
            if isinstance(embedded, str):
                embedded = json.loads(embedded)
            if isinstance(embedded, dict):
                found[name] = embedded
    sidecar = path.with_suffix(path.suffix + ".json")
    if sidecar.exists() and not found:
        data = json.loads(sidecar.read_text())
        found = {"workflow" if "nodes" in data else "prompt": data}
    return {"path": str(path), "metadata_keys": sorted(tags), "found": found,
            "recoverable": bool(found), "note": "No workflow can be inferred from pixels alone."}


@mcp.tool()
async def workflow_media(action: Literal["inspect", "extract", "compare", "load_to_canvas"], path: str, output_path: str | None = None, client_id: str | None = None) -> dict:
    """Recover real workflow metadata from PNG/WebP/JPEG, video tags (ffprobe) or
    adjacent filename.ext.json. Does not decode video or invent missing workflows.
    load_to_canvas opens a new workflow tab, preserving the current one.
    """
    result = extract(path)
    if action == "inspect":
        return {**result, "found": list(result["found"])}
    if not result["found"]:
        return result
    graph = result["found"].get("workflow", result["found"].get("prompt"))
    if action == "compare":
        from .canvas import call
        from .workflows import diff
        current = (await call("read", {"mode": "full"}, client_id))["result"]["ui"]
        return diff(graph, current)
    if action == "load_to_canvas":
        from .canvas import call
        await call("workflow", {"action": "new"}, client_id)
        return await call("workflow", {"action": "load", "graph": graph}, client_id)
    if output_path:
        if Path(output_path).expanduser().exists():
            raise FileExistsError(output_path)
        write_json(Path(output_path).expanduser(), graph)
        return {"path": output_path, "metadata_keys": result["metadata_keys"]}
    return result
