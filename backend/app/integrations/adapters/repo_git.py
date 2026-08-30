from __future__ import annotations

from pathlib import Path

from ..protocol import Connector, ConnectorError


class RepoGitConnector(Connector):
    """Connector git repo (direct, GitPython): commit_files clone + commit/push."""

    def __init__(self, name: str = "repo-github", config: dict | None = None) -> None:
        self.name = name
        self.config = config or {}
        self.clone_dir = self.config.get("clone_dir") or "/tmp/ba_repos"

    async def list_tools(self) -> list[dict]:
        """Khai báo tool commit_files."""
        return [
            {
                "name": "commit_files",
                "description": "Ghi batch file vào repo clone, commit và push (nếu có remote).",
            }
        ]

    async def call(self, tool: str, args: dict) -> dict:
        """Gọi commit_files với args {repo_url, files: {relpath: content}, message}."""
        if tool != "commit_files":
            raise ConnectorError(f"tool '{tool}' không được hỗ trợ bởi {self.name}")
        from git import Repo

        repo_url = args["repo_url"]
        repo_name = repo_url.split("/")[-1].removesuffix(".git")
        dest = Path(self.clone_dir) / repo_name
        try:
            repo = Repo(dest) if (dest / ".git").exists() else Repo.clone_from(repo_url, dest)
            for relpath, content in (args.get("files") or {}).items():
                path = dest / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(content), encoding="utf-8")
            repo.git.add(A=True)
            repo.index.commit(args.get("message") or f"update {repo_name}")
            if any(remote.url for remote in repo.remotes):
                repo.remote().push()
        except Exception as exc:
            raise ConnectorError(f"commit_files thất bại cho {repo_url}: {exc}") from exc
        return {"commit": repo.head.commit.hexsha[:12]}
