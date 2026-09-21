"""In-process relay. The browser owns the live graph; ComfyUI only forwards commands."""
import asyncio
import time
from collections import OrderedDict

from aiohttp import web
from server import PromptServer

clients = {}
requests = OrderedDict()
routes = PromptServer.instance.routes


@routes.get("/canvas-mcp/status")
async def status(request):
    return web.json_response({"version": "0.1.0", "clients": [
        {"client_id": key, **value["info"], "age_seconds": round(time.monotonic() - value["seen"], 1)}
        for key, value in clients.items()
    ]})


@routes.get("/canvas-mcp/ws")
async def websocket(request):
    socket = web.WebSocketResponse(heartbeat=25, max_msg_size=24 * 1024 * 1024)
    await socket.prepare(request)
    client_id = None
    async for frame in socket:
        if frame.type != web.WSMsgType.TEXT:
            continue
        message = frame.json()
        if message["type"] == "hello":
            client_id = message["client_id"]
            clients[client_id] = {"socket": socket, "info": message["info"], "seen": time.monotonic()}
        elif message["type"] == "heartbeat" and client_id in clients:
            clients[client_id].update(info=message["info"], seen=time.monotonic())
        elif message["type"] == "result":
            pending = requests.get(message["id"])
            if pending and pending["client_id"] == client_id and not pending["future"].done():
                pending["future"].set_result(message)
    if client_id in clients and clients[client_id]["socket"] is socket:
        del clients[client_id]
    return socket


@routes.post("/canvas-mcp/command")
async def command(request):
    message = await request.json()
    rid = message["id"]
    if rid not in requests:
        target = message.get("client_id")
        if target is None:
            if len(clients) != 1:
                return web.json_response({"error": "Choose client_id from canvas_status; no unique active canvas", "clients": list(clients)}, status=409)
            target = next(iter(clients))
        if target not in clients:
            return web.json_response({"error": "NO_ACTIVE_CANVAS", "client_id": target}, status=409)
        future = asyncio.get_running_loop().create_future()
        requests[rid] = {"client_id": target, "future": future}
        await clients[target]["socket"].send_json({**message, "type": "command"})
        for old_id in list(requests)[:-128]:
            if requests[old_id]["future"].done():
                del requests[old_id]
    try:
        result = await asyncio.wait_for(asyncio.shield(requests[rid]["future"]), timeout=min(message.get("timeout", 60), 180))
        return web.json_response(result)
    except asyncio.TimeoutError:
        return web.json_response({"error": "OUTCOME_UNKNOWN: browser did not acknowledge; inspect before retrying", "request_id": rid}, status=504)
