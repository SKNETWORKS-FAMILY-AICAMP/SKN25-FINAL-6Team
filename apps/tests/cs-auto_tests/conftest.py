from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
for path in (
    ROOT_DIR / "apps" / "cs_auto" / "backend",
    ROOT_DIR / "packages" / "common-python" / "src",
):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

