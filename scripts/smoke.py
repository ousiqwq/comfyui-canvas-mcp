#!/usr/bin/env python3
"""One small MCP integration smoke; optional no-model canvas/output round trip."""
import argparse
import asyncio
import json
import os
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(edit):
    env = os.environ.copy()
    server = StdioServerParameters(command="comfy-mcp-local", env=env)
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=120) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            names = [t.name for t in tools]
            assert len(names) == len(set(names)), "Duplicate tools"
            assert {"server_info", "canvas_read", "environment_snapshot", "model_catalog"} <= set(names)
            print(json.dumps({"tools": len(names), "names": names}))

            async def call(name, args=None):
                result = await session.call_tool(name, args or {})
                if result.is_error:
                    raise RuntimeError(f"{name}: {result.content}")
                text = [c.text for c in result.content if c.type == "text"]
                data = json.loads(text[0]) if text else {}
                print(name, json.dumps(data, ensure_ascii=False)[:1000], flush=True)
                return data

            await call("canvas_status")
            await call("runtime_manage", {"action": "status"})
            await call("server_info")
            if not edit:
                return
            await call("canvas_workflow", {"action": "new"})
            added = await call("canvas_apply", {"operations": [
                {"op": "add", "class_type": "EmptyImage", "pos": [80, 120], "as": "source"},
                {"op": "add", "class_type": "SaveImage", "pos": [480, 120], "as": "save"},
                {"op": "set_widget", "node_id": "$source", "widget": "width", "value": 64},
                {"op": "set_widget", "node_id": "$source", "widget": "height", "value": 64},
                {"op": "set_widget", "node_id": "$source", "widget": "color", "value": 3368652},
                {"op": "set_widget", "node_id": "$save", "widget": "filename_prefix", "value": "canvas-mcp-smoke"},
                {"op": "connect", "from_node_id": "$source", "from_output": "IMAGE", "to_node_id": "$save", "to_input": "images"},
            ]})
            before = await call("canvas_read")
            assert before["result"]["total"] == 2
            await call("canvas_layout", {"dry_run": True})
            after = await call("canvas_read")
            assert before["revision"] == after["revision"], "Dry-run changed graph"
            await call("canvas_control", {"action": "undo"})
            empty = await call("canvas_read")
            assert empty["result"]["total"] == 0, "Batch undo was not atomic"
            await call("canvas_control", {"action": "redo"})
            await call("canvas_workflow", {"action": "save_as", "path": "canvas-mcp-smoke.json", "force": True})
            saved=await call("canvas_eval", {"code":"const r=await api.getUserData('workflows/canvas-mcp-smoke.json'); const g=await r.json(); return {nodes:g.nodes.length,links:g.links.length};"})
            assert saved['result']=={'nodes':2,'links':1}, 'Saved workflow is not valid JSON'
            queued = await call("canvas_control", {"action": "run"})
            prompt_id = queued["result"]["prompts"][0]["prompt_id"]
            print("PROMPT_ID=" + prompt_id, flush=True)
            await call("job", {"action":"wait","prompt_id":prompt_id,"timeout_seconds":30})
            outputs=await call("fetch_outputs", {"prompt_id":prompt_id,"out_dir":os.path.expanduser('~/.local/share/comfyui-canvas-mcp/smoke-output')})
            await call("workflow_media", {"action":"inspect","path":outputs['files'][0]['path']})
            await call("canvas_screenshot")
            await call("canvas_workflow", {"action": "list"})
            print("SMOKE PASSED", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--edit", action="store_true")
    asyncio.run(main(parser.parse_args().edit))
