"""Unit tests for GigaAM engine wrapper (no live model download)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.stt.backends import load_asr_backend
from services.stt.gigaam_engine import (
    GigaAMEngine,
    _resolve_model_name,
    ensure_gigaam_artifacts,
)


def test_resolve_model_name_short_and_full() -> None:
    assert _resolve_model_name("e2e_rnnt") == "v3_e2e_rnnt"
    assert _resolve_model_name("v3_rnnt") == "v3_rnnt"


def test_gigaam_engine_transcribe_wav() -> None:
    model = MagicMock()
    model.transcribe.return_value = SimpleNamespace(text="  Хорошо.  ")
    engine = GigaAMEngine(model=model, model_id="v3_e2e_rnnt", device="cpu")
    assert engine.transcribe_wav(Path("/tmp/x.wav")) == "Хорошо."
    model.transcribe.assert_called_once_with("/tmp/x.wav")


def test_ensure_gigaam_artifacts_skips_existing(tmp_path: Path) -> None:
    resolved = "v3_e2e_rnnt"
    ckpt = tmp_path / f"{resolved}.ckpt"
    ckpt.write_bytes(b"x" * 64)
    (tmp_path / f"{resolved}_tokenizer.model").write_bytes(b"existing tokenizer")
    with (
        patch("services.stt.gigaam_engine._verify_checksum") as verify,
        patch("services.stt.gigaam_engine._download_file") as download,
    ):
        root = ensure_gigaam_artifacts(resolved, tmp_path)
    assert root == tmp_path
    verify.assert_called_once()
    download.assert_not_called()


def test_existing_checkpoint_downloads_only_missing_tokenizer(tmp_path: Path) -> None:
    resolved = "v3_e2e_rnnt"
    (tmp_path / f"{resolved}.ckpt").write_bytes(b"x" * 64)

    def download_tokenizer(url: str, dest: Path) -> Path:
        dest.write_bytes(b"downloaded tokenizer")
        return dest

    with (
        patch("services.stt.gigaam_engine._verify_checksum") as verify,
        patch(
            "services.stt.gigaam_engine._download_file", side_effect=download_tokenizer,
        ) as download,
    ):
        assert ensure_gigaam_artifacts(resolved, tmp_path) == tmp_path
    verify.assert_called_once()
    download.assert_called_once()
    assert download.call_args.args[0].endswith(f"/{resolved}_tokenizer.model")
    assert download.call_args.args[1] == tmp_path / f"{resolved}_tokenizer.model"


def test_load_asr_backend_unknown_engine() -> None:
    with pytest.raises(RuntimeError, match="Unknown ASR engine"):
        load_asr_backend({"engine": "whisper", "id": "large"})


def test_load_asr_backend_gigaam_mock() -> None:
    fake = GigaAMEngine(model=MagicMock(), model_id="v3_e2e_rnnt", device="cpu")
    with patch("services.stt.gigaam_engine.load_gigaam_engine", return_value=fake):
        backend, revision = load_asr_backend({"engine": "gigaam", "id": "v3_e2e_rnnt"})
    assert backend is fake
    assert revision == "gigaam:v3_e2e_rnnt@cpu"


def test_checkpoint_checksum_keeps_integrity_without_whole_file_read(tmp_path, monkeypatch):
    import hashlib

    from services.stt import gigaam_engine

    checkpoint = tmp_path / 'test.ckpt'
    payload = b'checkpoint boundary\x00' * 130000
    checkpoint.write_bytes(payload)
    monkeypatch.setitem(gigaam_engine._MODEL_HASHES, 'test', hashlib.md5(payload).hexdigest())

    def forbid_whole_file_read(path):
        raise AssertionError('checkpoint-sized allocation is forbidden')

    monkeypatch.setattr(Path, 'read_bytes', forbid_whole_file_read)
    gigaam_engine._verify_checksum(checkpoint, 'test')
    with checkpoint.open('r+b') as stream:
        stream.seek(len(payload) - 1)
        stream.write(b'!')
    with pytest.raises(RuntimeError, match='checksum mismatch'):
        gigaam_engine._verify_checksum(checkpoint, 'test')
