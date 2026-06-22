from __future__ import annotations

from fastapi.responses import JSONResponse


def test_trigger_report_links_trace(monkeypatch):
    captured: dict[str, object] = {}

    def fake_link(payload, **kwargs):
        captured["payload"] = payload
        captured["kwargs"] = kwargs

    def fake_run(**kwargs):
        return {
            "report": {"title": "Weekly Report"},
            "pdf_bytes": b"%PDF-test",
            "slack_result": None,
        }

    monkeypatch.setattr("api.main.link_weekly_report_trace", fake_link)
    monkeypatch.setattr("report.run", fake_run)
    monkeypatch.setenv("DASHBOARD_WEEKLY_REPORT_CHANNEL", "")
    monkeypatch.delenv("DASHBOARD_WEEKLY_REPORT_COMMENT", raising=False)

    from api.main import trigger_report

    response = trigger_report()

    assert isinstance(response, JSONResponse)
    assert captured["payload"] == {
        "status": "ok",
        "pdf_bytes": len(b"%PDF-test"),
        "slack_sent": False,
    }
    assert captured["kwargs"]["status"] == "ok"
    assert captured["kwargs"]["pdf_rendered"] is True
