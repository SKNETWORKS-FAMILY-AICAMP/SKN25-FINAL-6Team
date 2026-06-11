"""대시보드 테스트 공통 설정.

Python 경로와 한글 폰트 환경변수를 테스트 실행 전에 초기화한다.
이 파일은 pytest가 자동으로 로드하므로 별도 import가 필요 없다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]

# Windows 환경에서만 맑은 고딕 폰트 경로를 환경변수에 주입한다.
# 파일이 없으면(Linux/CI 등) 세팅하지 않아서 pdf.py가 /usr/share/fonts/... 경로를 탐색하도록 한다.
# Docker 이미지에는 fonts-nanum이 설치되어 있으므로 Linux에서는 NanumGothic이 사용된다.
_WINDOWS_FONT_REGULAR = Path(r"C:\Windows\Fonts\malgun.ttf")
_WINDOWS_FONT_BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")
if _WINDOWS_FONT_REGULAR.exists():
    os.environ.setdefault("DASHBOARD_WEEKLY_REPORT_FONT_REGULAR", str(_WINDOWS_FONT_REGULAR))
if _WINDOWS_FONT_BOLD.exists():
    os.environ.setdefault("DASHBOARD_WEEKLY_REPORT_FONT_BOLD", str(_WINDOWS_FONT_BOLD))

# 대시보드 백엔드와 공통 패키지를 sys.path에 추가한다.
for path in reversed(
    [
        ROOT_DIR / "apps" / "dashboard" / "backend",
        ROOT_DIR / "packages" / "common-python" / "src",
    ]
):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)
