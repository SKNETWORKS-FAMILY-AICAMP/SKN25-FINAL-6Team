from __future__ import annotations

from pathlib import Path


_SRC_CHATBOT_DIR = Path(__file__).resolve().parents[1] / "src" / "chatbot"
if _SRC_CHATBOT_DIR.exists():
    __path__.insert(0, str(_SRC_CHATBOT_DIR))
