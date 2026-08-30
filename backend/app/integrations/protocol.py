from __future__ import annotations

from typing import Protocol


class ConnectorError(Exception):
    """Lỗi connector (không có creds, network, tool không biết...)."""


class Connector(Protocol):
    """Connector = seam thế giới ngoài (plan §11): list_tools + call như MCP tool."""

    name: str

    async def list_tools(self) -> list[dict]: ...

    async def call(self, tool: str, args: dict) -> dict: ...
