"""Background scheduler for the weekly dashboard report."""

from __future__ import annotations

import logging
import os
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .service import run_weekly_report_workflow


LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


def _scheduled_weekly_report_job() -> None:
    channel = (os.environ.get("DASHBOARD_WEEKLY_REPORT_CHANNEL") or "").strip()
    if not channel:
        LOGGER.info("weekly report scheduler skipped: DASHBOARD_WEEKLY_REPORT_CHANNEL not configured")
        return
    try:
        run_weekly_report_workflow(
            7,
            send_to_slack=True,
            slack_channel=channel,
            slack_comment=os.environ.get("DASHBOARD_WEEKLY_REPORT_COMMENT"),
        )
        LOGGER.info("weekly report sent to Slack channel %s", channel)
    except Exception:  # noqa: BLE001 - scheduler must not crash the API
        LOGGER.exception("weekly report scheduler failed")


def create_weekly_report_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=KST)
    scheduler.add_job(
        _scheduled_weekly_report_job,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=KST),
        id="dashboard_weekly_report",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def start_weekly_report_scheduler() -> BackgroundScheduler | None:
    enabled = os.environ.get("DASHBOARD_WEEKLY_REPORT_AUTOSTART", "1").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        LOGGER.info("weekly report scheduler disabled by DASHBOARD_WEEKLY_REPORT_AUTOSTART")
        return None
    channel = (os.environ.get("DASHBOARD_WEEKLY_REPORT_CHANNEL") or "").strip()
    if not channel:
        LOGGER.info("weekly report scheduler not started because channel is not configured")
        return None
    scheduler = create_weekly_report_scheduler()
    scheduler.start()
    LOGGER.info("weekly report scheduler started")
    return scheduler

