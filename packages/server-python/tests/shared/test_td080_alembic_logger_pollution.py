"""TD-080 回归：alembic fileConfig 不污染已存在 logger。

根因：``alembic/env.py`` 的 ``fileConfig(config.config_file_name)`` 默认
``disable_existing_loggers=True``，跑 migration 时把测试中已创建的 logger
设 ``disabled=True``，导致后续测试 ``caplog`` 收不到 warning（全量顺序下
``test_embedding_empty_logs_warning`` 失败）。

修复：``fileConfig(..., disable_existing_loggers=False)``。

回归策略：
1. 源码断言 env.py 传 ``disable_existing_loggers=False``（gate 防回退）。
2. 集成回归由全量 pytest 覆盖（test_dd_workbench_migration 跑 alembic
   upgrade/downgrade 后，test_embedding_empty_logs_warning 仍捕获 warning）。
"""
from __future__ import annotations


def test_alembic_env_uses_disable_existing_loggers_false():
    """断言 alembic env.py fileConfig 传 disable_existing_loggers=False。"""
    from pathlib import Path

    env_py = Path(__file__).resolve().parents[2] / "alembic" / "env.py"
    src = env_py.read_text(encoding="utf-8")
    assert "disable_existing_loggers=False" in src, (
        "alembic/env.py fileConfig 必须传 disable_existing_loggers=False "
        "（TD-080：避免污染测试中已创建的 logger，导致后续 caplog 收不到 warning）"
    )
