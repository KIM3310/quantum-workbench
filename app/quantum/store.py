"""Thread-safe JSON file store for quantum run history.

Provides persistent storage for run records with upsert semantics,
sorted retrieval by update time, and resilient JSON parsing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger("quantum_workbench.store")


class RunStore:
    """Thread-safe JSON file-backed store for quantum run records.

    All mutations are serialized via an internal lock. Records are
    kept sorted by updated_at (descending) on every write.

    Args:
        path: Path to the JSON file. Parent directories are created if needed.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")
            logger.info("initialized empty run store at %s", self.path)

    def list_runs(self) -> list[dict[str, Any]]:
        """Return all run records, most recent first."""
        with self._lock:
            return self._read_all()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Retrieve a single run record by ID, or None if not found."""
        with self._lock:
            for record in self._read_all():
                if record["run_id"] == run_id:
                    return record
        return None

    def upsert_run(self, record: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a run record, re-sorting by updated_at.

        Args:
            record: Run record dict; must contain a 'run_id' key.

        Returns:
            The upserted record.
        """
        with self._lock:
            runs = self._read_all()
            updated = False
            for index, existing in enumerate(runs):
                if existing["run_id"] == record["run_id"]:
                    runs[index] = record
                    updated = True
                    break
            if not updated:
                runs.insert(0, record)
            runs.sort(
                key=lambda item: item.get("updated_at", item.get("created_at", "")),
                reverse=True,
            )
            self.path.write_text(
                json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.debug(
                "upserted run record",
                extra={"run_id": record.get("run_id"), "total_runs": len(runs)},
            )
        return record

    def _read_all(self) -> list[dict[str, Any]]:
        """Read and parse the JSON store file.

        Falls back to partial JSON decoding if the file is truncated,
        and raises ValueError if the root element is not a list.
        """
        text = self.path.read_text(encoding="utf-8").strip() or "[]"
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(
                "JSON decode error in store file, attempting partial recovery"
            )
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(text)
        if not isinstance(data, list):
            raise ValueError("run store must contain a list")
        return data
