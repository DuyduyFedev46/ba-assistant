from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from .protocol import Connector, ConnectorError

T = TypeVar("T")


class McpConnector(Connector):
    """Connector MCP generic — thêm MCP server mới chỉ bằng config url, không sửa engine."""

    def __init__(self, name: str, config: dict | None = None) -> None:
        self.name = name
        self.config = config or {}

    async def list_tools(self) -> list[dict]:
        """Mở session ngắn hạn tới MCP server và liệt kê tool."""

        async def _list(session) -> list[dict]:
            tools = await session.list_tools()
            return [{"name": t.name, "description": t.description} for t in tools.tools]

        return await self._with_session(_list)

    async def call(self, tool: str, args: dict) -> dict:
        """Gọi tool trên MCP server; trả {"ok": not error, "content": text}."""

        async def _call(session) -> dict:
            res = await session.call_tool(tool, args)
            text = "\n".join(c.text for c in res.content if hasattr(c, "text"))
            return {"ok": not res.isError, "content": text}

        return await self._with_session(_call)

    async def _with_session(self, fn: Callable[[object], Awaitable[T]]) -> T:
        """Mở session ngắn hạn (initialize rồi chạy fn) và đóng khi xong."""
        url = self.config.get("url")
        if not url:
            raise ConnectorError(f"McpConnector '{self.name}' thiếu config url")
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        try:
            async with sse_client(url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await fn(session)
        except Exception as exc:
            raise ConnectorError(
                f"McpConnector '{self.name}' gọi MCP server '{url}' thất bại: {exc}"
            ) from exc
