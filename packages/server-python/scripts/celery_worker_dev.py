"""Dev-mode Celery worker with auto-reload on Python source changes.

Celery 5.x removed the built-in ``--autoreload`` flag. This wrapper
re-implements the same UX using ``watchfiles`` (already a transitive
dependency of uvicorn[standard] / FastAPI). On any file change under
``app/`` it restarts the worker subprocess — matching the
``uvicorn --reload`` ergonomics for the Celery worker.

Usage:
    python scripts/celery_worker_dev.py

This is invoked by:
- ``packages/server-python/Makefile`` celery-worker target
- ``dev.sh`` start_celery()

The watcher only runs in dev; production deployments should not use this
script (use bare ``celery -A app.celery_app worker`` instead, with
``--pool`` and concurrency tuned for the workload).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

# Ensure the package root is importable so subprocess `celery -A app.celery_app` works
SERVER_DIR = Path(__file__).resolve().parent.parent
os.chdir(SERVER_DIR)

# Args to forward to the Celery worker. Keep aligned with the production
# invocation in Dockerfile.backend / deploy scripts.
CELERY_ARGS = [
    "celery",
    "-A",
    "app.celery_app",
    "worker",
    "--loglevel=info",
    "--pool=solo",
]


def _run_celery() -> int:
    """Run the Celery worker; return its exit code."""
    return subprocess.call(CELERY_ARGS)


def main() -> int:
    # Lazy import so non-dev shells (e.g. CI) without watchfiles installed
    # can still invoke the script and get a clear ImportError.
    from watchfiles import run_process

    # Use the current source tree as the watch root. Exclude __pycache__
    # and .pytest_cache to avoid spurious restarts on bytecode writes.
    watch_roots = [str(SERVER_DIR / "app")]

    print(
        f"[celery_worker_dev] Watching {watch_roots} for changes; "
        f"running: {' '.join(shlex.quote(a) for a in CELERY_ARGS)}",
        file=sys.stderr,
    )
    # run_process spawns the target as a subprocess; on file change it
    # kills and restarts. raise_interrupt=False (the default) ensures
    # Ctrl+C exits cleanly.
    run_process(*watch_roots, target=_run_celery)
    return 0


if __name__ == "__main__":
    sys.exit(main())
