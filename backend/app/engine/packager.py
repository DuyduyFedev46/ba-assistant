from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..integrations.registry import ConnectorRegistry
from .profile_loader import Profile
from .profile_mapper import build_doc_context
from .state import MeetingState

logger = logging.getLogger(__name__)


class PackageResult:
    """Kết quả đóng gói: files (tên → nội dung) + commit/repo nếu đã commit."""

    def __init__(self, files: dict[str, str], commit: str | None, repo: str | None) -> None:
        self.files = files
        self.commit = commit
        self.repo = repo


class Packager:
    """Đóng gói state cuối: render final doc + dump state JSON + commit repo (theo profile)."""

    def __init__(self, connectors: ConnectorRegistry, templates_dir: Path) -> None:
        self.connectors = connectors
        self.templates_dir = templates_dir

    async def package(self, *, meeting, profile: Profile, state: MeetingState) -> PackageResult:
        """Render final doc (nếu bật), dump meeting-state.json, commit repo nếu routing cấu hình."""
        files: dict[str, str] = {}
        date_str = meeting.started_at.date().isoformat()

        if profile.final_doc.enabled and profile.final_doc.template:
            template_name = Path(profile.final_doc.template).name
            env = Environment(loader=FileSystemLoader(str(self.templates_dir)))
            context = build_doc_context(state=state, profile=profile, date=date_str)
            rendered = env.get_template(template_name).render(**context)
            filename = profile.routing.file_convention.format(date=date_str, slug=profile.project)
            files[filename] = rendered

        files["meeting-state.json"] = json.dumps(
            state.model_dump(mode="json"), ensure_ascii=False, indent=2
        )

        commit: str | None = None
        if profile.routing.repo:
            connector = self.connectors.get("repo-github")
            out = await connector.call(
                "commit_files",
                {
                    "repo_url": profile.routing.repo,
                    "files": files,
                    "message": f"BA assistant: {profile.project} {date_str}",
                },
            )
            commit = out.get("commit")
        return PackageResult(files, commit, repo=profile.routing.repo or None)
