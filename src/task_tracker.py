"""
task_tracker.py — Persistent tracking of attempted and submitted tasks.

Prevents the autonomous agent from repeating the same bounty or issue,
allowing it to relentlessly process new opportunities one by one.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent
_HISTORY_PATH = _PROJECT_ROOT / "history.jsonl"


class TaskTracker:
    def __init__(self, history_file: Path = _HISTORY_PATH) -> None:
        self.history_file = history_file
        self._load_cache()

    def _load_cache(self) -> None:
        self.seen_urls: set[str] = set()
        if not self.history_file.exists():
            return
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        url = entry.get("url")
                        if url:
                            self.seen_urls.add(self._normalize_url(url))
                    except Exception:
                        continue
        except Exception:
            pass

    @staticmethod
    def _normalize_url(url: str) -> str:
        return url.strip().lower().rstrip("/")

    def is_attempted(self, url: str) -> bool:
        if not url:
            return False
        norm = self._normalize_url(url)
        if norm in self.seen_urls:
            return True
        if "listings/" in norm:
            slug = norm.split("listings/")[-1].strip("/")
            if slug in self.seen_urls:
                return True
        return False

    def filter_unattempted(self, opps: list[dict]) -> list[dict]:
        """Return only tasks that have not yet been completed or attempted."""
        unattempted = []
        for o in opps:
            url = o.get("url") or ""
            slug = o.get("slug") or ""
            if not self.is_attempted(url) and not (slug and self.is_attempted(slug)):
                unattempted.append(o)
        return unattempted

    def record_completed_task(
        self,
        url: str,
        title: str,
        source: str,
        artifact_or_pr: str,
        status: str = "submitted",
    ) -> None:
        """Record a completed task so it won't be repeated."""
        norm = self._normalize_url(url)
        self.seen_urls.add(norm)
        if "listings/" in norm:
            slug = norm.split("listings/")[-1].strip("/")
            self.seen_urls.add(slug)

        record = {
            "url": url,
            "title": title,
            "source": source,
            "artifact_or_pr": artifact_or_pr,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def count_submitted(self) -> int:
        return len(self.seen_urls)


# Global singleton tracker
tracker = TaskTracker()
