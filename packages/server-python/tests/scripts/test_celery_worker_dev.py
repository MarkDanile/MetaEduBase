"""Regression tests for the local Celery worker launcher."""

from __future__ import annotations

import os
import sys

from tests.scripts._script_loader import load_server_script


def _load_worker_script():
    original_cwd = os.getcwd()
    try:
        return load_server_script("celery_worker_dev")
    finally:
        os.chdir(original_cwd)


def test_worker_uses_current_python_environment(monkeypatch):
    script = _load_worker_script()
    calls: list[list[str]] = []
    monkeypatch.setattr(script.subprocess, "call", lambda args: calls.append(args) or 0)

    assert script._run_celery() == 0
    assert calls == [script.CELERY_ARGS]
    assert script.CELERY_ARGS[:3] == [sys.executable, "-m", "celery"]
