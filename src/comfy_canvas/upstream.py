"""The only integration point with the pinned official MCP package."""
from comfy_mcp import server
from functools import wraps
from mcp.server.mcpserver.exceptions import ToolError


class LocalTools:
    """Register on the same server; expose actionable local errors to MCP clients."""
    def tool(self):
        def decorate(function):
            @wraps(function)
            async def invoke(*args, **kwargs):
                try:
                    return await function(*args, **kwargs)
                except (ValueError, RuntimeError, OSError) as error:
                    raise ToolError(str(error)) from error
            return server.mcp.tool()(invoke)
        return decorate


mcp = LocalTools()


def serve():
    server.main()
