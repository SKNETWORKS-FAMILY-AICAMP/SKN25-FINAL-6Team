"""Save the operation LangGraph structure as a PNG image."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "apps" / "cs_auto" / "backend"
COMMON_ROOT = REPO_ROOT / "packages" / "common-python" / "src"

sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(COMMON_ROOT))


GRAPH_IMAGE_PATH = Path(__file__).with_name("operation_workflow_graph.png")


def _missing_workflow_dependencies() -> list[str]:
    return [
        package
        for package in ("langsmith", "langgraph")
        if importlib.util.find_spec(package) is None
    ]


def _import_build_operation_graph():
    from workflow import build_operation_graph

    return build_operation_graph


def save_operation_workflow_graph_image(output_path: Path = GRAPH_IMAGE_PATH) -> Path:
    build_operation_graph = _import_build_operation_graph()
    rag_app = build_operation_graph()
    img_data = rag_app.get_graph().draw_mermaid_png()
    output_path.write_bytes(img_data)
    return output_path


def test_operation_workflow_graph_image_is_saved() -> None:
    import pytest

    missing = _missing_workflow_dependencies()
    if missing:
        pytest.skip(f"missing workflow dependencies: {', '.join(missing)}")

    output_path = save_operation_workflow_graph_image()

    assert output_path.exists()
    assert output_path.read_bytes().startswith(b"\x89PNG")


def test_operation_workflow_graph_contains_new_agent_nodes() -> None:
    import pytest

    missing = _missing_workflow_dependencies()
    if missing:
        pytest.skip(f"missing workflow dependencies: {', '.join(missing)}")

    build_operation_graph = _import_build_operation_graph()
    graph = build_operation_graph(compile_graph=False)

    assert "load_ticket" in graph.nodes
    assert "intake_agent" in graph.nodes
    assert "context_agent" in graph.nodes
    assert "drafting_agent" in graph.nodes
    assert "review_agent" in graph.nodes
    assert "review" in graph.nodes
    assert "finalize" in graph.nodes


if __name__ == "__main__":
    try:
        image_path = save_operation_workflow_graph_image()
        print(f"워크플로 다이어그램이 성공적으로 저장되었습니다: {image_path}")
    except Exception as exc:
        print(f"다이어그램 생성 오류: {exc}")
