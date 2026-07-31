"""Contract tests for local infrastructure detection in ``dev.sh``."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DEV_SH = REPO_ROOT / "dev.sh"


def _write_command(path: Path, body: str) -> None:
    path.write_text(f"#!/usr/bin/env bash\n{body}\n")
    path.chmod(0o755)


def test_auto_mode_prefers_running_local_postgres_over_stopped_colima(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_command(fake_bin / "pg_isready", "exit 0")
    _write_command(fake_bin / "docker", "exit 1")
    _write_command(fake_bin / "colima", "exit 1")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "METAEDU_PG_BIN": str(fake_bin),
            "METAEDU_INFRA": "",
        }
    )
    result = subprocess.run(
        ["bash", "-c", f'source "{DEV_SH}"; detect_infra_mode'],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "local"


def test_auto_mode_prefers_local_postgres_when_docker_has_no_postgres(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_command(fake_bin / "pg_isready", "exit 0")
    _write_command(
        fake_bin / "docker",
        'if [[ "$1" == "info" ]]; then exit 0; fi\n'
        'if [[ "$1" == "ps" ]]; then echo unrelated-container; exit 0; fi\n'
        "exit 1",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "METAEDU_PG_BIN": str(fake_bin),
            "METAEDU_INFRA": "",
        }
    )
    result = subprocess.run(
        ["bash", "-c", f'source "{DEV_SH}"; detect_infra_mode'],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "local"


def test_local_redis_is_started_with_workspace_pid_and_log_files(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state_file = tmp_path / "redis-running"
    args_file = tmp_path / "redis-args"
    _write_command(
        fake_bin / "redis-cli",
        f'[[ -f "{state_file}" ]] && echo PONG && exit 0\nexit 1',
    )
    _write_command(
        fake_bin / "redis-server",
        f'printf "%s\\n" "$*" > "{args_file}"\ntouch "{state_file}"',
    )
    _write_command(fake_bin / "nc", "exit 1")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    result = subprocess.run(
        ["bash", "-c", f'source "{DEV_SH}"; ensure_redis_local'],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    args = args_file.read_text()
    assert "--bind 127.0.0.1" in args
    assert f"--pidfile {REPO_ROOT / '.dev-logs/redis.pid'}" in args
    assert f"--logfile {REPO_ROOT / '.dev-logs/redis.log'}" in args
    assert "Redis 已启动" in result.stdout


def test_docker_infra_starts_services_missing_beside_existing_postgres(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_args = tmp_path / "compose-args"
    _write_command(
        fake_bin / "docker",
        'if [[ "$1" == "info" ]]; then exit 0; fi\n'
        'if [[ "$1" == "ps" ]]; then echo metaedu-postgres-1; exit 0; fi\n'
        "exit 1",
    )
    _write_command(
        fake_bin / "docker-compose",
        f'printf "%s\\n" "$*" > "{compose_args}"',
    )
    _write_command(fake_bin / "redis-cli", "exit 1")
    _write_command(fake_bin / "nc", "exit 1")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    result = subprocess.run(
        ["bash", "-c", f'source "{DEV_SH}"; ensure_docker_infra'],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    args = compose_args.read_text().strip()
    assert "up -d redis minio" in args
    assert "up -d postgres" not in args
    assert "补齐 Docker 基础设施: redis minio" in result.stdout
