const C1 = "#6096B4";
const C2 = "#93BFCF";
const C3 = "#BDCDD6";
const C4 = "#EEE9DA";
const RED = "#C0392B";
const AMB = "#9A6B1A";
const GRN = "#2E7D5B";
const PUR = "#5B4B8A";
const AMBC = "#E9B857";

const CHART_REGISTRY = {};
const OPTS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: "bottom", labels: { boxWidth: 10, padding: 8, font: { family: "Pretendard", size: 10 } } },
    tooltip: { bodyFont: { family: "Pretendard", size: 11 }, titleFont: { family: "Pretendard", size: 11 } },
  },
  scales: { x: { display: false }, y: { display: false } },
};
const DONUT_OPTS = { ...OPTS, scales: {} };
const BAR_OPTS = {
  ...OPTS,
  scales: {
    x: { display: true, ticks: { font: { family: "Pretendard", size: 10 } }, grid: { display: false } },
    y: { display: true, ticks: { font: { family: "Pretendard", size: 10 } }, grid: { color: "rgba(0,0,0,0.05)" } },
  },
};

function resetChart(id) {
  if (CHART_REGISTRY[id]) {
    CHART_REGISTRY[id].destroy();
    CHART_REGISTRY[id] = null;
  }
}

function donut(id, labels, data, colors) {
  const el = document.getElementById(id);
  if (!el) return;
  resetChart(id);
  CHART_REGISTRY[id] = new Chart(el, {
    type: "doughnut",
    data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0, hoverOffset: 3 }] },
    options: { ...DONUT_OPTS, cutout: "60%" },
  });
}

function bar(id, labels, data, color) {
  const el = document.getElementById(id);
  if (!el) return;
  resetChart(id);
  CHART_REGISTRY[id] = new Chart(el, {
    type: "bar",
    data: { labels, datasets: [{ data, backgroundColor: color, borderRadius: 4, borderSkipped: false }] },
    options: BAR_OPTS,
  });
}

function line(id, labels, data) {
  const el = document.getElementById(id);
  if (!el) return;
  resetChart(id);
  CHART_REGISTRY[id] = new Chart(el, {
    type: "line",
    data: {
      labels,
      datasets: [{ data, borderColor: C1, backgroundColor: "rgba(96,150,180,0.08)", tension: 0.3, fill: true, pointRadius: 2, pointBackgroundColor: C1 }],
    },
    options: {
      ...OPTS,
      scales: {
        x: { display: true, ticks: { font: { family: "Pretendard", size: 10 } }, grid: { display: false } },
        y: { display: true, ticks: { font: { family: "Pretendard", size: 10 } }, grid: { color: "rgba(0,0,0,0.05)" } },
      },
    },
  });
}

function hbar(id, labels, data, colors) {
  const el = document.getElementById(id);
  if (!el) return;
  resetChart(id);
  CHART_REGISTRY[id] = new Chart(el, {
    type: "bar",
    data: { labels, datasets: [{ data, backgroundColor: colors, borderRadius: 4, borderSkipped: false }] },
    options: {
      ...OPTS,
      indexAxis: "y",
      scales: {
        x: { display: true, ticks: { font: { family: "Pretendard", size: 10 } }, grid: { color: "rgba(0,0,0,0.05)" } },
        y: { display: true, ticks: { font: { family: "Pretendard", size: 10 } }, grid: { display: false } },
      },
    },
  });
}

loadDashboardLiveData();

function switchPage(id, el) {
  document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
  document.querySelectorAll(".tb-tab").forEach((t) => t.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  el.classList.add("active");
}

function activateSide(el) {
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
  el.classList.add("active");
}

function toggleColl(btn) {
  btn.classList.toggle("open");
  btn.nextElementSibling.classList.toggle("open");
}

function openDetail(ticketId) {
  document.getElementById("detail-overlay").classList.add("open");
  if (ticketId) hydrateDetail(ticketId);
}

function closeDetail() {
  document.getElementById("detail-overlay").classList.remove("open");
}

function closeDetailOutside(e) {
  if (e.target === document.getElementById("detail-overlay")) closeDetail();
}

const DEMO_ACCOUNTS = {
  reviewer_01: "cs1234",
  reviewer_02: "cs1234",
  reviewer_03: "cs1234",
  admin: "admin00",
};

function doLogin() {
  const id = document.getElementById("li-id").value.trim();
  const pw = document.getElementById("li-pw").value;
  const role = document.getElementById("li-role").value;
  const err = document.getElementById("li-err");

  if (!id) {
    err.classList.add("show");
    err.innerHTML = '<i class="ti ti-alert-circle"></i> ID를 입력해주세요.';
    return;
  }

  if (DEMO_ACCOUNTS[id] === undefined || DEMO_ACCOUNTS[id] !== pw) {
    err.classList.add("show");
    err.innerHTML = '<i class="ti ti-alert-circle"></i> ID 또는 비밀번호가 올바르지 않습니다.';
    return;
  }

  err.classList.remove("show");
  const initials = id.replace(/[^a-zA-Z0-9]/g, "").slice(0, 2).toUpperCase();
  document.getElementById("op-avatar").textContent = initials || "OP";
  document.getElementById("op-name-display").textContent = id;
  document.getElementById("op-role-display").textContent = role;
  document.getElementById("op-dd-name").textContent = id;
  document.getElementById("op-dd-role").textContent = role + " · 접속중";
  document.getElementById("login-overlay").classList.add("hidden");
}

function doLogout() {
  document.getElementById("op-dropdown").classList.remove("open");
  document.getElementById("li-id").value = "";
  document.getElementById("li-pw").value = "";
  document.getElementById("li-err").classList.remove("show");
  document.getElementById("login-overlay").classList.remove("hidden");
}

function toggleOpMenu(e) {
  e.stopPropagation();
  document.getElementById("op-dropdown").classList.toggle("open");
}

document.addEventListener("click", () => {
  const dd = document.getElementById("op-dropdown");
  if (dd) dd.classList.remove("open");
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeDetail();
});

function showLoading(on) {
  document.getElementById("loading-overlay")?.classList.toggle("show", on);
}

function showToast(msg, type = "error") {
  const container = document.getElementById("toast");
  if (!container) return;
  const icon = type === "success" ? "ti-circle-check" : "ti-alert-circle";
  const item = document.createElement("div");
  item.className = `toast-item ${type}`;
  item.innerHTML = `<i class="ti ${icon}" aria-hidden="true"></i><span>${msg}</span>`;
  container.appendChild(item);
  setTimeout(() => item.remove(), 3000);
}

function downloadWeeklyPdf() {
  window.open("/dashboard/api/reports/weekly/pdf");
}

async function sendWeeklySlack() {
  const btn = document.getElementById("btn-slack-send");
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="ti ti-loader-2" aria-hidden="true"></i> 전송 중…'; }
  try {
    await dashboardApi("/reports/weekly/slack/now", {
      method: "POST",
      body: JSON.stringify({ days: 7 }),
    });
    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="ti ti-send" aria-hidden="true"></i> 즉시 전송'; }
    showToast("Slack 전송이 완료되었습니다.", "success");
  } catch (err) {
    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="ti ti-send" aria-hidden="true"></i> 즉시 전송'; }
    showToast(`Slack 전송 실패: ${err.message}`, "error");
  }
}

const LIVE_MSGS = ["응대중", "확인중", "검토중"];
const LIVE_OPS = ["reviewer_01", "reviewer_02", "reviewer_03"];

function refreshLiveStatus() {
  document.querySelectorAll(".live-status:not(.waiting)").forEach((el) => {
    const op = LIVE_OPS[Math.floor(Math.random() * LIVE_OPS.length)];
    const msg = LIVE_MSGS[Math.floor(Math.random() * LIVE_MSGS.length)];
    const dot = el.querySelector(".live-dot");
    el.innerHTML = "";
    el.appendChild(dot || Object.assign(document.createElement("span"), { className: "live-dot" }));
    el.appendChild(document.createTextNode(`${op} ${msg}`));
  });
}

setInterval(refreshLiveStatus, 8000);
