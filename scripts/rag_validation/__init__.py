"""REQ-024 P2 real validation package (split from monolithic script, TD-032 slice 8).

Re-exports `main` so the thin entry `scripts/validate_req024_p2_real_validation.py`
can do ``from rag_validation import main``.
"""

from .main import main

__all__ = ["main"]
