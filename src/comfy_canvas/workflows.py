"""Small pure-JSON analysis layer; actual conversions use the real frontend."""
import copy
import json
from pathlib import Path
from typing import Literal

from .config import write_json
from .upstream import mcp


def load(value):
    if isinstance(value, str):
        return json.loads(Path(value).expanduser().read_text(encoding="utf-8"))
    return copy.deepcopy(value)


def structure(graph):
    if "nodes" in graph:
        nodes = {str(n["id"]): n for n in graph["nodes"]}
        links = []
        for item in graph.get("links", []):
            if isinstance(item, list):
                links.append((str(item[1]), item[2], str(item[3]), item[4]))
            else:
                links.append((str(item["origin_id"]), item["origin_slot"], str(item["target_id"]), item["target_slot"]))
        return nodes, links, "ui"
    graph = graph.get("output", graph.get("prompt", graph))
    nodes = {str(k): v for k, v in graph.items() if isinstance(v, dict) and "class_type" in v}
    links = [(str(value[0]), value[1], key, name) for key, node in nodes.items()
             for name, value in node.get("inputs", {}).items()
             if isinstance(value, list) and len(value) == 2 and str(value[0]) in nodes and isinstance(value[1], int)]
    return nodes, links, "api"


def analyze(graph):
    nodes, links, fmt = structure(graph)
    used = {edge[0] for edge in links} | {edge[2] for edge in links}
    types = sorted({n.get("type", n.get("class_type")) for n in nodes.values()})
    candidates = []
    for key, node in nodes.items():
        values = node.get("widgets_values", []) if fmt == "ui" else list(node.get("inputs", {}).values())
        for value in values:
            if isinstance(value, str) and value.lower().endswith((".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".bin")):
                candidates.append({"node_id": key, "filename": value})
    return {"format": fmt, "node_count": len(nodes), "link_count": len(links), "node_types": types,
            "isolated": sorted(set(nodes) - used), "model_references": candidates,
            "subgraphs": graph.get("definitions", {}).get("subgraphs", []),
            "note": "Model references are filename candidates, not proven architecture/compatibility."}


def diff(left, right):
    a, al, af = structure(left)
    b, bl, bf = structure(right)
    changed, layout = [], []
    visual = {"pos", "size", "color", "bgcolor", "title", "order"}
    for key in a.keys() & b.keys():
        fields = sorted(k for k in a[key].keys() | b[key].keys() if a[key].get(k) != b[key].get(k))
        if not fields:
            continue
        (layout if set(fields) <= visual else changed).append({"id": key, "fields": fields})
    return {"formats": [af, bf], "added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()),
            "logic_changed": changed, "presentation_changed": layout,
            "links_added": sorted(set(bl) - set(al), key=str), "links_removed": sorted(set(al) - set(bl), key=str),
            "groups_changed": left.get("groups") != right.get("groups"),
            "subgraphs_changed": left.get("definitions") != right.get("definitions")}


def slice_graph(graph, ids, direction):
    nodes, links, fmt = structure(graph)
    selected = set(map(str, ids))
    missing = selected - nodes.keys()
    if missing:
        raise ValueError(f"Unknown nodes: {sorted(missing)}")
    if direction != "exact":
        while True:
            previous = set(selected)
            for source, _, target, _ in links:
                if direction in ("upstream", "both") and target in selected:
                    selected.add(source)
                if direction in ("downstream", "both") and source in selected:
                    selected.add(target)
            if selected == previous:
                break
    if fmt == "api":
        # Exact/downstream slices retain unresolved references explicitly, not fake values.
        result = {k: v for k, v in nodes.items() if k in selected}
        return result
    result = copy.deepcopy(graph)
    result["nodes"] = [n for n in result["nodes"] if str(n["id"]) in selected]
    result["links"] = [link for link in result.get("links", []) if
                       str(link[1] if isinstance(link, list) else link["origin_id"]) in selected and
                       str(link[3] if isinstance(link, list) else link["target_id"]) in selected]
    kept_links = {link[0] if isinstance(link, list) else link["id"] for link in result["links"]}
    for node in result["nodes"]:
        for slot in node.get("inputs", []):
            if slot.get("link") not in kept_links:
                slot["link"] = None
        for slot in node.get("outputs", []):
            slot["links"] = [link for link in (slot.get("links") or []) if link in kept_links]
    return result


@mcp.tool()
async def workflow_tools(action: Literal["analyze", "inventory", "diff", "slice", "strip", "flatten", "convert"], source: dict | str, other: dict | str | None = None, node_ids: list[str | int] | None = None, direction: Literal["exact", "upstream", "downstream", "both"] = "upstream", output_path: str | None = None, target_format: Literal["ui", "api"] = "ui", client_id: str | None = None) -> dict:
    """Analyze/diff workflow JSON or local filenames. Slice selects IDs and traverses
    links; strip keeps upstream of explicit output node_ids (no guessed outputs).
    flatten/convert use a NEW browser tab and actual frontend graph-to-prompt; UI
    reconstruction loses old layout/groups/notes, and may reject unknown node types.
    Source files are never overwritten. API slices may have external dependencies.
    """
    graph = load(source)
    if action in ("analyze", "inventory"):
        return analyze(graph)
    if action == "diff":
        return diff(graph, load(other))
    if action in ("slice", "strip"):
        if not node_ids:
            raise ValueError("node_ids required; specify the intended output branch for strip")
        result = slice_graph(graph, node_ids, "upstream" if action == "strip" else direction)
    else:
        from .canvas import call
        await call("workflow", {"action": "new"}, client_id)
        await call("workflow", {"action": "load", "graph": graph}, client_id)
        exported = (await call("workflow", {"action": "export"}, client_id))["result"]
        result = exported["prompt"]["output"]
        if target_format == "ui":
            await call("workflow", {"action": "load", "graph": result}, client_id)
            result = (await call("read", {"mode": "full"}, client_id))["result"]["ui"]
    if output_path:
        path = Path(output_path).expanduser()
        if path.exists():
            raise FileExistsError("Choose a new output filename; source remains untouched")
        write_json(path, result)
        return {"path": str(path), "summary": analyze(result), "layout_reconstructed": action in ("flatten", "convert")}
    return {"workflow": result, "layout_reconstructed": action in ("flatten", "convert")}
