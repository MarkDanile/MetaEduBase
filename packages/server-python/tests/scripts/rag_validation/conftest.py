"""`tests/scripts/rag_validation/` 局部 conftest。

将 `scripts/` 加到 sys.path，使 `from rag_validation.coverage import ...`
可解析。`_paths.py` 只插 REPO_ROOT，不插 scripts；这里补上。

不动全局 conftest.py，避免对其他测试产生副作用。
"""

from __future__ import annotations

import sys
from pathlib import Path

# tests/scripts/rag_validation/conftest.py
# → parents[0] = tests/scripts/rag_validation/
# → parents[1] = tests/scripts/
# → parents[2] = tests/
# → parents[3] = packages/server-python/
# → parents[4] = packages/
# → parents[5] = repo root  ← REPO_ROOT
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
