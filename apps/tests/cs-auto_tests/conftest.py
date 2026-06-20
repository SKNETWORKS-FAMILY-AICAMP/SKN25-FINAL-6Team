from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
os.environ.setdefault("CS_AUTO_KEYWORD_DIR", str(ROOT_DIR / "data" / "keywords"))

for path in reversed(
    [
        ROOT_DIR,
        ROOT_DIR / "apps" / "cs_auto" / "backend",
    ]
):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

