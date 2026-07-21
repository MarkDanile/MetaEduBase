"""Load package-local operational scripts without shadowing repo ``scripts.ai``."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"


def load_server_script(name: str) -> ModuleType:
    path = _SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"metaedu_server_script_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
