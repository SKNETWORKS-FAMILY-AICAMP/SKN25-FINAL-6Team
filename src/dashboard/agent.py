from deepagents import create_deep_agent

from config import settings
from dashboard.insight_agent.prompts import (
    ALERT_SUBAGENT_PROMPT,
    DASHBOARD_SYSTEM_PROMPT,
    INSIGHT_SUBAGENT_PROMPT,
    METRIC_SUBAGENT_PROMPT,
)
from dashboard.insight_agent.tools import (
    aggregate_operation_metrics,
    create_insight_record,
    detect_alert_conditions,
    load_operation_outputs,
)


dashboard_subagents = [
    {
        "name": "metric-aggregator",
        "description": "Aggregates STEP3 observability metrics from operation outputs.",
        "system_prompt": METRIC_SUBAGENT_PROMPT,
        "tools": [load_operation_outputs, aggregate_operation_metrics],
    },
    {
        "name": "insight-generator",
        "description": "Creates insight records from ticket_analysis, safety_results, and final outcomes.",
        "system_prompt": INSIGHT_SUBAGENT_PROMPT,
        "tools": [load_operation_outputs, create_insight_record],
    },
    {
        "name": "alert-router",
        "description": "Evaluates metrics and decides Slack or Discord alert conditions.",
        "system_prompt": ALERT_SUBAGENT_PROMPT,
        "tools": [aggregate_operation_metrics, detect_alert_conditions],
    },
]


agent = create_deep_agent(
    model=settings.openai_model,
    tools=[load_operation_outputs],
    system_prompt=DASHBOARD_SYSTEM_PROMPT,
    subagents=dashboard_subagents,
)
