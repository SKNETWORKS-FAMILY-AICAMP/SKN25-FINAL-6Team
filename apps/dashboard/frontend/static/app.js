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

window.addEventListener("load", () => {
  donut("c1", ["?대찓??", "移댄럹"], [68, 32], [C1, C2]);
  donut("c2", ["寃곗젣", "怨꾩젙", "踰꾧렇", "?섎텋", "湲고?"], [35, 22, 18, 15, 10], [C1, C2, C3, AMBC, `${C4}99`]);
  donut("c3", ["?꾨즺", "?湲?", "寃??", "湲닿툒"], [85, 12, 4, 3], [GRN, AMBC, PUR, RED]);
  donut("c4", ["?먮룞泥섎━", "?대떦??", "?먯뒪而?", "?щ텇??"], [45, 30, 15, 10], [C1, C2, AMB, C3]);
  donut("c5", ["AI", "?대떦??", "?쇳빀"], [55, 32, 13], [C1, C2, C3]);
  line("c6", ["5/22", "5/23", "5/24", "5/25", "5/26", "5/27", "5/28"], [18, 22, 25, 20, 28, 24, 25]);
  donut("r1", ["??쓬", "以묎컙", "?믪쓬", "移섎챸"], [45, 28, 19, 8], [GRN, AMBC, RED, PUR]);
  donut("r2", ["湲띿젙", "以묐┰", "遺??"], [52, 25, 23], [GRN, C3, RED]);
  hbar("r3", ["寃곗젣", "怨꾩젙", "踰꾧렇", "?섎텋"], [4, 2, 1, 2], [RED, AMB, C1, RED]);
  donut("r4", ["??쓬", "以묎컙", "?믪쓬"], [50, 30, 20], [C2, AMBC, RED]);
  bar("r5", ["諛섎났A", "諛섎났B", "諛섎났C", "諛섎났D"], [8, 5, 3, 2], RED);
  donut("r6", ["?대찓??", "移댄럹"], [75, 25], [RED, AMB]);
  donut("q1", ["?깃났", "?ㅽ뙣", "?湲?"], [88, 5, 7], [GRN, RED, AMBC]);
  donut("q2", ["?대찓??", "移댄럹"], [80, 20], [RED, AMB]);
  bar("q3", ["0媛?", "1媛?", "2媛?", "3媛?"], [8, 45, 35, 12], C1);
  donut("q4", ["SMTP", "二쇱냼?ㅻ쪟", "?쒓컙珥덇낵"], [60, 30, 10], [RED, AMB, C2]);
  hbar("q5", ["洹쇨굅?쇱튂", "?섍컖", "?뺤콉?꾨컲", "?ъ떎??"], [0.89, 0.23, 0.41, 0.87], [GRN, AMBC, RED, C1]);
  donut("w1", ["寃곗젣", "怨꾩젙", "踰꾧렇", "?섎텋"], [38, 24, 20, 18], [C1, C2, C3, AMBC]);
  donut("w2", ["??쓬", "以묎컙", "?믪쓬"], [55, 33, 12], [GRN, AMBC, RED]);
  donut("w3", ["AI", "?대떦??"], [60, 40], [C1, C2]);
  donut("w4", ["湲띿젙", "以묈┰", "遺??"], [55, 22, 23], [GRN, C3, RED]);
  donut("w5", ["?먮룞", "?섎룞", "?먯뒪而?"], [50, 35, 15], [C1, C2, AMB]);
  donut("w6", ["?꾨즺", "寃??", "?湲?"], [82, 10, 8], [GRN, AMBC, RED]);
});

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
    err.innerHTML = '<i class="ti ti-alert-circle"></i> ?댁쁺??ID瑜??낅젰?섏꽭??';
    return;
  }

  if (DEMO_ACCOUNTS[id] === undefined || DEMO_ACCOUNTS[id] !== pw) {
    err.classList.add("show");
    err.innerHTML = '<i class="ti ti-alert-circle"></i> ID ?먮뒗 鍮꾨?踰덊샇媛 ?щ컮瑜댁? ?딆뒿?덈떎.';
    return;
  }

  err.classList.remove("show");
  const initials = id.replace(/[^a-zA-Z媛-??-9]/g, "").slice(0, 2).toUpperCase();
  document.getElementById("op-avatar").textContent = initials || "OP";
  document.getElementById("op-name-display").textContent = id;
  document.getElementById("op-role-display").textContent = role;
  document.getElementById("op-dd-name").textContent = id;
  document.getElementById("op-dd-role").textContent = role + " 쨌 ?묒냽以?";
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

const LIVE_MSGS = ["?묐?以?", "?뺤씤以?", "寃?좎쨷"];
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
