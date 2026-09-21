from typing import Literal

from .client import request
from .config import run, settings
from .upstream import mcp


@mcp.tool()
async def runtime_manage(action: Literal["status", "logs", "start", "stop", "restart", "reload", "health"] = "status", lines: int = 100) -> dict:
    """Manage the existing systemd USER ComfyUI service (no sudo, no second server).
    Check queue before interrupting generation. logs reads real journal, not CLI logs.
    reload applies edited unit/drop-ins but does not restart. Existing memory limits
    and startup arguments are never rewritten by this tool.
    """
    service = settings()["service"]
    if action == "logs":
        return {"journal": run(["journalctl", "--user", "-u", service, "-n", str(lines), "--no-pager"])}
    if action == "status":
        return {"service": run(["systemctl", "--user", "show", service, "-p", "ActiveState,SubState,MainPID,ExecStart,MemoryCurrent,MemoryHigh,MemoryMax,MemorySwapMax,FragmentPath,DropInPaths"])}
    if action == "health":
        return {"system": request("/system_stats"), "queue": request("/queue"), "bridge": request("/canvas-mcp/status")}
    if action == "reload":
        return {"output": run(["systemctl", "--user", "daemon-reload"])}
    return {"output": run(["systemctl", "--user", action, service]), "action": action}
