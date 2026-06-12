from datetime import datetime
from output.pdf import render_report_pdf
from output.slack import send_weekly_report_pdf

report = {
    "title": "주간 운영 리포트 전송 테스트",
    "generated_at": datetime.now().isoformat(),
    "window": {"window_start": "2026-06-05T00:00:00", "window_end": "2026-06-12T00:00:00", "days": 7},
    "previous_window": {"window_start": "2026-05-29T00:00:00", "window_end": "2026-06-05T00:00:00", "days": 7},
    "summary": {"analysis_count": 0},
    "comparisons": {
        "analysis_count": {"current": 0, "previous": 0, "change": 0, "change_rate": "데이터 없음"},
    },
    "category_counts_current": [
        {"category": "결제", "count": 0},
        {"category": "지급", "count": 0},
        {"category": "뽑기", "count": 0},
        {"category": "계정", "count": 0},
        {"category": "인게임버그", "count": 0},
    ],
    "category_counts_previous": [],
    "spike_alerts": {"hourly": [], "daily": [], "monthly": []},
    "top_requests": [],
    "ai_interpretation": {
        "headline": "테스트 모드 — 실제 데이터 없음",
        "actions": [],
    },
}

pdf = render_report_pdf(report)
print(f"PDF 생성: {len(pdf)} bytes")

result = send_weekly_report_pdf(
    pdf_bytes=pdf,
    channel="C0B5KPFN19P",
    filename="test.pdf",
    title="전송 테스트",
    comment="슬랙 전송 테스트",
)
print("성공:", result)
