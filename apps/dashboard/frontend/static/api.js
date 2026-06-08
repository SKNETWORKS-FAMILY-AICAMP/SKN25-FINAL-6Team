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
  if (value === "naver_cafe") return "네이버카페";
  if (value === "chatbot") return "챗봇";
  if (value === "email") return "이메일";
  return value || "기타";
}

function badgeClass(status) {
  if (status === "closed" || status === "resolved") return "b-info";
  if (status === "pending" || status === "open") return "b-pend";
  return "b-rev";
}

function riskBadgeClass(level) {
  if (String(level || "").toUpperCase() === "HIGH") return "b-hi";
  if (String(level || "").toUpperCase() === "MID") return "b-mid";
  if (String(level || "").toUpperCase() === "MEDIUM") return "b-mid";
  if (String(level || "").toUpperCase() === "CRITICAL") return "b-hi";
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

  const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  const rm = summary.response_metrics || {};
  const sla = summary.sla_metrics || {};
  const bl = summary.backlog_metrics || {};
  const latencyH = rm.avg_response_latency_minutes != null
    ? ((Number(rm.avg_response_latency_minutes) || 0) / 60).toFixed(1) + "h"
    : "-";

  setEl("ov-response-rate",    pct(rm.response_rate));
  setEl("ov-draft-rate",       pct(rm.draft_coverage_rate));
  setEl("ov-analysis-rate",    pct(rm.analysis_coverage_rate));
  setEl("ov-avg-latency",      latencyH);
  setEl("ov-24h-rate",         pct(sla.responded_within_24h_rate));
  setEl("ov-unanswered-rate",  pct(sla.unanswered_rate));
  setEl("ov-old-pending",      bl.old_pending_count ?? "-");
  setEl("ov-urgent-unanswered", bl.urgent_unanswered_count ?? "-");

  const tc = summary.ticket_counts || {};
  setEl("sb-total",   tc.total   ?? "-");
  setEl("sb-pending", tc.pending ?? "-");
  setEl("sb-closed",  tc.closed  ?? "-");
  setEl("sb-urgent",  bl.urgent_unanswered_count ?? "-");

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
        <td><span class="tbl-assignee"><i class="ti ti-user" aria-hidden="true"></i>${item.nickname || "미배정"}</span></td>
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
        <td><span class="tbl-assignee"><i class="ti ti-user" aria-hidden="true"></i>${item.nickname || "미배정"}</span></td>
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

  const rs = summary.risk_summary || {};
  const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  setEl("rk-high-risk",          rs.high_risk_count          ?? "-");
  setEl("rk-critical-risk",      rs.critical_risk_count      ?? "-");
  setEl("rk-human-review",       rs.human_review_count       ?? "-");
  setEl("rk-negative-sentiment", rs.negative_sentiment_count ?? "-");

  const alerts = summary.safety_alerts || {};
  const applyAlert = (dotId, stateId, isOn) => {
    const dot   = document.getElementById(dotId);
    const state = document.getElementById(stateId);
    if (dot) { dot.className = `alert-dot ${isOn ? "on" : "off"}`; }
    if (state) {
      state.className = `as-state ${isOn ? "on" : "off"}`;
      state.textContent = isOn ? "켜짐" : "꺼짐";
    }
  };
  applyAlert("rk-dot-hallucination", "rk-alert-hallucination", !!alerts.high_hallucination);
  applyAlert("rk-dot-toxicity",      "rk-alert-toxicity",      !!alerts.high_toxicity);
  applyAlert("rk-dot-policy",        "rk-alert-policy",        !!alerts.high_policy_violation);
  applyAlert("rk-dot-factuality",    "rk-alert-factuality",    !!alerts.low_factuality);
}

function hydrateQualityPage(summary, totalTickets) {
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

  const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  const setBarWidth = (id, numerator, denominator) => {
    const el = document.getElementById(id);
    if (!el) return;
    const ratio = denominator > 0 ? Math.min((Number(numerator) || 0) / denominator, 1) : 0;
    el.style.width = `${(ratio * 100).toFixed(1)}%`;
  };

  const gp = summary.pipeline_gaps || {};
  const total = Math.max(Number(totalTickets) || 1, 1);

  setEl("gp-no-analysis",  gp.tickets_without_analysis  ?? "-");
  setEl("gp-no-draft",     gp.tickets_without_draft     ?? "-");
  setEl("gp-no-response",  gp.tickets_without_response  ?? "-");
  setEl("gp-quality-rate", pct(gp.quality_watch_rate));

  setBarWidth("gp-bar-analysis",  gp.tickets_without_analysis  || 0, total);
  setBarWidth("gp-bar-draft",     gp.tickets_without_draft     || 0, total);
  setBarWidth("gp-bar-response",  gp.tickets_without_response  || 0, total);
  setBarWidth("gp-bar-quality",   (gp.quality_watch_rate || 0) * 100, 100);
}

function drawOverviewCharts(summary) {
  if (!summary) return;
  donut("c1", (summary.source_distribution || []).map((x) => fmtSourceLabel(x.label)), (summary.source_distribution || []).map((x) => x.value), [C1, C2, C3, AMBC, C4]);
  donut("c2", (summary.category_distribution || []).map((x) => x.label), (summary.category_distribution || []).map((x) => x.value), [C1, C2, C3, AMBC, C4]);
  donut("c3", (summary.status_distribution || []).map((x) => x.label), (summary.status_distribution || []).map((x) => x.value), [GRN, AMBC, PUR, RED, C3]);
  donut("c4", (summary.routing_distribution || []).map((x) => x.label), (summary.routing_distribution || []).map((x) => x.value), [C1, C2, AMB, C3, RED]);
  donut("c5", (summary.responder_distribution || []).map((x) => x.label), (summary.responder_distribution || []).map((x) => x.value), [C1, C2, C3, AMBC]);
  if (summary.daily_trend && summary.daily_trend.length > 0) {
    line("c6", summary.daily_trend.map((x) => x.label), summary.daily_trend.map((x) => x.value));
  }
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
  donut("r6", (summary.risk_hotspots?.source_distribution || []).map((x) => fmtSourceLabel(x.label)), (summary.risk_hotspots?.source_distribution || []).map((x) => x.value), [C2, AMBC, RED, C1]);
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
  if (sub && report.window) sub.textContent = `${report.window.days}일간  ${report.window.window_start?.slice(0, 10)} ~ ${report.window.window_end?.slice(0, 10)}`;

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

function _fmtDt(val) {
  if (!val) return "-";
  return String(val).slice(0, 16).replace("T", " ");
}

function _scoreColor(score) {
  const s = Number(score) || 0;
  if (s >= 0.7) return "var(--red)";
  if (s >= 0.4) return "var(--amber)";
  return "var(--green)";
}

function _setHtml(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

async function hydrateDetail(ticketId) {
  if (!ticketId) return;

  try {
    const d = await dashboardApi(`/tickets/${ticketId}`);
    const t = d.ticket || {};
    const acc = d.account || {};
    const analysis = (d.analyses || [])[0] || {};
    const draft = (d.drafts || [])[0] || {};
    const safetyResult = (d.safety_results || [])[0] || {};
    const finalResp = (d.final_responses || [])[0] || {};
    const voc = (d.voc_feedback || [])[0] || {};
    const opLogs = d.operation_logs || {};
    const wfLogs = d.workflow_logs || {};

    const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

    setEl("dtl-ticket-id", `#${t.ticket_id ?? ticketId}`);
    setEl("dtl-title", t.title || "-");
    setEl("dtl-assignee", acc.nickname ? `${acc.nickname} 담당` : "미배정");

    const badgeStatus = document.getElementById("dtl-badge-status");
    if (badgeStatus) { badgeStatus.textContent = t.status || "-"; badgeStatus.className = `badge ${badgeClass(t.status)}`; }
    const badgeRisk = document.getElementById("dtl-badge-risk");
    if (badgeRisk && analysis.risk_level) { badgeRisk.textContent = analysis.risk_level.toUpperCase(); badgeRisk.className = `badge ${riskBadgeClass(analysis.risk_level)}`; }

    _setHtml("dtl-ticket-info", `
      <div class="df df3" style="margin-bottom:8px">
        <div class="d-field"><label>상태</label><div class="dv"><span class="badge ${badgeClass(t.status)}">${t.status || "-"}</span></div></div>
        <div class="d-field"><label>접수 경로</label><div class="dv"><span class="badge b-ch">${fmtSourceLabel(t.source_type)}</span></div></div>
        <div class="d-field"><label>카테고리</label><div class="dv">${analysis.category || "-"}</div></div>
        <div class="d-field"><label>닉네임</label><div class="dv">${acc.nickname || "-"}</div></div>
        <div class="d-field"><label>세션 ID</label><div class="dv mono" style="font-size:10px">${t.session_id || "-"}</div></div>
        <div class="d-field"><label>접수 시각</label><div class="dv mono">${_fmtDt(t.inquiry_created_at)}</div></div>
      </div>
      <div class="body-txt">${t.raw_query || "원문 데이터가 없습니다."}</div>
    `);

    _setHtml("dtl-account-info", `
      <div class="df df3">
        <div class="d-field"><label>이메일</label><div class="dv masked">${acc.email || "-"}</div></div>
        <div class="d-field"><label>UID</label><div class="dv mono">${acc.uid || "-"}</div></div>
        <div class="d-field"><label>서버 권역</label><div class="dv">${acc.server_region || "-"}</div></div>
        <div class="d-field"><label>계정 상태</label><div class="dv">${acc.account_status || "-"}</div></div>
        <div class="d-field"><label>최근 로그인</label><div class="dv mono" style="font-size:10px">${_fmtDt(acc.last_login_at)}</div></div>
        <div class="d-field"><label>진행 레벨</label><div class="dv">${acc.progression_level || "-"}</div></div>
      </div>
    `);

    _setHtml("dtl-analysis", analysis.summary ? `
      <div style="font-size:12px;background:rgba(96,150,180,0.07);border-left:3px solid var(--c1);border-radius:0 7px 7px 0;padding:8px 10px;color:var(--text2);line-height:1.6;margin-bottom:8px;font-weight:400">${analysis.summary}</div>
      <div class="df" style="grid-template-columns:1fr 1fr 1fr">
        <div class="d-field"><label>분류</label><div class="dv mono" style="font-size:11px">${analysis.category || "-"}</div></div>
        <div class="d-field"><label>처리 방향</label><div class="dv mono" style="font-size:11px">${analysis.routing_target || "-"}</div></div>
        <div class="d-field"><label>위험도</label><div class="dv"><span class="badge ${riskBadgeClass(analysis.risk_level)}">${(analysis.risk_level || "").toUpperCase() || "-"}</span></div></div>
      </div>
    ` : `<div style="font-size:12px;color:var(--text3)">분석 데이터가 없습니다.</div>`);

    _setHtml("dtl-draft", draft.draft_text
      ? `<div class="body-txt" style="color:var(--text)">${draft.draft_text.replace(/\n/g, "<br>")}</div>`
      : `<div style="font-size:12px;color:var(--text3)">생성된 초안이 없습니다.</div>`);

    const evidenceDocs = d.evidence_docs || [];
    _setHtml("dtl-evidence", evidenceDocs.length
      ? evidenceDocs.slice(0, 5).map((e, i) =>
          `<div style="padding:6px 9px;background:var(--surface);border-radius:6px;font-size:11px;color:var(--text2)"><strong style="font-weight:600;color:var(--text)">#${i + 1}</strong> ${e.source_type || ""} — ${(e.evidence_text || "").slice(0, 80)}${e.evidence_text?.length > 80 ? "…" : ""}</div>`
        ).join("")
      : `<div style="font-size:12px;color:var(--text3)">첨부된 근거가 없습니다.</div>`);

    const safetyRow = (label, score) => {
      const s = Number(score) ?? null;
      const display = s !== null ? s.toFixed(2) : "-";
      return `<div style="display:flex;justify-content:space-between;background:var(--surface);border-radius:6px;padding:6px 9px;font-size:11px"><span style="color:var(--text2)">${label}</span><span style="color:${_scoreColor(s)};font-weight:700">${display}</span></div>`;
    };
    _setHtml("dtl-safety", safetyResult.hallucination_score != null ? `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px">
        ${safetyRow("환각 점수", safetyResult.hallucination_score)}
        ${safetyRow("독성 점수", safetyResult.toxicity_score)}
        ${safetyRow("정책 위반", safetyResult.policy_violation_score)}
        ${safetyRow("사실성", safetyResult.factuality_score)}
      </div>
    ` : `<div style="font-size:12px;color:var(--text3)">안전 점검 결과가 없습니다.</div>`);

    _setHtml("dtl-response", finalResp.final_text ? `
      <div style="font-size:11px;color:var(--text3);margin-bottom:6px;font-family:var(--mono)">발송 시각: ${_fmtDt(finalResp.created_at)} · ${fmtSourceLabel(t.source_type)}</div>
      <div class="body-txt" style="color:var(--text);font-size:12px">${finalResp.final_text.replace(/\n/g, "<br>")}</div>
    ` : `<div style="font-size:12px;color:var(--text3)">전송된 응답이 없습니다.</div>`);

    const vocBadge = { positive: "b-done", negative: "b-hi", neutral: "b-pend" };
    _setHtml("dtl-voc", voc.raw_content ? `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span class="badge ${vocBadge[voc.sentiment] || "b-ch"}">${voc.sentiment || "-"}</span>
        <span style="font-size:12px;color:var(--text2);font-weight:400">${voc.raw_content}</span>
      </div>
      <div style="font-size:11px;color:var(--text3);font-family:var(--mono)">수신: ${_fmtDt(voc.created_at)}</div>
    ` : `<div style="font-size:12px;color:var(--text3)">이용자 피드백이 없습니다.</div>`);

    const allOpLogs = [
      ...(opLogs.payments || []).map(r => ({ time: r.paid_at, label: "결제", detail: `${r.product_name || ""} ${r.amount || ""}${r.currency || ""}` })),
      ...(opLogs.refunds || []).map(r => ({ time: r.requested_at, label: "환불", detail: r.refund_reason || r.refund_status || "" })),
      ...(opLogs.item_delivery_logs || []).map(r => ({ time: r.delivered_at || r.expected_at, label: "아이템", detail: `${r.item_name || ""} x${r.quantity || ""}` })),
      ...(opLogs.gacha_logs || []).map(r => ({ time: r.pulled_at, label: "가챠", detail: `${r.item_name || ""} (${r.rarity || ""})` })),
    ].sort((a, b) => (b.time || "").localeCompare(a.time || "")).slice(0, 8);

    _setHtml("dtl-op-logs", allOpLogs.length
      ? allOpLogs.map(r => `<div class="log-item"><span class="lt">${_fmtDt(r.time).slice(5)}</span><span class="lm"><strong>${r.label}</strong> — ${r.detail}</span></div>`).join("")
      : `<div style="font-size:12px;color:var(--text3)">운영 처리 로그가 없습니다.</div>`);

    const adminLogs = (wfLogs.admin_event_logs || []).slice(0, 8);
    _setHtml("dtl-workflow-logs", adminLogs.length
      ? adminLogs.map(r => `<div class="log-item"><span class="lt">${_fmtDt(r.created_at).slice(5)}</span><span class="lm"><strong>${r.event_type || r.node_name || "-"}</strong> — ${r.status || ""}${r.error_message ? " · " + r.error_message : ""}</span></div>`).join("")
      : `<div style="font-size:12px;color:var(--text3)">워크플로 로그가 없습니다.</div>`);

  } catch (error) {
    console.error("failed to load detail", error);
  }
}

async function loadDashboardLiveData() {
  showLoading(true);
  try {
    const [summaryAll, ticketList, weeklyReport] = await Promise.all([
      dashboardApi("/summary/all"),
      dashboardApi("/tickets?limit=12"),
      dashboardApi("/reports/weekly"),
    ]);

    hydrateOverviewPage(summaryAll.overview, ticketList.items || []);
    hydrateRiskPage(summaryAll.risk);
    hydrateQualityPage(summaryAll.quality, summaryAll.overview?.ticket_counts?.total);
    drawOverviewCharts(summaryAll.overview);
    drawRiskCharts(summaryAll.risk);
    drawQualityCharts(summaryAll.quality);
    hydrateWeeklyPage(weeklyReport);

    if ((summaryAll.overview?.priority_tickets || [])[0]?.ticket_id) {
      await hydrateDetail(summaryAll.overview.priority_tickets[0].ticket_id);
    }
  } catch (error) {
    console.error("failed to load dashboard live data", error);
    showToast("데이터를 불러오지 못했습니다. 네트워크 상태를 확인해 주세요.", "error");
  } finally {
    showLoading(false);
  }
}
