"""Recordings as a system: catalog, retention, consent-gated export.

The hook itself is best-effort by contract (observability never breaks
teardown); these tests pin the catalog format, the retention sweep, and
the export consent gate.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from packages.voice_runtime import recordings as rec

pytestmark = pytest.mark.recordings_system


@pytest.fixture()
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("IMVERA_RECORDINGS_DIR", str(tmp_path / "rec"))
    stt = tmp_path / "stt_dumps"
    stt.mkdir()
    monkeypatch.setattr(rec, "audio_glob_for_call", lambda call_id: [])
    return tmp_path


def test_catalog_append_and_list(isolated_dirs) -> None:
    entry = rec.finalize_call_entry(
        call_id="fs-test-1",
        family_id="f",
        consent=True,
        family_status="GREEN",
        call_outcome="COMPLETED",
        audio_files=["a.wav"],
    )
    assert rec.append_catalog(entry) is True
    rows = rec.read_catalog()
    assert [r["call_id"] for r in rows] == ["fs-test-1"]
    assert rows[0]["schema"] == 1


def test_export_refuses_without_consent(isolated_dirs) -> None:
    rec.append_catalog(rec.finalize_call_entry(call_id="fs-nc", consent=False))
    result = rec.export_call("fs-nc", isolated_dirs / "out")
    assert result["ok"] is False
    assert "consent" in result["error"]


def test_export_with_consent_copies_audio(isolated_dirs, tmp_path) -> None:
    wav = tmp_path / "fs-ok_u1.wav"
    wav.write_bytes(b"RIFF....")
    rec.append_catalog(
        rec.finalize_call_entry(
            call_id="fs-ok", consent=True, audio_files=[str(wav)]
        )
    )
    result = rec.export_call("fs-ok", isolated_dirs / "out")
    assert result["ok"] is True
    assert result["audio_copied"] == ["fs-ok_u1.wav"]
    manifest = json.loads((isolated_dirs / "out" / "fs-ok" / "manifest.json").read_text())
    assert manifest["catalog_row"]["call_id"] == "fs-ok"


def test_export_override_is_recorded(isolated_dirs) -> None:
    rec.append_catalog(rec.finalize_call_entry(call_id="fs-ov", consent=False))
    result = rec.export_call(
        "fs-ov", isolated_dirs / "out", override_reason="owner audit 2026-09-28"
    )
    assert result["ok"] is True
    manifest = json.loads((isolated_dirs / "out" / "fs-ov" / "manifest.json").read_text())
    assert manifest["override_reason"] == "owner audit 2026-09-28"


def test_sweep_deletes_only_old_audio(isolated_dirs, tmp_path, monkeypatch) -> None:
    rec_dir = rec.recordings_dir()
    old = rec_dir / "old.wav"
    new = rec_dir / "new.wav"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    ancient = time.time() - 40 * 86400
    os.utime(old, (ancient, ancient))
    result = rec.sweep_retention(days=30, roots=[rec_dir])
    assert result == {"scanned": 2, "removed": 1, "kept": 1}
    assert not old.exists()
    assert new.exists()


def test_hook_never_raises(isolated_dirs) -> None:
    class Broken:
        @property
        def state(self):
            raise RuntimeError("boom")

    assert rec.note_call_finalized(Broken()) is False
