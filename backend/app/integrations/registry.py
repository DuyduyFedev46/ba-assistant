from __future__ import annotations

import logging

import yaml

from ..config import Settings
from .adapters.calendar_google import CalendarGoogleConnector
from .adapters.repo_git import RepoGitConnector
from .fakes import FakeCalendarConnector, FakeRepoConnector
from .mcp_client import McpConnector
from .protocol import Connector, ConnectorError

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """Registry connector theo id — seam swap bằng test qua register()."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        """Đăng ký connector theo name (REPLACE nếu đã có — seam swap cho test)."""
        self._connectors[connector.name] = connector

    def get(self, name: str) -> Connector:
        """Lấy connector theo name; lỗi ConnectorError nếu chưa đăng ký."""
        if name not in self._connectors:
            raise ConnectorError(f"connector '{name}' chưa đăng ký")
        return self._connectors[name]

    @classmethod
    def from_settings(cls, settings: Settings) -> ConnectorRegistry:
        """Build registry từ connectors.yaml; llm_fake=True → thay bằng fake connector."""
        registry = cls()
        data = yaml.safe_load(settings.connectors_file.read_text(encoding="utf-8")) or {}
        for entry in data.get("connectors", []) or []:
            if entry.get("enabled") is False:
                continue
            connector = cls._build(settings, entry)
            if connector is not None:
                registry.register(connector)
        return registry

    @classmethod
    def _build(cls, settings: Settings, entry: dict) -> Connector | None:
        cid = entry.get("id")
        config = entry.get("config") or {}
        transport = entry.get("transport")
        if not cid:
            logger.warning("bỏ entry connector không có id: %s", entry)
            return None
        if settings.llm_fake and cid == "calendar-google":
            return FakeCalendarConnector(cid)
        if settings.llm_fake and cid == "repo-github":
            return FakeRepoConnector(cid)
        if transport == "mcp":
            return McpConnector(cid, config)
        if transport == "direct":
            if cid == "calendar-google":
                return CalendarGoogleConnector(cid, config)
            if cid == "repo-github":
                return RepoGitConnector(cid, config)
        logger.warning("bỏ connector '%s' (transport=%s) — không biết loại", cid, transport)
        return None
