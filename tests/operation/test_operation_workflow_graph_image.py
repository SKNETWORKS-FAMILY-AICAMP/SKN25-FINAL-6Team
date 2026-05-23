"""Save the operation LangGraph structure as a PNG image."""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.operation.workflow import build_operation_graph


GRAPH_IMAGE_PATH = Path(__file__).with_name("operation_workflow_graph.png")


def save_operation_workflow_graph_image(output_path: Path = GRAPH_IMAGE_PATH) -> Path:
    rag_app = build_operation_graph()
    img_data = rag_app.get_graph().draw_mermaid_png()
    output_path.write_bytes(img_data)
    return output_path


def test_operation_workflow_graph_image_is_saved() -> None:
    output_path = save_operation_workflow_graph_image()

    assert output_path.exists()
    assert output_path.read_bytes().startswith(b"\x89PNG")


if __name__ == "__main__":
    try:
        image_path = save_operation_workflow_graph_image()
        print(f"아키텍처 다이어그램이 성공적으로 저장되었습니다: {image_path}")
    except Exception as exc:
        print(f"다이어그램 생성 오류: {exc}")
