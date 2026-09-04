from __future__ import annotations
import json
from pathlib import Path


class StateStore:
    def __init__(self, path: Path | None = None):
        self.path = path or Path.home() / ".local/share/xepub/state.json"
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {"books": {}, "preferences": {}}

    def book(self, key: str) -> dict:
        return self.data.setdefault("books", {}).setdefault(key, {})

    @property
    def preferences(self) -> dict:
        return self.data.setdefault("preferences", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)
