import subprocess
from pathlib import Path

from nod.domain.errors import GitError


class GitService:
    def __init__(self, root: Path):
        self.root = root

    def is_repository(self) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=self.root, capture_output=True, text=True
        )
        return result.returncode == 0

    def current_branch(self) -> str:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.root, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise GitError(result.stderr.strip() or "Unable to determine Git branch.")
        return result.stdout.strip()

    def branch_exists(self, name: str) -> bool:
        result = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{name}"],
            cwd=self.root
        )
        return result.returncode == 0

    def create_branch(self, name: str, checkout: bool = True) -> None:
        command = ["git", "switch", "-c", name] if checkout else ["git", "branch", name]
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
        if result.returncode != 0:
            raise GitError(result.stderr.strip() or "Unable to create Git branch.")
