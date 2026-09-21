import asyncio
import base64
import json
import uuid
from pathlib import Path
from typing import Literal

from mcp.types import ImageContent, TextContent
from pydantic import BaseModel, ConfigDict, Field

from .client import command, request
from .config import state_dir, write_json
from .upstream import mcp

bound_client = None


class Operation(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    op: Literal["add", "remove", "clear", "edit", "move", "resize", "set_widget", "remove_widget", "set_property", "set_mode", "connect", "disconnect", "copy", "paste", "create_group", "move_group", "edit_group", "remove_group", "reroute_add", "reroute_move", "reroute_remove", "widget_to_input", "input_to_widget"]
    alias: str | None = Field(None, alias="as", description="Alias for a newly added node; use $alias in later operations")
    node_id: str | int | None = None
    node_ids: list[str | int] | None = None
    class_type: str | None = None
    pos: list[float] | None = None
    size: list[float] | None = None
    title: str | None = None
    widget: str | int | None = None
    value: object = None
    property: str | None = None
    from_node_id: str | int | None = None
    from_output: str | int | None = None
    to_node_id: str | int | None = None
    to_input: str | int | None = None
    group_id: str | int | None = None
    color: str | None = None
    mode: str | int | None = None


async def call(action, params=None, client_id=None, revision=None, timeout=60, request_id=None):
    result = await command(action, params, client_id or bound_client, revision, timeout, request_id)
    if not result.get("ok"):
        raise RuntimeError(result.get("error", str(result)))
    return result


@mcp.tool()
async def canvas_status(bind_client: str | None = None, unbind: bool = False, capabilities: bool = False) -> dict:
    """List actual browser canvases. Bind one client when multiple pages are open.
    capabilities=true returns live Panel action parameter signatures. No screenshots needed.
    Binding lasts for this MCP process; it never follows window focus automatically.
    """
    global bound_client
    status = await asyncio.to_thread(request, "/canvas-mcp/status")
    if unbind:
        bound_client = None
    if bind_client:
        if bind_client not in [c["client_id"] for c in status["clients"]]:
            raise ValueError("Client is not connected")
        bound_client = bind_client
    status["bound_client"] = bound_client
    if capabilities:
        status["capabilities"] = (await call("capabilities"))["result"]
    return status


@mcp.tool()
async def canvas_read(mode: Literal["outline", "full", "selected", "viewport", "errors", "node"] = "outline", ids: list[str | int] | None = None, types: list[str] | None = None, title: str | None = None, offset: int = 0, limit: int = 100, client_id: str | None = None) -> dict:
    """Read live graph IDs, precise graph-space pos/size/bounds, widgets, slots, links,
    groups, reroutes and viewport. full returns serialized UI JSON. errors reports
    frontend execution/validation errors. Use returned revision on subsequent edits.
    """
    return await call("read", dict(mode=mode, ids=ids, types=types, title=title, offset=offset, limit=limit), client_id)


@mcp.tool()
async def canvas_apply(operations: list[Operation], client_id: str | None = None, revision: str | None = None, request_id: str | None = None) -> dict:
    """Batch live edits in one undo group. Add uses class_type/pos/as; widget uses
    node_id/widget/value; connect uses from_node_id/from_output/to_node_id/to_input
    (slots may be names or indexes). Aliases use $name. Extra fields follow live
    canvas_status(capabilities=true) signatures. Read back after editing.
    Reuse request_id only to retrieve an uncertain request, not for a different edit.
    """
    return await call("apply", {"operations": [o.model_dump(by_alias=True, exclude_unset=True) for o in operations]}, client_id, revision, request_id=request_id)


@mcp.tool()
async def canvas_layout(action: Literal["auto", "snap", "align_x", "align_y", "distribute_x", "distribute_y", "relative", "collisions"] = "auto", node_ids: list[str | int] | None = None, dry_run: bool = False, options: dict | None = None, client_id: str | None = None, revision: str | None = None) -> dict:
    """Lay out real graph coordinates. options: grid, direction, spacing; relative:
    anchor_id, offset:[x,y]. Auto uses Panel's topology layout; fixed nodes stay fixed.
    dry_run previews moves. collisions reports overlapping node bounds.
    """
    return await call("layout", {**(options or {}), "action": action, "node_ids": node_ids, "dry_run": dry_run}, client_id, revision)


@mcp.tool()
async def canvas_subgraph(action: Literal["create", "from_group", "inspect", "enter", "exit", "unpack", "expose_input", "expose_output", "unexpose_input", "unexpose_output", "move_rail", "promote_widget", "save", "list", "add"], params: dict | None = None, client_id: str | None = None, revision: str | None = None) -> dict:
    """Panel native subgraphs, exposed sockets/widgets, boundary rails and reusable
    blueprints. Discover exact action parameters with canvas_status(capabilities=true).
    IDs refer to the currently viewed graph; re-read after entering/exiting.
    """
    return await call("subgraph", {**(params or {}), "action": action}, client_id, revision)


@mcp.tool()
async def canvas_workflow(action: Literal["list", "new", "open", "switch", "close", "rename", "save", "save_as", "load", "export", "checkpoint", "checkpoints", "inspect_checkpoint", "restore_checkpoint"], path: str | None = None, name: str | None = None, graph: dict | None = None, force: bool = False, client_id: str | None = None, revision: str | None = None) -> dict:
    """Manage browser workflow tabs and ComfyUI user storage. path is a workflow
    path, or checkpoint ID for inspect/restore. force permits closing unsaved work or
    overwriting an existing saved file. Checkpoints live on disk; restore saves a
    reverse checkpoint first. load accepts UI JSON or API prompt (layout reconstructed).
    """
    folder = state_dir("canvas")
    if action == "checkpoints":
        return {"checkpoints": [p.stem for p in sorted(folder.glob("*.json"), reverse=True)]}
    if action == "inspect_checkpoint":
        return json.loads((folder / (Path(path).name + ".json")).read_text())
    if action in ("checkpoint", "restore_checkpoint"):
        current = await call("read", {"mode": "full"}, client_id, revision)
        checkpoint_id = uuid.uuid4().hex
        write_json(folder / f"{checkpoint_id}.json", current)
        if action == "checkpoint":
            return {"checkpoint": checkpoint_id, "path": str(folder / f"{checkpoint_id}.json")}
        saved = json.loads((folder / (Path(path).name + ".json")).read_text())
        restored = await call("workflow", {"action": "load", "graph": saved["result"]["ui"]}, client_id)
        return {"reverse_checkpoint": checkpoint_id, "restored": restored}
    return await call("workflow", dict(action=action, path=path, name=name, graph=graph, force=force), client_id, revision)


@mcp.tool()
async def canvas_control(action: str, params: dict | None = None, client_id: str | None = None, revision: str | None = None, request_id: str | None = None) -> dict:
    """Actions: select(node_ids), undo, redo, clear, refresh_nodes, run(batch_count,
    to_node_id optional output target), interrupt(prompt_id required), fit, pan, zoom.
    View actions follow Panel graph_canvas parameters. run returns real prompt IDs;
    follow with official job/fetch_outputs. It submits current unsaved browser data.
    """
    if action == "run":
        await canvas_workflow("checkpoint", client_id=client_id, revision=revision)
    return await call("control", {**(params or {}), "action": action}, client_id, revision, 120, request_id)


@mcp.tool()
async def canvas_screenshot(mode: Literal["full", "viewport", "region", "nodes"] = "full", bounds: list[float] | None = None, node_ids: list[str | int] | None = None, padding: int = 60, client_id: str | None = None) -> list:
    """Return a real canvas image plus graph bounds. region uses [x,y,width,height];
    nodes computes bounds from node_ids. Restores the user's view after capture.
    """
    reply = await call("screenshot", dict(mode=mode, bounds=bounds, node_ids=node_ids, padding=padding), client_id)
    data = reply["result"]
    uri = data.pop("data_url", None) or data.pop("dataUrl", None) or data.pop("image", None)
    if not uri:
        return [TextContent(type="text", text=json.dumps(reply))]
    return [ImageContent(type="image", mimeType="image/png", data=uri.split(",", 1)[-1]), TextContent(type="text", text=json.dumps(reply))]


@mcp.tool()
async def canvas_eval(code: str, client_id: str | None = None, revision: str | None = None, request_id: str | None = None) -> dict:
    """Execute async JavaScript in the real frontend with app, api, LiteGraph,
    commands, window/document. Return JSON-serializable data. This is unrestricted:
    prefer structured actions, checkpoint major changes, never blindly retry an
    unknown outcome. Undo cannot reverse network side effects or stop infinite loops.
    """
    return await call("eval", {"code": code}, client_id, revision, request_id=request_id)
