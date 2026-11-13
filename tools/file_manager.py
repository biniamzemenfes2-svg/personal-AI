"""Sandboxed file operations: everything stays inside the workspace."""
from pathlib import Path


class FileManager:
    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _resolve(self, filename: str) -> Path:
        path = (self.workspace / filename).resolve()
        if not path.is_relative_to(self.workspace):
            raise PermissionError("Path is outside the AetherOS workspace.")
        return path

    def write(self, filename: str, content: str) -> str:
        path = self._resolve(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content or "", encoding="utf-8")
        return f"Saved file to {filename}"

    def read(self, filename: str) -> str:
        path = self._resolve(filename)
        if not path.is_file():
            raise FileNotFoundError(f"File does not exist: {filename}")
        return path.read_text(encoding="utf-8")

    def list(self):
        return sorted(
            str(p.relative_to(self.workspace))
            for p in self.workspace.rglob("*") if p.is_file()
        )
