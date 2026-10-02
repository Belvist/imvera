"""Deployed runtime truth must survive slim images without a git executable."""

import subprocess

import pytest

from packages.dialogue_engine import runtime


@pytest.fixture(autouse=True)
def revision_cache(monkeypatch):
    monkeypatch.delenv("IMVERA_GIT_SHA", raising=False)
    runtime.git_sha_short.cache_clear()
    yield
    runtime.git_sha_short.cache_clear()


def test_image_revision_does_not_require_git(monkeypatch):
    monkeypatch.setenv("IMVERA_GIT_SHA", "c896aeeb9595e4889fdc5a11cdf058e9bd0173e2")

    def absent_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", absent_git)
    assert runtime.runtime_truth()["dialogue.engine.version"] == (
        "c896aeeb9595e4889fdc5a11cdf058e9bd0173e2"
    )


def test_missing_git_without_revision_remains_explicitly_unknown(monkeypatch):
    def absent_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", absent_git)
    assert runtime.runtime_truth()["dialogue.engine.version"] == "unknown"
