"""weekly_report_tests 패키지 공통 설정.

apps/weekly_report 와 packages/common-python/src 를 sys.path 최상단에 추가해
각 테스트 파일이 상대 경로 없이 모듈을 임포트할 수 있게 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]

for path in reversed(
    [
        ROOT_DIR / "apps" / "weekly_report",
        ROOT_DIR / "packages" / "common-python" / "src",
    ]
):
    # reversed()로 순서를 뒤집어 insert(0) 하면 목록 앞쪽 경로가 sys.path[0]에 놓인다.
    # 결과적으로 weekly_report > common-python 우선순위가 유지된다.
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)
