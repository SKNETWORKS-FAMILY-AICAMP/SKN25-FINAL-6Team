from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


PROMPT_ROOT = Path(
    os.environ.get(
        "CS_AUTO_PROMPT_DIR",
        Path(__file__).resolve().parents[4] / "data" / "prompts" / "cs_auto",
    )
)


def load_prompt_template(relative_path: str) -> str:
    path = PROMPT_ROOT / relative_path
    raw_data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(raw_data, str):
        return raw_data.strip()
    if isinstance(raw_data, dict) and isinstance(raw_data.get("template"), str):
        return raw_data["template"].strip()
    raise ValueError(f"Prompt YAML must be a string or contain 'template': {path}")


def render_prompt_template(relative_path: str, **kwargs: object) -> str:
    return load_prompt_template(relative_path).format(**kwargs)
