from __future__ import annotations

import os
from pathlib import Path


PROMPT_ROOT = Path(
    os.environ.get(
        "CS_AUTO_PROMPT_DIR",
        Path(__file__).resolve().parents[4] / "data" / "prompts" / "cs_auto",
    )
)


def load_prompt_template(relative_path: str) -> str:
    path = PROMPT_ROOT / relative_path
    return path.read_text(encoding="utf-8").strip()


def render_prompt_template(relative_path: str, **kwargs: object) -> str:
    return load_prompt_template(relative_path).format(**kwargs)
