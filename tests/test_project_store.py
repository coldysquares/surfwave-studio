from pathlib import Path

import pytest

from src.shared.project import ProjectStore


def test_create_add_and_resolve_asset(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "demo", "Night Drive")
    source = store.add_asset(kind="source", path="source/master.wav", label="Original mix")
    stem = store.add_asset(
        kind="stem",
        path="stems/vocals.wav",
        label="Vocals",
        source_ids=[source.id],
        meta={"engine": "demucs"},
    )

    assert store.exists()
    assert store.read()["id"] == "night-drive"
    assert store.get_asset(stem.id).source_ids == (source.id,)
    assert store.resolve_asset_path(stem.id) == (store.root / "stems/vocals.wav").resolve()


def test_workspace_state_is_independent(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "demo", "Demo")
    store.update_workspace_state("studio", {"selected_take": "take-1"})
    store.update_workspace_state("voice_lab", {"selected_model": "nick-general"})

    assert store.workspace_state("studio") == {"selected_take": "take-1"}
    assert store.workspace_state("voice_lab") == {"selected_model": "nick-general"}


def test_rejects_unsafe_paths(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "demo", "Demo")
    with pytest.raises(ValueError):
        store.add_asset(kind="source", path="../outside.wav")


def test_source_relationships_must_exist(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "demo", "Demo")
    with pytest.raises(KeyError):
        store.add_asset(kind="render", path="renders/x.wav", source_ids=["missing"])


def test_remove_never_deletes_files(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "demo", "Demo")
    audio = store.root / "takes" / "take.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"audio")
    asset = store.add_asset(kind="take", path="takes/take.wav")

    store.remove_asset(asset.id)

    assert audio.exists()
    assert store.assets() == []
