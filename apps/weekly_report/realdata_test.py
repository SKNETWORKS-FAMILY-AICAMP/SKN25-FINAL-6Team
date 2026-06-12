"""실제 DB 데이터로 주간 리포트 생성 후 Slack 전송 테스트."""

import report

result = report.run(
    days=7,
    render_pdf=True,
    send_to_slack=True,
    slack_channel="C0B5KPFN19P",
    slack_comment="[실데이터 테스트] 주간 운영 리포트",
)
print("PDF 크기:", len(result["pdf_bytes"] or b""), "bytes")
print("Slack 전송:", result["slack_result"])
