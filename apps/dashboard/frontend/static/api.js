async function dashboardApi(path, options = {}) {
  const response = await fetch(`/dashboard/api${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch (_error) {
      detail = await response.text();
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return response.json();
}

function pct(value) {
  return `${((Number(value) || 0) * 100).toFixed(1)}%`;
}

function fmtMinutesToHours(value) {
  return `${((Number(value) || 0) / 60).toFixed(1)}h`;
}

function fmtSourceLabel(value) {
  if (value === "naver_cafe") return "移댄럹";
  if (value === "chatbot") return "梨쀫큸";
  return value || "湲고?";
}

function badgeClass(status) {
  if (status === "closed" || status === "resolved") return "b-info";
  if (status === "pending" || status === "open") return "b-pend";
  return "b-rev";
}

function riskBadgeClass(level) {
  if (String(level || "").toUpperCase() === "HIGH") return "b-hi";
  if (String(level || "").toUpperCase() === "MID") return "b-mid";
  return "b-low";
}

function hydrateOverviewPage(summary, tickets) {
  const p1 = document.getElementById("p1");
  if (!p1 || !summary) return;

  const topMetrics = p1.querySelectorAll('div[style*="font-size:36px"]');
  if (topMetrics.length >= 4) {
    topMetrics[0].textContent = summary.ticket_counts?.total ?? 0;
    topMetrics[1].textContent = summary.ticket_counts?.pending ?? 0;
    topMetrics[2].textContent = summary.ticket_counts?.closed ?? 0;
    topMetrics[3].textContent = summary.ticket_counts?.today ?? 0;
  }

  const aiHeadline = p1.querySelector(".ai-headline");
  const aiSummary = p1.querySelector(".ai-summary");
  if (aiHeadline && summary.ai_interpretation?.headline) aiHeadline.textContent = summary.ai_interpretation.headline;
  if (aiSummary && summary.ai_interpretation?.summary) aiSummary.textContent = summary.ai_interpretation.summary;

  const cards = p1.querySelectorAll(".table-card");
  const priorityBody = cards[0]?.querySelector("tbody");
  const recentBody = cards[1]?.querySelector("tbody");

  if (priorityBody) {
    priorityBody.innerHTML = (summary.priority_tickets || [])
      .slice(0, 4)
      .map(
        (item) => `
      <tr onclick="openDetail(${item.ticket_id})">
        <td style="font-family:var(--mono);font-size:10px">#${item.ticket_id}</td>
        <td style="font-weight:500;color:var(--text)">${item.title || "-"}</td>
        <td><span class="badge ${badgeClass(item.status)}">${item.status || "-"}</span></td>
        <td><span class="badge ${riskBadgeClass(item.risk_level)}">${(item.risk_level || "LOW").toUpperCase()}</span></td>
        <td><span class="tbl-assignee"><i class="ti ti-user" aria-hidden="true"></i>${item.nickname || "誘몃같??"}</span></td>
        <td><span class="live-status waiting"><span class="live-dot"></span>${item.queue_reason || "-"}</span></td>
        <td>${item.inquiry_created_at ? new Date(item.inquiry_created_at).toLocaleDateString("ko-KR") : "-"}</td>
      </tr>
    `,
      )
      .join("");
  }

  if (recentBody) {
    recentBody.innerHTML = (tickets || [])
      .slice(0, 4)
      .map(
        (item) => `
      <tr onclick="openDetail(${item.ticket_id})">
        <td style="font-family:var(--mono);font-size:10px">#${item.ticket_id}</td>
        <td style="font-weight:500;color:var(--text)">${item.title || "-"}</td>
        <td><span class="badge b-ch">${fmtSourceLabel(item.source_type)}</span></td>
        <td><span class="tbl-assignee"><i class="ti ti-user" aria-hidden="true"></i>${item.nickname || "誘몃같??"}</span></td>
        <td><span class="live-status waiting"><span class="live-dot"></span>${item.status || "-"}</span></td>
        <td style="color:var(--text3);font-size:10px">${item.inquiry_created_at ? new Date(item.inquiry_created_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }) : "-"}</td>
      </tr>
    `,
      )
      .join("");
  }
}

function hydrateRiskPage(summary) {
  const p2 = document.getElementById("p2");
  if (!p2 || !summary) return;

  const scores = p2.querySelectorAll(".risk-score");
  if (scores.length >= 4) {
    scores[0].textContent = (Number(summary.safety_score_summary?.avg_hallucination_score || 0)).toFixed(2);
    scores[1].textContent = (Number(summary.safety_score_summary?.avg_toxicity_score || 0)).toFixed(2);
    scores[2].textContent = (Number(summary.safety_score_summary?.avg_policy_violation_score || 0)).toFixed(2);
    scores[3].textContent = (Number(summary.safety_score_summary?.avg_factuality_score || 0)).toFixed(2);
  }
}

function hydrateQualityPage(summary) {
  const p3 = document.getElementById("p3");
  if (!p3 || !summary) return;

  const kpis = p3.querySelectorAll(".kpi-num");
  if (kpis.length >= 8) {
    kpis[0].textContent = summary.draft_summary?.draft_count ?? 0;
    kpis[1].textContent = summary.draft_summary?.evidence_linked_drafts ?? 0;
    kpis[2].textContent = summary.final_response_summary?.final_response_count ?? 0;
    kpis[3].textContent = summary.safety_summary?.safety_check_count ?? 0;
    kpis[4].innerHTML = pct(summary.coverage_metrics?.draft_ticket_rate);
    kpis[5].innerHTML = pct(summary.coverage_metrics?.evidence_attachment_rate);
    kpis[6].innerHTML = pct(summary.coverage_metrics?.final_response_ticket_rate);
    kpis[7].innerHTML = fmtMinutesToHours(summary.final_response_summary?.avg_final_latency_minutes);
  }
}

function drawOverviewCharts(summary) {
  if (!summary) return;
  donut("c1", (summary.source_distribution || []).map((x) => fmtSourceLabel(x.label)), (summary.source_distribution || []).map((x) => x.value), [C1, C2, C3, AMBC, C4]);
  donut("c2", (summary.category_distribution || []).map((x) => x.label), (summary.category_distribution || []).map((x) => x.value), [C1, C2, C3, AMBC, C4]);
  donut("c3", (summary.status_distribution || []).map((x) => x.label), (summary.status_distribution || []).map((x) => x.value), [GRN, AMBC, PUR, RED, C3]);
  donut("c4", (summary.routing_distribution || []).map((x) => x.label), (summary.routing_distribution || []).map((x) => x.value), [C1, C2, AMB, C3, RED]);
  donut("c5", (summary.responder_distribution || []).map((x) => x.label), (summary.responder_distribution || []).map((x) => x.value), [C1, C2, C3, AMBC]);
}

function drawRiskCharts(summary) {
  if (!summary) return;
  donut("r1", (summary.analysis_risk_distribution || []).map((x) => x.label), (summary.analysis_risk_distribution || []).map((x) => x.value), [GRN, AMBC, RED, PUR, C3]);
  donut("r2", (summary.sentiment_distribution || []).map((x) => x.label), (summary.sentiment_distribution || []).map((x) => x.value), [GRN, C3, RED, AMBC]);
  hbar("r3", (summary.risk_hotspots?.category_distribution || []).map((x) => x.label), (summary.risk_hotspots?.category_distribution || []).map((x) => x.value), [RED, AMB, C1, C3]);
  donut("r4", (summary.risk_hotspots?.source_distribution || []).map((x) => fmtSourceLabel(x.label)), (summary.risk_hotspots?.source_distribution || []).map((x) => x.value), [C2, AMBC, RED, C1]);
  hbar(
    "r5",
    ["hallucination", "toxicity", "policy", "factuality"],
    [
      Number(summary.safety_score_summary?.avg_hallucination_score || 0),
      Number(summary.safety_score_summary?.avg_toxicity_score || 0),
      Number(summary.safety_score_summary?.avg_policy_violation_score || 0),
      Number(summary.safety_score_summary?.avg_factuality_score || 0),
    ],
    [AMBC, RED, PUR, C1],
  );
}

function drawQualityCharts(summary) {
  if (!summary) return;
  donut("q1", (summary.notification_summary || []).map((x) => x.label), (summary.notification_summary || []).map((x) => x.value), [GRN, RED, AMBC, C3]);
  donut("q2", (summary.failure_distribution?.notification_channel_distribution || []).map((x) => x.label), (summary.failure_distribution?.notification_channel_distribution || []).map((x) => x.value), [RED, AMB, C2, C3]);
  bar("q3", ["draft", "evidence", "final"], [summary.draft_summary?.draft_count ?? 0, summary.evidence_summary?.evidence_count ?? 0, summary.final_response_summary?.final_response_count ?? 0], C1);
  donut("q4", (summary.failure_distribution?.notification_error_distribution || []).map((x) => x.label), (summary.failure_distribution?.notification_error_distribution || []).map((x) => x.value), [RED, AMB, C2, C3]);
  hbar("q5", ["draft_rate", "evidence_rate", "response_rate"], [Number(summary.coverage_metrics?.draft_ticket_rate || 0), Number(summary.coverage_metrics?.evidence_attachment_rate || 0), Number(summary.coverage_metrics?.final_response_ticket_rate || 0)], [C1, GRN, AMBC]);
}

function hydrateWeeklyPage(report) {
  const p4 = document.getElementById("p4");
  if (!p4 || !report) return;

  const title = p4.querySelector(".pg-title");
  const sub = p4.querySelector(".pg-sub");
  if (title && report.title) title.textContent = report.title;
  if (sub && report.window) sub.textContent = `${report.window.days}??湲곗? ${report.window.window_start?.slice(0, 10)} ~ ${report.window.window_end?.slice(0, 10)}`;

  const nums = p4.querySelectorAll(".kpi-num");
  if (nums.length >= 4) {
    nums[0].textContent = report.summary?.analysis_count ?? 0;
    nums[1].textContent = report.summary?.high_risk_count ?? 0;
    nums[2].textContent = report.summary?.negative_sentiment_count ?? 0;
    nums[3].textContent = report.summary?.human_review_count ?? 0;
  }

  const aiHeadline = p4.querySelector(".ai-headline");
  const aiSummary = p4.querySelector(".ai-summary");
  if (aiHeadline && report.ai_interpretation?.headline) aiHeadline.textContent = report.ai_interpretation.headline;
  if (aiSummary && report.ai_interpretation?.summary) aiSummary.textContent = report.ai_interpretation.summary;

  const sumVals = p4.querySelectorAll(".sum-val");
  if (sumVals.length >= 4) {
    sumVals[0].textContent = pct(report.summary?.response_rate);
    sumVals[1].textContent = pct(report.summary?.analysis_coverage_rate);
    sumVals[2].textContent = pct(report.summary?.draft_coverage_rate);
    sumVals[3].textContent = pct(report.summary?.final_response_ticket_rate);
  }

  const actions = p4.querySelectorAll(".action-item");
  (report.ai_interpretation?.actions || []).slice(0, actions.length).forEach((text, index) => {
    actions[index].innerHTML = `<i class="ti ti-arrow-right" aria-hidden="true"></i> ${text}`;
  });

  donut("w1", (report.category_distribution || []).map((x) => x.label), (report.category_distribution || []).map((x) => x.value), [C1, C2, C3, AMBC, C4]);
  donut("w2", (report.risk_distribution || []).map((x) => x.label), (report.risk_distribution || []).map((x) => x.value), [GRN, AMBC, RED, PUR, C3]);
  donut("w3", (report.responder_distribution || []).map((x) => x.label), (report.responder_distribution || []).map((x) => x.value), [C1, C2, C3, AMBC]);
  donut("w4", (report.sentiment_distribution || []).map((x) => x.label), (report.sentiment_distribution || []).map((x) => x.value), [GRN, C3, RED, AMBC]);
  donut("w5", (report.routing_distribution || []).map((x) => x.label), (report.routing_distribution || []).map((x) => x.value), [C1, C2, AMB, C3, RED]);
  donut("w6", ["analysis", "draft", "response"], [Number(report.summary?.analysis_coverage_rate || 0), Number(report.summary?.draft_coverage_rate || 0), Number(report.summary?.final_response_ticket_rate || 0)], [GRN, AMBC, RED]);

  const tables = p4.querySelectorAll("table.tbl tbody");
  if (tables.length >= 2) {
    tables[0].innerHTML = (report.review_rows || [])
      .slice(0, 5)
      .map(
        (row) => `
      <tr onclick="openDetail(${row.ticket_id})"><td style="font-family:var(--mono);font-size:10px">#${row.ticket_id}</td><td style="font-weight:600;color:var(--text)">${row.title || "-"}</td><td><span class="badge ${riskBadgeClass(row.risk_level)}">${(row.risk_level || "LOW").toUpperCase()}</span></td><td><span class="badge ${badgeClass(row.status)}">${row.status || "-"}</span></td><td style="color:var(--text3);font-size:10px">${row.routing_target || "-"}</td></tr>
    `,
      )
      .join("");

    tables[1].innerHTML = (report.analysis_rows || [])
      .slice(0, 8)
      .map(
        (row) => `
      <tr onclick="openDetail(${row.ticket_id})"><td style="font-family:var(--mono);font-size:10px">#${row.ticket_id}</td><td style="font-weight:500;color:var(--text)">${row.title || "-"}</td><td>${row.category || "-"}</td><td><span class="badge ${riskBadgeClass(row.risk_level)}">${(row.risk_level || "LOW").toUpperCase()}</span></td><td style="font-size:10px;color:var(--text3)">${row.routing_target || "-"}</td><td style="font-family:var(--mono);font-size:10px;color:var(--text3)">${row.analyzed_at ? row.analyzed_at.slice(5, 16).replace("T", " ") : "-"}</td></tr>
    `,
      )
      .join("");
  }
}

async function hydrateDetail(ticketId) {
  if (!ticketId) return;

  try {
    const detail = await dashboardApi(`/tickets/${ticketId}`);
    const overlay = document.getElementById("detail-overlay");
    if (!overlay) return;

    const title = overlay.querySelector("h3");
    if (title && detail.ticket?.title) title.textContent = detail.ticket.title;

    const summaryBox = overlay.querySelector('[style*="border-left:3px solid var(--c1)"]');
    if (summaryBox) {
      summaryBox.textContent = detail.analyses?.[0]?.summary || detail.ticket?.raw_query || "?곸꽭 ?곗씠?곌? ?놁뒿?덈떎.";
    }
  } catch (error) {
    console.error("failed to load detail", error);
  }
}

async function loadDashboardLiveData() {
  try {
    const [summaryAll, ticketList, weeklyReport] = await Promise.all([
      dashboardApi("/summary/all"),
      dashboardApi("/tickets?limit=12"),
      dashboardApi("/reports/weekly"),
    ]);

    hydrateOverviewPage(summaryAll.overview, ticketList.items || []);
    hydrateRiskPage(summaryAll.risk);
    hydrateQualityPage(summaryAll.quality);
    drawOverviewCharts(summaryAll.overview);
    drawRiskCharts(summaryAll.risk);
    drawQualityCharts(summaryAll.quality);
    hydrateWeeklyPage(weeklyReport);

    if ((summaryAll.overview?.priority_tickets || [])[0]?.ticket_id) {
      await hydrateDetail(summaryAll.overview.priority_tickets[0].ticket_id);
    }
  } catch (error) {
    console.error("failed to load dashboard live data", error);
  }
}
