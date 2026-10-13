"""A draft is one pattern on its way into the library. It lives in a folder under DATA_DIR/drafts."""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any


def _now() -> float:
    return time.time()


class Draft:
    def __init__(self, root: Path, draft_id: str):
        self.id = draft_id
        self.dir = root / draft_id
        self.meta_path = self.dir / "meta.json"

    # ---- files
    @property
    def pdf(self) -> Path:
        return self.dir / "pattern.pdf"

    @property
    def main_html(self) -> Path:
        return self.dir / "main.html"

    @property
    def print_html(self) -> Path:
        return self.dir / "print.html"

    def previews_dir(self) -> Path:
        d = self.dir / "previews"
        d.mkdir(exist_ok=True)
        return d

    # ---- meta
    def load(self) -> dict[str, Any]:
        with open(self.meta_path, encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, meta: dict[str, Any]) -> None:
        meta["updated"] = _now()
        tmp = self.meta_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self.meta_path)


class DraftStore:
    def __init__(self, data_dir: Path, ttl_hours: int):
        self.root = data_dir / "drafts"
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_hours * 3600

    def create(self, initial: dict[str, Any]) -> Draft:
        draft_id = uuid.uuid4().hex[:16]
        d = Draft(self.root, draft_id)
        d.dir.mkdir(parents=True)
        meta = {"id": draft_id, "created": _now(), "status": "working", **initial}
        d.save(meta)
        return d

    def get(self, draft_id: str) -> Draft | None:
        if not draft_id.isalnum() or len(draft_id) != 16:
            return None
        d = Draft(self.root, draft_id)
        return d if d.meta_path.exists() else None

    def delete(self, draft_id: str) -> None:
        d = self.get(draft_id)
        if d:
            shutil.rmtree(d.dir, ignore_errors=True)

    def cleanup(self) -> int:
        removed = 0
        cutoff = _now() - self.ttl
        for child in self.root.iterdir():
            try:
                if child.is_dir() and child.stat().st_mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
        return removed
