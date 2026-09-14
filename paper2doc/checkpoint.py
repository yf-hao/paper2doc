from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CHECKPOINT_VERSION = 1


class CheckpointError(RuntimeError):
    """Raised when a checkpoint cannot be safely loaded or written."""


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_checkpoint_dir() -> Path:
    configured = os.getenv("PAPER2DOC_CHECKPOINT_DIR")
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Caches"
    elif os.name == "nt":
        root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "paper2doc" / "checkpoints"


def _settings_hash(settings: dict[str, Any]) -> str:
    encoded = json.dumps(settings, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hash_text(encoded)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CheckpointStore:
    def __init__(
        self,
        input_path: str | Path,
        settings: dict[str, Any],
        directory: str | Path | None = None,
        restart: bool = False,
    ):
        self.input_path = Path(input_path).expanduser().resolve()
        self.settings = settings
        self.source_sha256 = hash_file(self.input_path)
        self.settings_sha256 = _settings_hash(settings)
        checkpoint_dir = Path(directory).expanduser() if directory else default_checkpoint_dir()
        self.path = checkpoint_dir / (
            f"paper2doc-{self.source_sha256}-{self.settings_sha256}.checkpoint.json"
        )
        if restart and self.path.exists():
            self.path.unlink()
        self._data = self._new_data()
        if self.path.exists():
            self._load()

    def _new_data(self) -> dict[str, Any]:
        return {
            "version": CHECKPOINT_VERSION,
            "source_sha256": self.source_sha256,
            "settings_sha256": self.settings_sha256,
            "input_path": str(self.input_path),
            "settings": self.settings,
            "translations": {},
            "context": None,
            "updated_at": _now(),
        }

    def _load(self) -> None:
        try:
            with self.path.open("r", encoding="utf-8") as source:
                data = json.load(source)
        except (OSError, json.JSONDecodeError) as exc:
            raise CheckpointError(f"Cannot read checkpoint: {self.path}") from exc
        if not isinstance(data, dict):
            raise CheckpointError(f"Invalid checkpoint format: {self.path}")
        if data.get("version") != CHECKPOINT_VERSION:
            raise CheckpointError(f"Unsupported checkpoint version: {data.get('version')}")
        if data.get("source_sha256") != self.source_sha256:
            raise CheckpointError("Checkpoint does not belong to the current PDF")
        if data.get("settings_sha256") != self.settings_sha256:
            raise CheckpointError("Checkpoint settings do not match the current command")
        if not isinstance(data.get("translations"), dict):
            raise CheckpointError("Checkpoint translations are invalid")
        self._data = data

    @property
    def has_saved_translations(self) -> bool:
        return bool(self._data["translations"])

    def restored_translations(self, units: list[tuple[str, str]]) -> dict[str, str]:
        restored: dict[str, str] = {}
        saved = self._data["translations"]
        for unit_id, text in units:
            item = saved.get(unit_id)
            if not isinstance(item, dict):
                continue
            if item.get("source_sha256") != hash_text(text):
                continue
            translation = item.get("translation")
            if isinstance(translation, str) and translation.strip():
                restored[unit_id] = translation.strip()
        return restored

    def record(self, units: list[tuple[str, str]], translations: dict[str, str]) -> None:
        saved = self._data["translations"]
        for unit_id, text in units:
            translation = translations.get(unit_id)
            if not isinstance(translation, str) or not translation.strip():
                raise CheckpointError(f"Cannot checkpoint empty translation: {unit_id}")
            saved[unit_id] = {
                "source_sha256": hash_text(text),
                "translation": translation.strip(),
                "status": "completed",
            }
        self._data["updated_at"] = _now()
        self._atomic_save()

    def set_context(self, context: dict[str, Any] | None) -> None:
        self._data["context"] = context
        self._data["updated_at"] = _now()
        self._atomic_save()

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise CheckpointError(f"Cannot remove checkpoint: {self.path}") from exc

    def _atomic_save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=self.path.parent,
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                json.dump(self._data, target, ensure_ascii=False, indent=2)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary_path, self.path)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        except OSError as exc:
            raise CheckpointError(f"Cannot write checkpoint: {self.path}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

