"""集中 tests/ 顶层 conftest 共用的 sys.path / repo 路径副作用。

REQ-010: ensure repo root is on sys.path so tests can import scripts.ai.*
without making tests/ a hard-coded package consumer.

历史位置: 原本写在 ``tests/conftest.py`` L7-L11, 因 ``sys.path.insert``
出现在 import 块之前, 下游 8 个 import 全部命中 E402, 与 TD-012 收口
后保持的 ruff 全门禁冲突。

本文件只暴露 ``_REPO_ROOT`` 和副作用后的 ``sys.path`` 状态; 任何 import
``from tests._paths import *`` 的消费者都应在文件最顶部, 以保留原
``conftest.py`` 的"放在 file-top"语义。
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

__all__ = ["_REPO_ROOT"]
