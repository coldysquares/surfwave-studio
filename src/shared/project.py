"""SURFwave project manifest primitives.

The project is the connective tissue between specialized rooms. It does not
force a workflow. Studio, Voice Lab, and future rooms can read/write their own
state while sharing one asset ledger.

No third-party dependencies. No audio files are copied by this module unless a
caller explicitly does so. Paths in the manifest are always project-relative.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "surfwave.project.v1"
MANIFEST_NAME = "surfwave.project.json"
WORKSPACES = ("studio", "voice_lab", "slopscore", "song_lab")
ASSET_KINDS = {
    "source",
    "stem",
    "take",
    "render",
    "export",
    "analysis",
    "model_ref",
    "other",
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def slugify(value: str) -> str:
    value = (value or "untitled").strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-._")
    return value[:80] or "untitled"


def _clean_relpath(value: str | Path) -> str:
    path = Path(value)
    if path.is_absolute():
        raise ValueError("Project asset paths must be relative.")
    clean = Path(*[part for part in path.parts if part not in ("", ".")])
    if ".." in clean.parts:
        raise ValueError("Project asset path cannot escape the project root.")
    return clean.as_posix()


def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


@dataclass(frozen=True)
class Asset:
    id: str
    kind: str
    path: str
    label: str
    source_ids: tuple[str, ...] = ()
    meta: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Asset":
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            path=str(data["path"]),
            label=str(data.get("label") or Path(str(data["path"])).name),
            source_ids=tuple(str(x) for x in data.get("source_ids", [])),
            meta=dict(data.get("meta") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "path": self.path,
            "label": self.label,
            "source_ids": list(self.source_ids),
            "meta": dict(self.meta or {}),
        }


class ProjectStore:
    """Read/write one local SURFwave project directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.manifest_path = self.root / MANIFEST_NAME

    @classmethod
    def create(cls, root: str | Path, title: str) -> "ProjectStore":
        store = cls(root)
        if store.manifest_path.exists():
            raise FileExistsError(f"Project already exists: {store.manifest_path}")
        now = _now()
        data = {
            "schema": SCHEMA,
            "id": slugify(title),
            "title": (title or "Untitled").strip() or "Untitled",
            "created_at": now,
            "updated_at": now,
            "assets": [],
            "workspace_state": {name: {} for name in WORKSPACES},
        }
        _atomic_json_write(store.manifest_path, data)
        return store

    def exists(self) -> bool:
        return self.manifest_path.is_file()

    def read(self) -> dict[str, Any]:
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMA:
            raise ValueError(f"Unsupported SURFwave project schema: {data.get('schema')!r}")
        data.setdefault("assets", [])
        state = data.setdefault("workspace_state", {})
        for workspace in WORKSPACES:
            state.setdefault(workspace, {})
        return data

    def write(self, data: dict[str, Any]) -> None:
        if data.get("schema") != SCHEMA:
            raise ValueError("Refusing to write an unknown project schema.")
        data["updated_at"] = _now()
        _atomic_json_write(self.manifest_path, data)

    def assets(self, kinds: Iterable[str] | None = None) -> list[Asset]:
        wanted = set(kinds) if kinds else None
        result = [Asset.from_dict(item) for item in self.read().get("assets", [])]
        return [asset for asset in result if wanted is None or asset.kind in wanted]

    def get_asset(self, asset_id: str) -> Asset:
        for asset in self.assets():
            if asset.id == asset_id:
                return asset
        raise KeyError(asset_id)

    def resolve_asset_path(self, asset_or_id: Asset | str) -> Path:
        asset = asset_or_id if isinstance(asset_or_id, Asset) else self.get_asset(asset_or_id)
        candidate = (self.root / _clean_relpath(asset.path)).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Asset resolves outside project root.")
        return candidate

    def add_asset(
        self,
        *,
        kind: str,
        path: str | Path,
        label: str | None = None,
        source_ids: Iterable[str] = (),
        meta: dict[str, Any] | None = None,
        asset_id: str | None = None,
    ) -> Asset:
        if kind not in ASSET_KINDS:
            raise ValueError(f"Unknown asset kind: {kind}")
        rel = _clean_relpath(path)
        sources = tuple(dict.fromkeys(str(x) for x in source_ids if x))
        data = self.read()
        existing_ids = {str(item.get("id")) for item in data["assets"]}
        for source_id in sources:
            if source_id not in existing_ids:
                raise KeyError(f"Unknown source asset: {source_id}")

        candidate_id = asset_id or f"{kind}-{uuid.uuid4().hex[:12]}"
        if candidate_id in existing_ids:
            raise ValueError(f"Duplicate asset id: {candidate_id}")

        asset = Asset(
            id=candidate_id,
            kind=kind,
            path=rel,
            label=(label or Path(rel).name).strip(),
            source_ids=sources,
            meta=dict(meta or {}),
        )
        data["assets"].append(asset.to_dict())
        self.write(data)
        return asset

    def remove_asset(self, asset_id: str) -> None:
        """Remove a ledger entry only. Never delete the underlying file."""
        data = self.read()
        before = len(data["assets"])
        data["assets"] = [item for item in data["assets"] if item.get("id") != asset_id]
        if len(data["assets"]) == before:
            raise KeyError(asset_id)
        for item in data["assets"]:
            if asset_id in item.get("source_ids", []):
                raise ValueError(f"Cannot remove {asset_id}; another asset still references it.")
        self.write(data)

    def workspace_state(self, workspace: str) -> dict[str, Any]:
        self._check_workspace(workspace)
        return dict(self.read()["workspace_state"].get(workspace) or {})

    def update_workspace_state(self, workspace: str, patch: dict[str, Any]) -> dict[str, Any]:
        self._check_workspace(workspace)
        data = self.read()
        current = dict(data["workspace_state"].get(workspace) or {})
        current.update(patch)
        data["workspace_state"][workspace] = current
        self.write(data)
        return current

    @staticmethod
    def _check_workspace(workspace: str) -> None:
        if workspace not in WORKSPACES:
            raise ValueError(f"Unknown workspace: {workspace}")
