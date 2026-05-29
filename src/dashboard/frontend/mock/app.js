const dashboardState = {
  days: 30,
  risk: "all",
  source: "all",
  search: "",
  tab: "overview",
  selectedTicketId: 2042,
  autoplay: false,
  autoplayTimer: null,
};

const dashboardData = {
  overviewMetrics: [
    { label: "전체 문의", value: "482", foot: "최근 30일 누적", tone: "neutral" },
    { label: "대기 문의", value: "57", foot: "old pending 12건 포함", tone: "high" },
    { label: "종료 문의", value: "401", foot: "최종 응답 발행 완료", tone: "low" },
    { label: "오늘 접수", value: "24", foot: "커뮤니티 급증 시간대 감지", tone: "medium" },
    { label: "응답률", value: "83.2%", foot: "threshold 70% 상회", tone: "low" },
    { label: "초안 커버리지", value: "88.7%", foot: "draft linked tickets", tone: "low" },
    { label: "분석 커버리지", value: "94.1%", foot: "latest analysis 기준", tone: "low" },
    { label: "평균 응답 지연", value: "42m", foot: "final_response 기준", tone: "medium" },
  ],
  charts: {
    source: [
      { label: "community", value: 286 },
      { label: "chatbot", value: 196 },
    ],
    status: [
      { label: "closed", value: 401 },
      { label: "pending", value: 57 },
      { label: "human_review", value: 24 },
    ],
    routing: [
      { label: "rag_reply", value: 342 },
      { label: "human_review", value: 88 },
      { label: "urgent_alert", value: 52 },
    ],
    trend: [
      { day: "Thu", value: 41 },
      { day: "Fri", value: 52 },
      { day: "Sat", value: 46 },
      { day: "Sun", value: 39 },
      { day: "Mon", value: 63 },
      { day: "Tue", value: 71 },
      { day: "Wed", value: 64 },
    ],
    analysisRisk: [
      { label: "critical", value: 9 },
      { label: "high", value: 37 },
      { label: "medium", value: 118 },
      { label: "low", value: 203 },
    ],
    sentiment: [
      { label: "very_negative", value: 26 },
      { label: "negative", value: 88 },
      { label: "neutral", value: 213 },
      { label: "positive", value: 41 },
    ],
    patternRisk: [
      { label: "critical", value: 4 },
      { label: "high", value: 18 },
      { label: "medium", value: 49 },
      { label: "low", value: 73 },
    ],
    notifications: [
      { label: "sent", value: 68 },
      { label: "pending", value: 7 },
      { label: "failed", value: 3 },
    ],
  },
  safetySummary: [
    { label: "Hallucination", score: 0.42, threshold: "warn >= 0.7" },
    { label: "Toxicity", score: 0.18, threshold: "warn >= 0.7" },
    { label: "Policy", score: 0.51, threshold: "warn >= 0.7" },
    { label: "Factuality", score: 0.79, threshold: "warn <= 0.3" },
  ],
  coverageSummary: [
    { title: "근거 연결 초안", value: "91", note: "draft 103건 중 88.3%" },
    { title: "평균 relevance", value: "0.84", note: "evidence_docs.relevance_score" },
    { title: "최종 응답", value: "79", note: "ticket_count 대비 83.2%" },
    { title: "평균 최종 지연", value: "42m", note: "inquiry_created_at 대비" },
  ],
  alerts: [
    {
      id: "A-1",
      severity: "critical",
      title: "payment_delivery_mismatch",
      summary: "결제 성공 후 지급 실패 티켓이 3건 연속 감지되었습니다.",
      ticketId: 2042,
    },
    {
      id: "A-2",
      severity: "warning",
      title: "human_review_queue_spike",
      summary: "human_review 큐가 지난 1시간 대비 38% 증가했습니다.",
      ticketId: 2045,
    },
    {
      id: "A-3",
      severity: "warning",
      title: "notification_failure",
      summary: "Discord 알림 채널 전송 실패 1건이 남아 있습니다.",
      ticketId: 2040,
    },
  ],
  qualityCandidates: [
    {
      ticketId: 2045,
      title: "가챠 확률 항의 문의",
      note: "policy_violation_score 0.74 / 표현 수위 재검토 필요",
      severity: "high",
    },
    {
      ticketId: 2042,
      title: "아이템 미지급 재발 문의",
      note: "factuality_score 0.31 / 운영 로그 추가 확인 필요",
      severity: "medium",
    },
    {
      ticketId: 2038,
      title: "장애 공지 초안 점검",
      note: "긴급 알림 문구와 공지 링크 일치 여부 확인 필요",
      severity: "medium",
    },
  ],
  weeklyHighlights: [
    "이번 주 접수량은 전주 대비 18% 증가했습니다.",
    "커뮤니티 채널의 부정 감정 비율이 31%까지 상승했습니다.",
    "환불 관련 문의는 안정적이지만 지급 누락 패턴이 반복 관측되었습니다.",
    "human_review 큐의 42%가 가챠/정책 민감 문의입니다.",
  ],
  weeklyDelivery: [
    { channel: "#ops-dashboard", status: "sent", when: "09:00", note: "정기 전송 성공" },
    { channel: "#risk-watch", status: "sent", when: "09:01", note: "critical 포함 요약 전송" },
    { channel: "discord-ops", status: "failed", when: "09:02", note: "webhook timeout" },
  ],
  tickets: [
    {
      id: 2042,
      title: "결제 성공 후 아이템 미지급 재발 문의",
      body: "새벽 결제 후 우편함에 지급이 없고, 같은 문제가 두 번째 발생했습니다. 운영 로그와 결제 로그를 같이 확인해 주세요.",
      nickname: "NovaMint",
      source: "community",
      category: "item_delivery",
      risk: "critical",
      sentiment: "very_negative",
      status: "pending",
      routingTarget: "human_review",
      createdAt: "2026-05-28 09:11",
      analysis: "결제 성공 로그와 delivery fail 로그가 동시에 확인되어 payment_delivery_mismatch 패턴입니다. 반복 이력까지 있어 최우선 검토가 필요합니다.",
      draft: "안녕하세요. 결제는 정상 완료되었으나 아이템 지급 이력에서 실패 로그가 확인되었습니다. 운영 검토 대상으로 우선 접수하여 지급 여부와 재발 원인을 함께 확인하겠습니다.",
      final: "",
      evidence: [
        "payment_status=success / TXN-55A91 / paid_at=01:12",
        "delivery_status=fail / item=루비 긴급 패키지 / delivered_at=NULL",
      ],
      voc: "반복 결제 이슈로 신뢰 하락 우려",
    },
    {
      id: 2045,
      title: "가챠 확률이 비정상적으로 느껴집니다",
      body: "천장 직전까지 갔는데 동일 희귀도만 반복됩니다. 확률 구조와 로그를 운영에서 확인해 주세요.",
      nickname: "ArcVolt",
      source: "community",
      category: "gacha",
      risk: "high",
      sentiment: "negative",
      status: "human_review",
      routingTarget: "human_review",
      createdAt: "2026-05-28 08:52",
      analysis: "정책 민감 문의이며 확률 관련 설명 표현을 엄격히 관리해야 합니다. 개별 로그 확인과 고지 확률 범위 안내가 모두 필요합니다.",
      draft: "안녕하세요. 현재 소환 로그와 공지된 확률 구조를 함께 확인 중입니다. 확인이 완료되면 고지 기준에 따라 상세하게 안내드리겠습니다.",
      final: "",
      evidence: [
        "banner=은하 소환 / pity_count=78 / rarity=SR 반복",
        "정책 문서: 확률형 아이템 문의는 고지 확률 범위 내 확인 필요",
      ],
      voc: "확률형 상품에 대한 신뢰도 저하 의견",
    },
    {
      id: 2038,
      title: "패치 이후 매칭 진입 시 튕김 현상",
      body: "점검 이후 로비는 진입되지만 매칭을 누르면 종료됩니다. 서버 이슈인지 공지가 있는지 알고 싶습니다.",
      nickname: "Patchless",
      source: "community",
      category: "outage",
      risk: "high",
      sentiment: "negative",
      status: "pending",
      routingTarget: "urgent_alert",
      createdAt: "2026-05-28 08:10",
      analysis: "동일 시간대 유사 문의가 급증한 장애성 티켓입니다. 개별 답변보다 운영 공지와 알림 채널 공유가 우선입니다.",
      draft: "현재 다수 계정에서 유사 현상이 접수되어 운영 장애 확인이 진행 중입니다. 공지 업데이트 전까지 접속 시각과 기기 정보를 남겨주시면 원인 파악에 도움이 됩니다.",
      final: "",
      evidence: [
        "incident keyword spike: matching crash",
      ],
      voc: "패치 안정성 관련 불만 증가",
    },
    {
      id: 2031,
      title: "환불 처리 후 카드 명세 반영 문의",
      body: "환불이 승인됐다고 안내받았는데 카드 명세에 아직 반영되지 않았습니다. 예상 소요 시간을 알고 싶습니다.",
      nickname: "SiaWave",
      source: "chatbot",
      category: "refund",
      risk: "medium",
      sentiment: "neutral",
      status: "closed",
      routingTarget: "rag_reply",
      createdAt: "2026-05-27 17:42",
      analysis: "일반 환불 안내형 문의입니다. 카드사 반영 시차를 설명하면 충분합니다.",
      draft: "환불은 정상 승인 완료되었으며 카드사 반영까지는 영업일 기준 3~5일이 추가 소요될 수 있습니다.",
      final: "환불 승인 완료 및 카드사 반영 시차를 안내했습니다.",
      evidence: [
        "refund_status=approved / approved_at=17:12",
        "정책 문서: 카드 반영 3~5 영업일",
      ],
      voc: "환불 처리 완료 후 상태 추적성 개선 요청",
    },
    {
      id: 2040,
      title: "운영 알림이 Discord로 오지 않습니다",
      body: "Slack에는 오는데 Discord 운영 채널에는 장애 알림이 누락되는 것 같습니다.",
      nickname: "OpsKim",
      source: "chatbot",
      category: "policy",
      risk: "medium",
      sentiment: "negative",
      status: "pending",
      routingTarget: "rag_reply",
      createdAt: "2026-05-28 07:58",
      analysis: "notification_logs 실패 건과 연결되는 운영 도구 이슈입니다. 사용자 티켓보다는 시스템 관찰 이슈에 가깝습니다.",
      draft: "Discord 알림 채널 전송 실패 이력을 확인 중이며 재전송 가능 여부와 원인을 함께 점검하겠습니다.",
      final: "",
      evidence: [
        "notification_logs.status=failed / error_category=timeout",
      ],
      voc: "운영 채널 신뢰도 저하",
    },
  ],
};

const $ = (id) => document.getElementById(id);

const els = {
  daysFilter: $("daysFilter"),
  daysValue: $("daysValue"),
  riskFilter: $("riskFilter"),
  sourceFilter: $("sourceFilter"),
  searchFilter: $("searchFilter"),
  resetFilters: $("resetFilters"),
  metricGrid: $("metricGrid"),
  metricTemplate: $("metricTemplate"),
  alertCount: $("alertCount"),
  alertList: $("alertList"),
  sourceChart: $("sourceChart"),
  statusChart: $("statusChart"),
  routingChart: $("routingChart"),
  trendChart: $("trendChart"),
  analysisRiskChart: $("analysisRiskChart"),
  sentimentChart: $("sentimentChart"),
  patternRiskChart: $("patternRiskChart"),
  safetySummary: $("safetySummary"),
  notificationChart: $("notificationChart"),
  coverageSummary: $("coverageSummary"),
  qualityCandidates: $("qualityCandidates"),
  weeklyHighlights: $("weeklyHighlights"),
  weeklyDelivery: $("weeklyDelivery"),
  weeklyTicketList: $("weeklyTicketList"),
  slackStatus: $("slackStatus"),
  ticketCount: $("ticketCount"),
  ticketTable: $("ticketTable"),
  ticketDetailId: $("ticketDetailId"),
  ticketDetailTitle: $("ticketDetailTitle"),
  ticketDetailMeta: $("ticketDetailMeta"),
  ticketDetailBody: $("ticketDetailBody"),
  ticketDetailRoute: $("ticketDetailRoute"),
  ticketAnalysis: $("ticketAnalysis"),
  ticketDraft: $("ticketDraft"),
  ticketFinal: $("ticketFinal"),
  ticketEvidenceCount: $("ticketEvidenceCount"),
  ticketEvidence: $("ticketEvidence"),
  ticketVoc: $("ticketVoc"),
  riskThresholdFlag: $("riskThresholdFlag"),
  simulateSpike: $("simulateSpike"),
  toggleAutoplay: $("toggleAutoplay"),
};

function riskClass(value) {
  return ["critical", "high", "medium", "low"].includes(value) ? value : "neutral";
}

function filteredTickets() {
  const keyword = dashboardState.search.trim().toLowerCase();
  return dashboardData.tickets.filter((ticket) => {
    const riskMatch = dashboardState.risk === "all" || ticket.risk === dashboardState.risk;
    const sourceMatch = dashboardState.source === "all" || ticket.source === dashboardState.source;
    const searchMatch =
      !keyword ||
      `${ticket.title} ${ticket.nickname} ${ticket.category} ${ticket.body}`.toLowerCase().includes(keyword);
    return riskMatch && sourceMatch && searchMatch;
  });
}

function selectedTicket() {
  const list = filteredTickets();
  const found = dashboardData.tickets.find((ticket) => ticket.id === dashboardState.selectedTicketId);
  if (found && list.some((ticket) => ticket.id === found.id)) return found;
  dashboardState.selectedTicketId = list[0]?.id ?? null;
  return dashboardData.tickets.find((ticket) => ticket.id === dashboardState.selectedTicketId) ?? null;
}

function renderMetrics() {
  els.metricGrid.innerHTML = "";
  dashboardData.overviewMetrics.forEach((item) => {
    const node = els.metricTemplate.content.firstElementChild.cloneNode(true);
    node.querySelector(".metric-label").textContent = item.label;
    node.querySelector(".metric-value").textContent = item.value;
    node.querySelector(".metric-foot").textContent = item.foot;
    const badge = node.querySelector(".metric-badge");
    badge.className = `metric-badge badge ${riskClass(item.tone)}`;
    badge.textContent = item.tone === "neutral" ? "info" : item.tone;
    els.metricGrid.appendChild(node);
  });
}

function renderBarChart(target, items) {
  const max = Math.max(...items.map((item) => item.value), 1);
  target.innerHTML = items
    .map(
      (item) => `
        <div class="bar-row">
          <span>${item.label}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${(item.value / max) * 100}%"></div></div>
          <strong>${item.value}</strong>
        </div>
      `
    )
    .join("");
}

function renderTrend() {
  const max = Math.max(...dashboardData.charts.trend.map((item) => item.value), 1);
  els.trendChart.innerHTML = dashboardData.charts.trend
    .map(
      (item) => `
        <div class="line-day">
          <span class="line-value">${item.value}</span>
          <div class="line-stick" style="height:${(item.value / max) * 130 + 20}px"></div>
          <span class="line-label">${item.day}</span>
        </div>
      `
    )
    .join("");
}

function renderAlerts() {
  els.alertCount.textContent = `${dashboardData.alerts.length}건`;
  els.alertList.innerHTML = dashboardData.alerts
    .map(
      (alert) => `
        <button class="alert-card" type="button" data-ticket="${alert.ticketId}">
          <div class="row-top">
            <strong>${alert.title}</strong>
            <span class="badge ${riskClass(alert.severity)}">${alert.severity}</span>
          </div>
          <p class="body-copy">${alert.summary}</p>
        </button>
      `
    )
    .join("");

  els.alertList.querySelectorAll("[data-ticket]").forEach((node) => {
    node.addEventListener("click", () => {
      dashboardState.selectedTicketId = Number(node.dataset.ticket);
      renderAll();
    });
  });
}

function renderRiskSection() {
  renderBarChart(els.analysisRiskChart, dashboardData.charts.analysisRisk);
  renderBarChart(els.sentimentChart, dashboardData.charts.sentiment);
  renderBarChart(els.patternRiskChart, dashboardData.charts.patternRisk);
  els.safetySummary.innerHTML = dashboardData.safetySummary
    .map(
      (item) => `
        <article class="score-card">
          <strong>${item.label}</strong>
          <div class="row-top">
            <span class="badge ${item.label === "Factuality" ? "low" : item.score >= 0.7 ? "high" : "medium"}">${item.score.toFixed(2)}</span>
            <span class="muted">${item.threshold}</span>
          </div>
        </article>
      `
    )
    .join("");
}

function renderQualitySection() {
  renderBarChart(els.notificationChart, dashboardData.charts.notifications);
  els.coverageSummary.innerHTML = dashboardData.coverageSummary
    .map(
      (item) => `
        <article class="summary-card">
          <strong>${item.title}</strong>
          <div class="metric-value">${item.value}</div>
          <p class="metric-foot">${item.note}</p>
        </article>
      `
    )
    .join("");

  els.qualityCandidates.innerHTML = dashboardData.qualityCandidates
    .map(
      (item) => `
        <article class="alert-card">
          <div class="row-top">
            <strong>#${item.ticketId} ${item.title}</strong>
            <span class="badge ${riskClass(item.severity)}">${item.severity}</span>
          </div>
          <p class="body-copy">${item.note}</p>
        </article>
      `
    )
    .join("");
}

function renderWeeklySection() {
  els.weeklyHighlights.innerHTML = dashboardData.weeklyHighlights
    .map((text) => `<article class="detail-card"><strong>핵심 요약</strong><p class="body-copy">${text}</p></article>`)
    .join("");

  els.weeklyDelivery.innerHTML = dashboardData.weeklyDelivery
    .map(
      (item) => `
        <article class="detail-card">
          <div class="row-top">
            <strong>${item.channel}</strong>
            <span class="badge ${item.status === "failed" ? "high" : "low"}">${item.status}</span>
          </div>
          <p class="body-copy">${item.when} · ${item.note}</p>
        </article>
      `
    )
    .join("");

  const failedExists = dashboardData.weeklyDelivery.some((item) => item.status === "failed");
  els.slackStatus.className = `badge ${failedExists ? "medium" : "low"}`;
  els.slackStatus.textContent = failedExists ? "부분 실패" : "정상";

  els.weeklyTicketList.innerHTML = dashboardData.tickets
    .slice(0, 4)
    .map(
      (ticket) => `
        <button class="ticket-row" type="button" data-ticket="${ticket.id}">
          <div class="row-top">
            <strong>#${ticket.id} ${ticket.title}</strong>
            <span class="badge ${riskClass(ticket.risk)}">${ticket.risk}</span>
          </div>
          <div class="row-meta">
            <span>${ticket.category}</span>
            <span>${ticket.routingTarget}</span>
            <span>${ticket.createdAt}</span>
          </div>
        </button>
      `
    )
    .join("");

  els.weeklyTicketList.querySelectorAll("[data-ticket]").forEach((node) => {
    node.addEventListener("click", () => {
      dashboardState.selectedTicketId = Number(node.dataset.ticket);
      renderDetail();
    });
  });
}

function renderTicketTable() {
  const list = filteredTickets();
  els.ticketCount.textContent = `${list.length}건`;
  els.ticketTable.innerHTML = list
    .map(
      (ticket) => `
        <button class="ticket-row ${ticket.id === dashboardState.selectedTicketId ? "active" : ""}" type="button" data-ticket="${ticket.id}">
          <div class="row-top">
            <strong>#${ticket.id} ${ticket.title}</strong>
            <span class="badge ${riskClass(ticket.risk)}">${ticket.risk}</span>
          </div>
          <div class="row-meta">
            <span>${ticket.nickname}</span>
            <span>${ticket.source}</span>
            <span>${ticket.category}</span>
            <span>${ticket.status}</span>
            <span>${ticket.routingTarget}</span>
            <span>${ticket.createdAt}</span>
          </div>
        </button>
      `
    )
    .join("");

  els.ticketTable.querySelectorAll("[data-ticket]").forEach((node) => {
    node.addEventListener("click", () => {
      dashboardState.selectedTicketId = Number(node.dataset.ticket);
      renderDetail();
      renderTicketTable();
    });
  });
}

function renderDetail() {
  const ticket = selectedTicket();
  if (!ticket) return;

  els.ticketDetailId.textContent = `ticket_id=${ticket.id}`;
  els.ticketDetailTitle.textContent = ticket.title;
  els.ticketDetailBody.textContent = ticket.body;
  els.ticketDetailBody.className = "body-copy";
  els.ticketDetailRoute.textContent = ticket.routingTarget;
  els.ticketDetailRoute.className = `badge ${riskClass(ticket.risk)}`;
  els.ticketDetailMeta.innerHTML = `
    <span class="badge neutral">${ticket.nickname}</span>
    <span class="badge neutral">${ticket.source}</span>
    <span class="badge neutral">${ticket.category}</span>
    <span class="badge neutral">${ticket.status}</span>
    <span class="badge neutral">${ticket.sentiment}</span>
  `;

  els.ticketAnalysis.innerHTML = `<strong>분석 결과</strong><p class="body-copy">${ticket.analysis}</p>`;
  els.ticketDraft.innerHTML = `<strong>답변 초안</strong><p class="body-copy">${ticket.draft || "초안 없음"}</p>`;
  els.ticketFinal.innerHTML = `<strong>최종 응답</strong><p class="body-copy">${ticket.final || "최종 응답 없음"}</p>`;
  els.ticketEvidenceCount.textContent = `${ticket.evidence.length}건`;
  els.ticketEvidence.innerHTML = ticket.evidence
    .map((item) => `<article class="detail-card"><strong>근거</strong><p class="body-copy">${item}</p></article>`)
    .join("");
  els.ticketVoc.innerHTML = `<strong>VOC</strong><p class="body-copy">${ticket.voc}</p>`;
}

function switchTab(tab) {
  dashboardState.tab = tab;
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tab}`);
  });
}

function simulateSpike() {
  dashboardData.overviewMetrics[1].value = "64";
  dashboardData.overviewMetrics[3].value = "31";
  dashboardData.charts.analysisRisk[0].value += 3;
  dashboardData.charts.analysisRisk[1].value += 6;
  dashboardData.safetySummary[0].score = 0.76;
  dashboardData.safetySummary[2].score = 0.72;
  dashboardData.alerts.unshift({
    id: `A-${Date.now()}`,
    severity: "critical",
    title: "high_risk_spike",
    summary: "최근 1시간 HIGH/critical 티켓이 급증했습니다.",
    ticketId: 2038,
  });
  els.riskThresholdFlag.textContent = "임계 초과";
  els.riskThresholdFlag.className = "badge critical";
  renderAll();
}

function toggleAutoplay() {
  dashboardState.autoplay = !dashboardState.autoplay;
  els.toggleAutoplay.textContent = `자동 변화: ${dashboardState.autoplay ? "ON" : "OFF"}`;
  if (dashboardState.autoplay) {
    dashboardState.autoplayTimer = window.setInterval(() => {
      const ticket = dashboardData.tickets[Math.floor(Math.random() * dashboardData.tickets.length)];
      dashboardState.selectedTicketId = ticket.id;
      ticket.status = ticket.status === "closed" ? "pending" : ticket.status === "pending" ? "human_review" : "closed";
      if (ticket.status === "closed" && !ticket.final) {
        ticket.final = ticket.draft;
      }
      renderAll();
    }, 4500);
  } else if (dashboardState.autoplayTimer) {
    clearInterval(dashboardState.autoplayTimer);
    dashboardState.autoplayTimer = null;
  }
}

function renderOverview() {
  renderBarChart(els.sourceChart, dashboardData.charts.source);
  renderBarChart(els.statusChart, dashboardData.charts.status);
  renderBarChart(els.routingChart, dashboardData.charts.routing);
  renderTrend();
}

function renderAll() {
  renderMetrics();
  renderAlerts();
  renderOverview();
  renderRiskSection();
  renderQualitySection();
  renderWeeklySection();
  renderTicketTable();
  renderDetail();
}

els.daysFilter.addEventListener("input", (event) => {
  dashboardState.days = Number(event.target.value);
  els.daysValue.textContent = `${dashboardState.days}일`;
});

els.riskFilter.addEventListener("change", (event) => {
  dashboardState.risk = event.target.value;
  renderAll();
});

els.sourceFilter.addEventListener("change", (event) => {
  dashboardState.source = event.target.value;
  renderAll();
});

els.searchFilter.addEventListener("input", (event) => {
  dashboardState.search = event.target.value;
  renderAll();
});

els.resetFilters.addEventListener("click", () => {
  dashboardState.days = 30;
  dashboardState.risk = "all";
  dashboardState.source = "all";
  dashboardState.search = "";
  els.daysFilter.value = "30";
  els.daysValue.textContent = "30일";
  els.riskFilter.value = "all";
  els.sourceFilter.value = "all";
  els.searchFilter.value = "";
  renderAll();
});

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

els.simulateSpike.addEventListener("click", simulateSpike);
els.toggleAutoplay.addEventListener("click", toggleAutoplay);

renderAll();
