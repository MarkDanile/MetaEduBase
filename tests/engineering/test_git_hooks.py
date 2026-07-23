from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def init_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def copy_hooks(path: Path) -> None:
    shutil.copytree(REPO_ROOT / ".githooks", path / ".githooks")


def test_installer_configures_shared_hooks_for_checkout(tmp_path: Path) -> None:
    init_repo(tmp_path)
    copy_hooks(tmp_path)
    installer = tmp_path / "scripts/install-git-hooks"
    installer.parent.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts/install-git-hooks", installer)
    installer.chmod(installer.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        [str(installer)], cwd=tmp_path, text=True, capture_output=True, check=False
    )

    assert result.returncode == 0, result.stderr
    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    assert configured.stdout.strip() == ".githooks"
    assert all(os.access(tmp_path / ".githooks" / hook, os.X_OK) for hook in (
        "pre-commit", "pre-push", "commit-msg"
    ))


def test_pre_commit_propagates_ruff_failure(tmp_path: Path) -> None:
    init_repo(tmp_path)
    copy_hooks(tmp_path)
    write_executable(
        tmp_path / "packages/server-python/.venv/bin/python",
        "#!/usr/bin/env bash\nexit 17\n",
    )
    source = tmp_path / "packages/server-python/app/bad.py"
    source.parent.mkdir(parents=True)
    source.write_text("undefined_name\n", encoding="utf-8")
    subprocess.run(["git", "add", str(source)], cwd=tmp_path, check=True)

    result = subprocess.run(
        ["bash", ".githooks/pre-commit"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 17
    assert "Ruff on staged backend files" in result.stdout


def test_pre_commit_propagates_frontend_lint_failure(tmp_path: Path) -> None:
    init_repo(tmp_path)
    copy_hooks(tmp_path)
    write_executable(tmp_path / "bin/pnpm", "#!/usr/bin/env bash\nexit 19\n")
    source = tmp_path / "packages/web/src/bad.ts"
    source.parent.mkdir(parents=True)
    source.write_text("const broken: string = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", str(source)], cwd=tmp_path, check=True)
    env = os.environ | {"PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}

    result = subprocess.run(
        ["bash", ".githooks/pre-commit"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 19
    assert "ESLint on staged frontend files" in result.stdout


def test_pre_push_blocks_main_without_advertising_bypass(tmp_path: Path) -> None:
    init_repo(tmp_path)
    copy_hooks(tmp_path)

    result = subprocess.run(
        ["bash", ".githooks/pre-push"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "直接推送到 main 被拦截" in result.stdout
    assert "no-verify" not in result.stdout
