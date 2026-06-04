(function () {
// CS 자동응답 백엔드(`/cs-auto/api`)에 공통 옵션으로 요청을 보내는 fetch 래퍼다.
async function csApi(path, options = {}) {
  const response = await fetch(`/cs-auto/api${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
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

// 백엔드 일시 값을 화면용 날짜/시간 문자열로 바꾼다.
function formatCsDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// 백엔드 시각을 현재 시점 기준 상대 시간 문자열로 바꾼다.
function formatTimeAgo(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.max(Math.floor(diffMs / 60000), 0);
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;
  return `${Math.floor(diffHour / 24)}일 전`;
}

// API의 source_type 값을 화면 표시용 채널명으로 매핑한다.
function sourceLabel(sourceType) {
  if (sourceType === "naver_cafe") return "카페";
  if (sourceType === "chatbot") return "챗봇";
  if (sourceType === "email") return "이메일";
  return sourceType || "기타";
}

// API의 위험도 값을 대문자 표준값으로 정규화한다.
function riskLevel(level) {
  return String(level || "LOW").toUpperCase();
}

function formatReviewerRole(role) {
  if (role === "admin") return "관리자";
  if (role === "reviewer") return "운영자";
  return role || "운영자";
}

// 티켓 상태와 위험도를 조합해 화면용 우선순위 배지 정보를 만든다.
function priorityMeta(status, level) {
  const normalizedLevel = riskLevel(level);
  if (normalizedLevel === "HIGH") {
    return { label: "긴급", tone: "urgent" };
  }
  if (status === "closed") {
    return { label: "완료", tone: "done" };
  }
  if (status === "open") {
    return { label: "대기", tone: "pending" };
  }
  return { label: "검토 중", tone: "review" };
}

// 티켓이 종료/완료 상태인지 판별한다.
function isDoneTicket(ticket) {
  return ticket?.status === "closed" || ticket?.status === "done" || ticket?.priorityTone === "done" || ticket?.draftStatus === "approved";
}

// 티켓이 긴급 상태인지 판별한다.
function isUrgentTicket(ticket) {
  return ticket?.priorityTone === "urgent" || riskLevel(ticket?.risk || ticket?.level) === "HIGH";
}

// 티켓이 검토 진행 상태인지 판별한다.
function isReviewTicket(ticket) {
  if (!ticket || isDoneTicket(ticket) || isUrgentTicket(ticket)) {
    return false;
  }
  return ticket.priorityTone === "review" || ticket.status === "review" || ticket.status === "pending" || Boolean(getAssignedReviewer(ticket));
}

// 티켓이 아직 처리되지 않은 대기 상태인지 판별한다.
function isPendingTicket(ticket) {
  return Boolean(ticket) && ticket.status === "open" && !isDoneTicket(ticket) && !isUrgentTicket(ticket);
}

// API 응답의 담당자 값에서 실질적인 운영자 ID만 추출한다.
function isTodayTicket(ticket) {
  if (!ticket?.inquiryCreatedAt) return false;
  const date = new Date(ticket.inquiryCreatedAt);
  if (Number.isNaN(date.getTime())) return false;
  const now = new Date();
  return date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate();
}

function getAssignedReviewer(ticket) {
  const reviewer = ticket?.assignee;
  if (!reviewer || reviewer === "unassigned" || reviewer === "미할당") {
    return null;
  }
  return reviewer;
}

// 티켓 상태에 맞는 화면 표시용 상태 문구를 만든다.
function getStatusText(ticket) {
  if (isDoneTicket(ticket)) {
    return "종료 처리";
  }
  const reviewer = getAssignedReviewer(ticket);
  if (reviewer) {
    return `${reviewer} 검토 중`;
  }
  return "대기 중";
}

// 티켓 상태 문구에 적용할 스타일 클래스를 반환한다.
function getStatusTextClass(ticket) {
  if (isDoneTicket(ticket)) {
    return "font-medium text-alert-green";
  }
  return getAssignedReviewer(ticket) ? "font-semibold text-alert-amber" : "font-normal text-ink-500";
}

// 현재 운영자/티켓 상태 기준으로 상태 배지 색상을 결정한다.
function getStatusBubbleClass(ticket) {
  if (!appState.currentReviewer) {
    return "bg-sand-100 text-ink-700 border border-sand-300";
  }
  if (isDoneTicket(ticket)) {
    return "bg-alert-greenBg text-alert-green";
  }
  if (getAssignedReviewer(ticket)) {
    return "bg-alert-amberBg text-alert-amber";
  }
  return "bg-brand-500/10 text-brand-500";
}

// 사이드 탭 조건에 맞는 티켓인지 판별한다.
function matchesSideTab(ticket, label) {
  if (label === SIDE_TAB_ALL) {
    return true;
  }
  if (label === SIDE_TAB_PENDING) {
    return isPendingTicket(ticket);
  }
  if (label === SIDE_TAB_URGENT) {
    return isUrgentTicket(ticket);
  }
  return true;
}

// 상단 필터 조건에 맞는 티켓인지 판별한다.
function matchesFilter(ticket, filterLabel) {
  if (filterLabel === FILTER_ALL) {
    return true;
  }
  if (filterLabel === FILTER_PENDING) {
    return isPendingTicket(ticket);
  }
  if (filterLabel === FILTER_REVIEW) {
    return isReviewTicket(ticket);
  }
  if (filterLabel === FILTER_URGENT) {
    return isUrgentTicket(ticket);
  }
  if (filterLabel === FILTER_DONE) {
    return isDoneTicket(ticket);
  }
  return true;
}

// 현재 선택된 탭과 필터 기준으로 화면에 보여줄 티켓 목록을 계산한다.
function getVisibleTickets() {
  return appState.tickets.filter((ticket) => matchesSideTab(ticket, appState.activeSideTab) && matchesFilter(ticket, appState.activeFilter));
}

// 티켓 상태를 집계해 사이드 탭 렌더링용 카운트를 계산한다.
function getRenderedSideTabs() {
  const countTickets = Array.isArray(appState.allTickets) ? appState.allTickets : appState.tickets;
  const counts = {
    pending: countTickets.filter(isPendingTicket).length,
    urgent: countTickets.filter(isUrgentTicket).length,
  };

  return sideTabs.map((tab) => {
    if (tab.label === SIDE_TAB_ALL) {
      return { ...tab, count: "" };
    }
    if (tab.label === SIDE_TAB_PENDING) {
      return { ...tab, count: String(counts.pending) };
    }
    if (tab.label === SIDE_TAB_URGENT) {
      return { ...tab, count: String(counts.urgent), red: true };
    }
    return tab;
  });
}

// `GET /tickets...` 목록 API의 한 행을 화면 상태에서 쓰는 티켓 객체로 변환한다.
function syncTicketInAllTickets(ticket) {
  if (!ticket?.id) return;
  const existingAll = appState.allTickets.find((item) => item.id === ticket.id);
  if (existingAll) {
    Object.assign(existingAll, ticket);
  } else {
    appState.allTickets.unshift(ticket);
  }
}

function mapTicketSummary(row) {
  const priority = priorityMeta(row.status, row.risk_level);
  // [추가] 목록 API 응답의 assignee_id 사용 (기존 reviewer_id → assignee_id로 변경)
  const assignee = row.assignee_id || null;
  return {
    id: String(row.ticket_id),
    priorityLabel: priority.label,
    priorityTone: priority.tone,
    level: riskLevel(row.risk_level),
    channel: sourceLabel(row.source_type),
    sourceType: row.source_type || "unknown",
    channelIcon: row.source_type === "naver_cafe" ? "brand-blogger" : "mail",
    category: row.routing_target || row.source_type || "unclassified",
    status: row.status || "open",
    title: row.title || `Ticket ${row.ticket_id}`,
    assignee: assignee || "unassigned",
    statusText: getStatusText({ status: row.status || "open", priorityTone: priority.tone, assignee }),
    timeAgo: formatTimeAgo(row.inquiry_created_at),
    nickname: row.nickname || "-",
    accountId: row.account_id ? `account_${row.account_id}` : "-",
    createdAt: formatCsDateTime(row.inquiry_created_at),
    inquiryCreatedAt: row.inquiry_created_at || null,
    body: row.title || "",
    aiSummary: "워크플로 실행 전입니다.",
    route: row.routing_target || "unknown",
    direction: row.routing_target || "unrouted",
    risk: riskLevel(row.risk_level),
    draft: "아직 생성된 초안이 없습니다.",
    draftId: row.draft_id || null,
    draftStatus: row.draft_id ? "draft" : "draft",
    canEditDraft: Boolean(row.can_edit_draft),
    isDraftEditing: false,
    regenCount: 0,
    regenLimit: 3,
    lastGeneratedAt: row.draft_created_at ? formatCsDateTime(row.draft_created_at) : "-",
  };
}

// `GET /tickets/{ticketId}` 상세 API 응답을 appState에 병합하고 부가 패널 데이터도 갱신한다.
function applyTicketDetail(detail) {
  if (!detail || !detail.ticket) return;
  const ticketId = String(detail.ticket.ticket_id);
  const existing = appState.tickets.find((ticket) => ticket.id === ticketId);
  const latestAnalysis = detail.analyses?.[0] || null;
  const latestDraft = detail.drafts?.[0] || null;
  const latestResponse = detail.final_responses?.[0] || null;
  const latestReview = detail.review_logs?.[0] || null;
  const priority = priorityMeta(detail.ticket.status, latestAnalysis?.risk_level || existing?.risk);
  // [수정] qa_ticket.assignee_id 우선 사용 — 기존 코드는 admin_event_logs의 reviewer_id를 1순위로 써서 할당된 검토 탭 필터가 틀어지는 버그 존재
  const assignee = detail.ticket.assignee_id || latestReview?.metadata?.reviewer_id || existing?.assignee || "unassigned";
  const nextData = {
    ...(existing || {}),
    id: ticketId,
    priorityLabel: priority.label,
    priorityTone: priority.tone,
    title: detail.ticket.title || existing?.title || `Ticket ${ticketId}`,
    nickname: detail.ticket.nickname || existing?.nickname || "-",
    accountId: detail.ticket.account_id ? `account_${detail.ticket.account_id}` : existing?.accountId || "-",
    createdAt: formatCsDateTime(detail.ticket.inquiry_created_at),
    inquiryCreatedAt: detail.ticket.inquiry_created_at || existing?.inquiryCreatedAt || null,
    body: detail.ticket.raw_query || existing?.body || "",
    aiSummary: latestAnalysis?.summary || existing?.aiSummary || "분석 결과가 없습니다.",
    route: latestAnalysis?.category || existing?.route || "unknown",
    direction: latestAnalysis?.routing_target || existing?.direction || "unrouted",
    risk: riskLevel(latestAnalysis?.risk_level || existing?.risk),
    level: riskLevel(latestAnalysis?.risk_level || existing?.level),
    draft: latestResponse?.final_text || latestDraft?.draft_text || existing?.draft || "아직 생성된 초안이 없습니다.",
    draftId: latestDraft?.draft_id || existing?.draftId || null,
    draftStatus: latestResponse ? "approved" : latestDraft ? "draft" : "draft",
    canEditDraft: Boolean(detail.ticket.can_edit_draft),
    lastGeneratedAt: latestDraft?.created_at ? formatCsDateTime(latestDraft.created_at) : existing?.lastGeneratedAt || "-",
    status: detail.ticket.status || existing?.status || "open",
    sourceType: detail.ticket.source_type || existing?.sourceType || "unknown",
    assignee,
    statusText: getStatusText({
      status: detail.ticket.status || existing?.status || "open",
      priorityTone: priority.tone,
      draftStatus: latestResponse ? "approved" : latestDraft ? "draft" : "draft",
      assignee,
      risk: latestAnalysis?.risk_level || existing?.risk,
    }),
  };
  if (existing) {
    Object.assign(existing, nextData);
  } else {
    appState.tickets.unshift(nextData);
  }
  syncTicketInAllTickets(nextData);
  appState.selectedTicketId = ticketId;
  appState.evidence = (detail.evidence_docs || []).map((item, index) => ({
    rank: item.retrieval_rank || index + 1,
    source: `${item.source_type || "evidence"} / ${item.source_id || item.evidence_id || "-"}`,
    body: item.evidence_text || "",
    open: index === 0,
  }));
  appState.history = (detail.review_logs || []).map((item) => ({
    decision: item.status || item.event_type || "review",
    tone: item.status === "approved" ? "done" : item.status === "rejected" ? "urgent" : "review",
    reviewer: item.metadata?.reviewer_id || "reviewer",
    reason: item.metadata?.reason || item.status || "-",
    time: formatCsDateTime(item.created_at),
  }));
  appState.alerts = (detail.notifications || []).map((item) => ({
    title: `[${item.status || "notification"}] #${ticketId}`,
    target: item.channel || "-",
    time: `${formatCsDateTime(item.sent_at)} | ${item.status || "-"}`,
    faded: item.status !== "ok",
  }));
}

// [추가] 사이드바 탭별 API 경로 반환
// 현재 선택된 사이드 탭에 맞춰 목록 조회용 API 경로를 만든다.
function ticketApiPath(sideTab) {
  if (sideTab === SIDE_TAB_PENDING) {
    return "/tickets?status=open&limit=200";
  }
  if (sideTab === SIDE_TAB_URGENT) {
    return "/tickets?limit=200";
  }
  return "/tickets?limit=200";
}

// [추가] sideTab 파라미터 추가 — 탭별 API 경로로 호출
// `GET /tickets...` 또는 `GET /tickets/today`를 호출해 티켓 목록을 불러온다.
async function loadTicketsFromApi(sideTab) {
  const tab = sideTab || appState.activeSideTab || SIDE_TAB_PENDING;
  try {
    const listPath = ticketApiPath(tab);
    const allPath = ticketApiPath(SIDE_TAB_ALL);
    const [rows, allRows] = listPath === allPath
      ? await csApi(listPath).then((items) => [items, items])
      : await Promise.all([csApi(listPath), csApi(allPath)]);
    appState.tickets = rows.map(mapTicketSummary);
    appState.allTickets = allRows.map(mapTicketSummary);
    if (appState.tickets.length) {
      appState.selectedTicketId = appState.tickets[0].id;
      await loadTicketDetail(appState.selectedTicketId);
    }
    render();
  } catch (error) {
    console.error("failed to load tickets", error);
    showLoginError(`티켓 목록을 불러오지 못했습니다: ${error.message}`);
  }
}

// `POST /tickets/{ticketId}/assign` 후 `GET /tickets/{ticketId}`로 상세 정보를 다시 불러온다.
async function loadTicketDetail(ticketId) {
  if (!ticketId) return;
  try {
    // [추가] 티켓 선택 시 현재 운영자를 담당자로 등록 — 다른 운영자 화면에 "응대중" 표시
    if (appState.currentReviewer) {
      csApi(`/tickets/${ticketId}/assign`, {
        method: "POST",
        body: JSON.stringify({ reviewer_id: appState.currentReviewer }),
      }).catch(() => {});
    }
    const detail = await csApi(`/tickets/${ticketId}`);
    applyTicketDetail(detail);
    render();
  } catch (error) {
    console.error("failed to load ticket detail", error);
  }
}

// `POST /tickets/{ticketId}/run-workflow`를 호출해 초안 생성 워크플로를 실행한다.
async function runWorkflowForSelectedTicket() {
  const ticket = getSelectedTicket();
  if (!ticket) return;
  appState.workflowVisible = true;
  appState.workflowProgress = 15;
  appState.workflowLabel = "워크플로 실행 중...";
  render();
  try {
    // [수정] 담당자 자동 할당 제거 — 할당은 티켓 선택(loadTicketDetail) 시 처리
    await csApi(`/tickets/${ticket.id}/run-workflow`, { method: "POST" });
    await loadTicketDetail(ticket.id);
    appState.workflowVisible = true;
    appState.workflowProgress = 100;
    appState.workflowLabel = "초안 생성 완료";
    render();
  } catch (error) {
    console.error("workflow failed", error);
    showLoginError(`워크플로 실행 실패: ${error.message}`);
  }
}
const DEMO_ACCOUNTS = Object.freeze({});

// 데모 로그인 검증 후 목록 조회 API를 호출해 운영자 초기 상태를 만든다.
async function doLogin() {
  const idInput = document.getElementById("li-id");
  const pwInput = document.getElementById("li-pw");
  if (!idInput || !pwInput) return;

  const id = idInput.value.trim();
  const pw = pwInput.value;
  const err = document.getElementById("li-err");

  const adminLogin = async () => {
    const loginResult = await csApi("/auth/admin/login", {
      method: "POST",
      body: JSON.stringify({
        login_id: id,
        password: pw,
      }),
    });
    if (!loginResult.login_success) {
      showLoginError(loginResult.message || "ID 또는 비밀번호가 올바르지 않습니다.");
      return true;
    }

    if (err) err.classList.remove("show");
    appState.currentReviewer = loginResult.login_id;
    appState.currentReviewerDisplayName = loginResult.display_name || loginResult.login_id;
    appState.currentReviewerRole = formatReviewerRole(loginResult.role);
    await loadTicketsFromApi();
    render();
    return true;
  };

  if (!id) {
    showLoginError("운영자 ID를 입력하세요.");
    return;
  }

  if (await adminLogin().catch((error) => {
    console.error("admin login failed", error);
    showLoginError(error.message || "로그인에 실패했습니다.");
    return true;
  })) {
    return;
  }

  if (DEMO_ACCOUNTS[id] === undefined || DEMO_ACCOUNTS[id] !== pw) {
    showLoginError("ID 또는 비밀번호가 올바르지 않습니다.");
    return;
  }

  if (err) err.classList.remove("show");
  appState.currentReviewer = id;
  appState.currentReviewerRole = formatReviewerRole("reviewer");
  await loadTicketsFromApi();
  render();
}

// `PATCH /drafts/{draftId}`로 초안 수정 내용을 저장하거나, 로컬 편집 모드만 토글한다.
async function confirmDraft() {
  const ticket = getSelectedTicket();
  if (!ticket?.canEditDraft) {
    ticket.isDraftEditing = false;
    render();
    return;
  }
  if (ticket?.draftId && ticket.isDraftEditing) {
    try {
      await csApi(`/drafts/${ticket.draftId}`, {
        method: "PATCH",
        body: JSON.stringify({
          draft_text: ticket.draft,
          reviewer_id: appState.currentReviewer,
        }),
      });
      await loadTicketDetail(ticket.id);
    } catch (error) {
      console.error("edit draft failed", error);
      showLoginError(`초안 수정 실패: ${error.message}`);
    }
    return;
  }
  if (!ticket.isDraftEditing) {
    ticket.isDraftEditing = true;
    render();
    return;
  }

  ticket.isDraftEditing = false;
  ticket.draftStatus = "confirmed";
  ticket.confirmedDraft = ticket.draft;
  ticket.status = "review";
  ticket.priorityTone = "review";
  ticket.priorityLabel = "검토 중";
  ticket.statusText = `${appState.currentReviewer || "reviewer"} 검토 확정`;
  updateTicketHistory(ticket, "확정", "review", "AI 답변 초안 수정 후 확정");
  render();
}

// `POST /drafts/{draftId}/approve`로 초안을 승인하고 상세 정보를 다시 불러온다.
async function approveDraft() {
  const ticket = getSelectedTicket();
  if (ticket?.sourceType === "chatbot" && ticket.status === "pending") {
    try {
      await csApi(`/tickets/${ticket.id}/resolve`, {
        method: "POST",
        body: JSON.stringify({
          reviewer_id: appState.currentReviewer,
          reason: "resolved by email",
        }),
      });
      await loadTicketsFromApi();
    } catch (error) {
      console.error("resolve ticket failed", error);
      showLoginError(`처리 완료 실패: ${error.message}`);
    }
    return;
  }
  if (!ticket?.canEditDraft) {
    return;
  }
  if (ticket?.draftId) {
    try {
      await csApi(`/drafts/${ticket.draftId}/approve`, {
        method: "POST",
        body: JSON.stringify({
          final_text: ticket.draft,
          reviewer_id: appState.currentReviewer,
        }),
      });
      await loadTicketDetail(ticket.id);
    } catch (error) {
      console.error("approve draft failed", error);
      showLoginError(`승인 실패: ${error.message}`);
    }
    return;
  }
  ticket.isDraftEditing = false;
  ticket.draftStatus = "approved";
  ticket.approvedDraft = ticket.draft;
  ticket.status = "done";
  ticket.priorityTone = "done";
  ticket.priorityLabel = "완료";
  ticket.statusText = `${appState.currentReviewer || "reviewer"} 승인 완료`;
  updateTicketHistory(ticket, "승인", "done", "AI 답변 초안 바로 승인");
  render();
}

// `POST /drafts/{draftId}/reject` 후 워크플로를 재실행해 초안을 다시 생성한다.
async function regenerateDraft() {
  const ticket = getSelectedTicket();
  if (!ticket?.canEditDraft) {
    return;
  }
  const reason = appState.regenReason.trim();
  if ((ticket.regenCount || 0) >= (ticket.regenLimit || 3) || !reason) {
    return;
  }
  try {
    if (ticket?.draftId) {
      await csApi(`/drafts/${ticket.draftId}/reject`, {
        method: "POST",
        body: JSON.stringify({
          reason,
          reviewer_id: appState.currentReviewer,
        }),
      });
    } else {
      await csApi(`/tickets/${ticket.id}/run-workflow`, { method: "POST" });
    }
      appState.showRegenBox = false;
      appState.regenReason = "";
      await loadTicketDetail(ticket.id);
    } catch (error) {
      console.error("regenerate draft failed", error);
      showLoginError(`재생성 실패: ${error.message}`);
    }
    return;
  }

/*
  ticket.regenCount = (ticket.regenCount || 0) + 1;
  ticket.isDraftEditing = false;
  ticket.draftStatus = "draft";
  ticket.status = "review";
  ticket.priorityTone = "review";
  ticket.priorityLabel = "검토 중";
  ticket.statusText = `${appState.currentReviewer || "reviewer"} 재생성 검토 중`;
  updateTicketHistory(ticket, "재생성", "pending", `재생성 ${ticket.regenCount}회 · 사유: ${reason}`);
  appState.showRegenBox = false;
  appState.regenReason = "";
  startWorkflow(() => {
    ticket.draft = getDraftRegenerationText(ticket, reason);
    ticket.lastGeneratedAt = timeStampLabel();
    render();
  });
}
*/

window.CsAutoApi = {
  approveDraft,
  confirmDraft,
  csApi,
  doLogin,
  getAssignedReviewer,
  getRenderedSideTabs,
  getStatusBubbleClass,
  getStatusText,
  getStatusTextClass,
  getVisibleTickets,
  isDoneTicket,
  isPendingTicket,
  isReviewTicket,
  isUrgentTicket,
  loadTicketDetail,
  loadTicketsFromApi,
  regenerateDraft,
  runWorkflowForSelectedTicket,
};
})();
