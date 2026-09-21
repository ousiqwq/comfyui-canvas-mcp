import asyncio
import json
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .config import settings


def request(path, payload=None, timeout=65):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(settings()["url"].rstrip("/") + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(exc.read().decode(errors="replace")) from exc


async def command(action, params=None, client_id=None, revision=None, timeout=60, request_id=None):
    return await asyncio.to_thread(request, "/canvas-mcp/command", {
        "id": request_id or uuid.uuid4().hex, "action": action, "params": params or {},
        "client_id": client_id, "revision": revision, "timeout": timeout,
    }, timeout + 5)
