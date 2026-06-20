#!/usr/bin/env python3
"""REQ-024 P2 real validation — thin entry (TD-032 slice 8 split).

Logic lives in the `rag_validation` package (sibling directory). This file
keeps the historical invocation path stable:
``python scripts/validate_req024_p2_real_validation.py ...``

By default it does not call an external LLM provider; pass --allow-llm for
true LLM validation. See ``rag_validation/main.py`` for arg parsing and
orchestration.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag_validation import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
