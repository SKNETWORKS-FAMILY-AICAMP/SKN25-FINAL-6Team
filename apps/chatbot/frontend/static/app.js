tailwind.config = {
      theme: {
        extend: {
          colors: {
            brand: {
              blue: "#6096B4",
              soft: "#93BFCF",
              mist: "#BDCDD6",
              cream: "#EEE9DA",
              ink: "#102F4A"
            }
          },
          boxShadow: {
            glass: "0 30px 90px rgba(16, 47, 74, 0.16)"
          }
        }
      }
    };

document.addEventListener("DOMContentLoaded", () => {
const modalData = {
      privacy: {
        title: "개인정보 처리방침",
        body: `
          <p>계정 연동 과정에서 입력된 이메일, 비밀번호, 서버 정보는 인증 목적으로만 사용됩니다.</p>
          <ul class="mt-4 list-disc pl-5">
            <li>비밀번호는 화면이나 로그에 저장하지 않습니다.</li>
            <li>운영 화면에는 필요한 최소 정보만 표시합니다.</li>
            <li>문의 처리에 필요한 계정 식별 정보는 안전하게 관리됩니다.</li>
          </ul>
        `
      },
      terms: {
        title: "이용약관",
        body: `
          <p>Game CS Agent는 게임 문의 접수, FAQ 안내, 운영자 검수 연결을 지원하는 고객지원 서비스입니다.</p>
          <ul class="mt-4 list-disc pl-5">
            <li>AI 답변은 근거 문서와 운영 데이터 기반으로 제공됩니다.</li>
            <li>확인이 필요한 문의는 운영자 검수 대상으로 전환될 수 있습니다.</li>
            <li>서비스 악용 또는 허위 문의는 제한될 수 있습니다.</li>
          </ul>
        `
      },
      help: {
        title: "도움말",
        body: `
          <p>계정 연동이 되지 않는 경우 이메일, 비밀번호, 서버 선택 값을 다시 확인해 주세요.</p>
          <ul class="mt-4 list-disc pl-5">
            <li>비밀번호를 잊은 경우 계정 복구 절차를 이용해 주세요.</li>
            <li>서버가 다르면 계정 조회가 실패할 수 있습니다.</li>
            <li>계속 문제가 발생하면 운영자에게 문의해 주세요.</li>
          </ul>
        `
      }
    };

    const backdrop = document.getElementById("modalBackdrop");
    const title = document.getElementById("modalTitle");
    const body = document.getElementById("modalBody");
    const close = document.getElementById("modalClose");
    const loginPage = document.getElementById("loginPage");
    const chatPage = document.getElementById("chatPage");
    const linkAccountButton = document.getElementById("linkAccountButton");
    const logoutButton = document.getElementById("logoutButton");
    const chatViewButton = document.getElementById("chatViewButton");
    const newChatButton = document.getElementById("newChatButton");
    const inquiryHistoryButton = document.getElementById("inquiryHistoryButton");
    const backToChatButton = document.getElementById("backToChatButton");
    const chatMainSection = document.getElementById("chatMainSection");
    const inquiryMainSection = document.getElementById("inquiryMainSection");
    const inquiryHistoryList = document.getElementById("inquiryHistoryList");
    const chatFaqSection = document.getElementById("chatFaqSection");
    const rightPanel = document.getElementById("rightPanel");
    const faqCategoryTitle = document.getElementById("faqCategoryTitle");
    const faqList = document.getElementById("faqList");
    const chatForm = document.getElementById("chatForm");
    const chatInput = document.getElementById("chatInput");
    const chatMessages = document.getElementById("chatMessages");
    const faqByCategory = {
      payment: {
        label: "결제/환불",
        routeText: "결제나 환불과 관련된 문의를 선택하셨어요. 결제 내역과 지급 상태를 확인할 수 있도록 필요한 내용을 안내드릴게요.",
        questions: [
          "결제는 완료됐는데 아이템을 못 받았어요",
          "환불은 어떻게 하나요?",
          "결제 수단을 변경하고 싶어요",
          "구매한 상품 내역을 확인하고 싶어요",
        ],
      },
      faq: {
        label: "FAQ/가이드",
        routeText: "자주 묻는 질문과 공식 안내를 기준으로 확인해드릴게요. 궁금한 항목을 선택하거나 직접 질문을 입력해 주세요.",
        questions: [
          "초보자 가이드는 어디서 확인하나요?",
          "게임 공지는 어디서 볼 수 있나요?",
          "이벤트 보상 수령 방법이 궁금해요",
          "개인정보 처리방침을 확인하고 싶어요",
        ],
      },
      bug: {
        label: "버그/오류",
        routeText: "버그나 오류와 관련된 문의를 선택하셨어요. 발생 상황을 알려주시면 확인에 필요한 내용을 안내드릴게요.",
        questions: [
          "게임 실행 중 오류가 발생했어요",
          "화면이 멈추거나 튕겨요",
          "퀘스트 진행이 되지 않아요",
          "가챠 기록이 이상해요",
        ],
      },
      voc: {
        label: "VOC/건의",
        routeText: "건의나 의견을 남기실 수 있어요. 불편했던 점이나 개선 의견을 편하게 입력해 주세요.",
        questions: [
          "이벤트 보상이 아쉬워요",
          "개선 의견을 남기고 싶어요",
          "칭찬이나 피드백을 전달하고 싶어요",
          "불편했던 점을 말하고 싶어요",
        ],
      },
    };
    const submittedInquiries = [
      {
        id: "TCK-1001",
        type: "결제/아이템",
        title: "결제 완료 후 아이템 미지급 확인 요청",
        content: "루비 500개 패키지를 결제했지만 인벤토리와 우편함에 보이지 않습니다.",
      },
      {
        id: "TCK-1000",
        type: "계정",
        title: "계정 비밀번호 변경 방법 안내",
        content: "비밀번호 변경 경로를 확인하고 싶습니다.",
      },
    ];

    const clientState = {
      login: null,
      sessionId: Date.now(),
      inquiries: [],
      activeTicketId: null,
      previousMessages: [],
    };

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function textToHtml(value) {
      return escapeHtml(value).replaceAll("\n", "<br />");
    }

    function formatTicketTime(value) {
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

    function formatServerLabel(value) {
      const text = String(value || "");
      return text ? text.toUpperCase() : "KR";
    }

    function ticketTypeLabel(ticket) {
      return ticket.source_type || ticket.status || "inquiry";
    }

    function normalizeInquiry(ticket) {
      return {
        id: `#${ticket.ticket_id}`,
        ticketId: ticket.ticket_id,
        type: ticketTypeLabel(ticket),
        title: ticket.title || ticket.raw_query || `Ticket ${ticket.ticket_id}`,
        content: ticket.final_text || ticket.raw_query || "",
        status: ticket.status || "-",
        createdAt: ticket.inquiry_created_at,
      };
    }

    async function loadServerRegions() {
      try {
        const payload = await window.ChatbotApi.getServerRegions();
        const serverSelect = document.getElementById("server");
        if (!serverSelect || !Array.isArray(payload.items)) return;
        serverSelect.innerHTML = payload.items.map((item) => {
          const label = formatServerLabel(item);
          return `<option value="${escapeHtml(item)}">${escapeHtml(label)}</option>`;
        }).join("");
      } catch (error) {
        console.error("failed to load server regions", error);
      }
    }

    async function refreshInquiries() {
      if (!clientState.login?.user_id) {
        submittedInquiries.length = 0;
        clientState.inquiries = [];
        clientState.activeTicketId = null;
        renderInquiryHistoryPage();
        return;
      }
      const params = new URLSearchParams({
        user_id: String(clientState.login.user_id),
        limit: "20",
      });
      if (clientState.login.account_id) {
        params.set("account_id", String(clientState.login.account_id));
      }
      const items = await window.ChatbotApi.getTickets(params);
      submittedInquiries.length = 0;
      submittedInquiries.push(...items.map(normalizeInquiry));
      clientState.inquiries = items;
      clientState.activeTicketId = items[0]?.ticket_id || clientState.activeTicketId || 1;
      renderInquiryHistoryPage();
    }

    function syncLinkedAccount() {
      const login = clientState.login;
      if (!login) return;
      document.getElementById("linkedEmail").textContent = login.email || document.getElementById("email").value.trim();
      document.getElementById("linkedUid").textContent = login.game_id || "-";
      document.getElementById("linkedServer").textContent = formatServerLabel(login.server_region);
    }

    async function performLogin() {
      const email = document.getElementById("email").value.trim();
      const password = document.getElementById("password").value;
      const server = document.getElementById("server").value;
      if (!email || !password || !server) {
        openInfoModal("로그인 오류", "<p>이메일, 비밀번호, 서버를 모두 입력해 주세요.</p>");
        return;
      }
      linkAccountButton.disabled = true;
      try {
        const loginResult = await window.ChatbotApi.login({
          email,
          password,
          server_region: server,
        });
        if (!loginResult.login_success) {
          throw new Error(loginResult.message || "계정 연동에 실패했습니다.");
        }
        clientState.login = loginResult;
        clientState.previousMessages = [];
        clientState.sessionId = Date.now();
        syncLinkedAccount();
        await refreshInquiries();
        showChatPage();
      } catch (error) {
        console.error("login failed", error);
        openInfoModal("계정 연동 실패", `<p>${textToHtml(error.message || "로그인에 실패했습니다.")}</p>`);
      } finally {
        linkAccountButton.disabled = false;
      }
    }

    function openModal(key) {
      const content = modalData[key];
      title.textContent = content.title;
      body.innerHTML = content.body;
      backdrop.classList.remove("hidden");
      backdrop.classList.add("flex");
      backdrop.setAttribute("aria-hidden", "false");
    }

    function closeModal() {
      backdrop.classList.add("hidden");
      backdrop.classList.remove("flex");
      backdrop.setAttribute("aria-hidden", "true");
    }

    document.querySelectorAll("[data-modal]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        openModal(link.dataset.modal);
      });
    });

    close.addEventListener("click", closeModal);
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) closeModal();
    });
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeModal();
    });

    function showChatPage() {
      syncLinkedAccount();
      loginPage.classList.add("hidden");
      chatPage.classList.remove("hidden");
      chatPage.classList.add("flex");
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function showLoginPage() {
      clientState.previousMessages = [];
      chatPage.classList.add("hidden");
      chatPage.classList.remove("flex");
      loginPage.classList.remove("hidden");
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function addUserMessage(message) {
      const bubble = document.createElement("article");
      bubble.className = "ml-auto max-w-[56%] rounded-2xl rounded-tr-md bg-[#dcebf3] px-5 py-4 text-[15px] font-bold leading-7 text-[#153958] shadow-[0_12px_28px_rgba(96,150,180,0.13)]";
      bubble.textContent = message;
      chatMessages.appendChild(bubble);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addAssistantMessage(message) {
      const row = document.createElement("div");
      row.className = "flex items-start gap-4";
      row.innerHTML = `
        <div class="grid h-[52px] w-[52px] shrink-0 place-items-center rounded-full bg-white/65 text-[28px] text-brand-blue shadow-[0_10px_24px_rgba(16,47,74,0.08)]">✦</div>
        <article class="max-w-[520px] rounded-2xl rounded-tl-md bg-white/82 px-5 py-4 text-[15px] font-semibold leading-7 text-[#153958] shadow-[0_12px_30px_rgba(16,47,74,0.08)]">
          ${textToHtml(message)}
          <div class="mt-3 text-xs font-bold text-[#6c8799]">방금 전</div>
        </article>
      `;
      chatMessages.appendChild(row);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function openInfoModal(titleText, bodyHtml) {
      title.textContent = titleText;
      body.innerHTML = bodyHtml;
      backdrop.classList.remove("hidden");
      backdrop.classList.add("flex");
      backdrop.setAttribute("aria-hidden", "false");
    }

    function renderInquiryHistory() {
      if (!submittedInquiries.length) {
        return `
          <div class="rounded-xl border border-dashed border-brand-blue/15 bg-white/55 p-6 text-center text-sm font-semibold text-[#5b7890]">
            아직 저장된 문의 이력이 없습니다.
          </div>
        `;
      }
      return `
        <ul class="space-y-3">
          ${submittedInquiries.map((item) => `
            <li class="rounded-xl bg-white/70 p-4">
              <div class="mb-1 flex items-center justify-between gap-3">
                <span class="text-xs font-black text-brand-blue">${item.id}</span>
                <span class="text-xs font-bold text-[#6c8799]">${formatTicketTime(item.createdAt)}</span>
              </div>
              <p class="text-sm font-bold text-[#5b7890]">${item.type}</p>
              <p class="mt-1">${item.title}</p>
              <p class="mt-2 max-h-12 overflow-hidden text-sm font-semibold leading-6 text-[#6c8799]">${item.content}</p>
            </li>
          `).join("")}
        </ul>
      `;
    }

    function renderInquiryHistoryPage() {
      if (!submittedInquiries.length) {
        inquiryHistoryList.innerHTML = `
          <article class="rounded-2xl border border-dashed border-brand-blue/15 bg-white/60 p-8 text-center text-sm font-semibold text-[#5b7890]">
            문의 이력이 아직 없습니다.
          </article>
        `;
        return;
      }
      inquiryHistoryList.innerHTML = submittedInquiries.map((item) => `
        <article class="rounded-2xl border border-brand-blue/12 bg-white/72 p-5 shadow-[0_12px_30px_rgba(16,47,74,0.05)]">
          <div class="mb-3 flex items-start justify-between gap-4">
            <div>
              <p class="text-xs font-black uppercase tracking-[0.14em] text-brand-blue">${item.id}</p>
              <h2 class="mt-1 text-xl font-black text-[#153958]">${item.title}</h2>
            </div>
            <div class="rounded-full bg-[#dcebf3] px-3 py-2 text-xs font-black text-[#244762]">${item.status || "-"}</div>
          </div>
          <div class="mb-4 flex flex-wrap gap-2 text-sm font-black text-[#5b7890]">
            <span class="rounded-full bg-[#f5efe2] px-3 py-2">유형: ${item.type}</span>
            <span class="rounded-full bg-[#f5efe2] px-3 py-2">계정: ${document.getElementById("linkedEmail").textContent}</span>
            <span class="rounded-full bg-[#f5efe2] px-3 py-2">시간: ${formatTicketTime(item.createdAt)}</span>
          </div>
          <p class="whitespace-pre-line rounded-xl bg-[#fffaf0]/70 p-4 text-sm font-semibold leading-7 text-[#244762]">${item.content || "아직 답변 또는 원문이 없습니다."}</p>
          <div class="mt-4 flex justify-end gap-2">
            <button class="rounded-xl border border-brand-blue/15 bg-white/70 px-4 py-2 text-sm font-black text-[#244762]" type="button">상세 보기</button>
          </div>
        </article>
      `).join("");
    }

    function setActiveMenu(activeMenu) {
      const chatActive = activeMenu === "chat";
      chatViewButton.className = chatActive ? "flex h-[58px] w-full items-center gap-4 rounded-lg bg-gradient-to-br from-[#3d82ae] to-brand-blue px-5 text-left text-white shadow-[0_18px_36px_rgba(96,150,180,0.28)]" : "flex h-[58px] w-full items-center gap-4 rounded-lg px-5 text-left text-[#244762] hover:bg-white/55";
      inquiryHistoryButton.className = chatActive ? "flex h-[58px] w-full items-center gap-4 rounded-lg px-5 text-left text-[#244762] hover:bg-white/55" : "flex h-[58px] w-full items-center gap-4 rounded-lg bg-gradient-to-br from-[#3d82ae] to-brand-blue px-5 text-left text-white shadow-[0_18px_36px_rgba(96,150,180,0.28)]";
      chatViewButton.querySelector("span").className = chatActive ? "text-2xl text-white" : "text-2xl text-brand-blue";
      inquiryHistoryButton.querySelector("span").className = chatActive ? "text-2xl text-brand-blue" : "text-2xl text-white";
    }

    function showInquiryPage() {
      setActiveMenu("inquiry");
      renderInquiryHistoryPage();
      chatMainSection.classList.add("hidden");
      chatMainSection.classList.remove("flex");
      inquiryMainSection.classList.remove("hidden");
      inquiryMainSection.classList.add("flex");
      rightPanel.style.display = "none";
    }

    function showChatMainPage() {
      setActiveMenu("chat");
      inquiryMainSection.classList.add("hidden");
      inquiryMainSection.classList.remove("flex");
      chatMainSection.classList.remove("hidden");
      chatMainSection.classList.add("flex");
      rightPanel.style.display = "";
      chatFaqSection.classList.remove("hidden");
    }

    function buildWelcomeMessage(timeLabel = "새 대화 시작") {
      return `
        <div class="flex items-start gap-4">
          <div class="grid h-[52px] w-[52px] shrink-0 place-items-center rounded-full bg-white/65 text-[28px] text-brand-blue shadow-[0_10px_24px_rgba(16,47,74,0.08)]">✦</div>
          <article class="max-w-[620px] rounded-2xl rounded-tl-md bg-white/82 px-5 py-4 text-[15px] font-semibold leading-7 text-[#153958] shadow-[0_12px_30px_rgba(16,47,74,0.08)]">
            <p class="text-[17px] font-black leading-8">안녕하세요, 일상 고객센터 AI입니다.<br />무엇을 도와드릴까요?</p>
            <p class="mt-1 text-sm font-bold text-[#5b7890]">아래 카테고리를 선택하거나 궁금한 내용을 직접 입력해 주세요.</p>
            <div class="categoryBubblePanel mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <button class="categoryButton rounded-xl bg-brand-blue px-4 py-3 text-left text-sm font-black text-white" data-category="payment" type="button">결제/환불</button>
            <button class="categoryButton rounded-xl bg-white/65 px-4 py-3 text-left text-sm font-black text-[#244762]" data-category="faq" type="button">FAQ/가이드</button>
            <button class="categoryButton rounded-xl bg-white/65 px-4 py-3 text-left text-sm font-black text-[#244762]" data-category="bug" type="button">버그/오류</button>
            <button class="categoryButton rounded-xl bg-white/65 px-4 py-3 text-left text-sm font-black text-[#244762]" data-category="voc" type="button">VOC/건의</button>
            </div>
            <div class="mt-3 text-xs font-bold text-[#6c8799]">${timeLabel}</div>
          </article>
        </div>
      `;
    }

    function resetChat() {
      chatMessages.innerHTML = buildWelcomeMessage();
      bindCategoryButtons();
      bindQuickQuestions();
    }

    function bindCategoryButtons() {
      document.querySelectorAll(".categoryButton").forEach((button) => {
        if (button.dataset.bound === "true") return;
        button.dataset.bound = "true";
        button.addEventListener("click", () => {
          const category = button.dataset.category;
          const selected = faqByCategory[category] || faqByCategory.payment;
          showChatMainPage();
          renderCategoryFaq(category);
          document.querySelectorAll("#chatMessages .categoryBubblePanel").forEach((panel) => {
            panel.remove();
          });
          addUserMessage(selected.label);
          addAssistantMessage(selected.routeText);
        });
      });
    }

    function bindQuickQuestions() {
      document.querySelectorAll(".quickQuestion").forEach((button) => {
        if (button.dataset.bound === "true") return;
        button.dataset.bound = "true";
        button.addEventListener("click", () => {
          const question = button.textContent.replace("›", "").trim();
          addUserMessage(question);
          addAssistantMessage("해당 문의를 확인했어요. 계정과 결제 기록을 기준으로 안내가 필요한 항목을 정리해드릴게요.");
        });
      });
    }

    function renderCategoryFaq(category) {
      const selected = faqByCategory[category] || faqByCategory.payment;
      faqCategoryTitle.textContent = `${selected.label} 관련 문의`;
      faqList.innerHTML = selected.questions.map((question) => `
        <button class="quickQuestion flex w-full items-center justify-between rounded-xl bg-white/48 px-4 py-4 text-left text-sm font-black text-[#244762] shadow-[0_10px_24px_rgba(16,47,74,0.03)]" type="button">
          ${question} <span>›</span>
        </button>
      `).join("");

      document.querySelectorAll(".categoryButton").forEach((button) => {
        const active = button.dataset.category === category;
        button.className = active
          ? "categoryButton rounded-xl bg-brand-blue px-4 py-3 text-left text-sm font-black text-white"
          : "categoryButton rounded-xl bg-white/65 px-4 py-3 text-left text-sm font-black text-[#244762]";
      });
      bindQuickQuestions();
    }

    linkAccountButton.addEventListener("click", performLogin);
    logoutButton.addEventListener("click", () => {
      clientState.login = null;
      clientState.inquiries = [];
      clientState.activeTicketId = null;
      clientState.previousMessages = [];
      submittedInquiries.length = 0;
      resetChat();
      showLoginPage();
    });
    chatViewButton.addEventListener("click", showChatMainPage);
    newChatButton.addEventListener("click", () => {
      showChatMainPage();
      resetChat();
    });
    inquiryHistoryButton.addEventListener("click", showInquiryPage);
    backToChatButton.addEventListener("click", showChatMainPage);
    bindCategoryButtons();
    chatForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = chatInput.value.trim();
      if (!message) return;
      if (!clientState.login?.user_id) {
        openInfoModal("로그인 필요", "<p>먼저 계정을 연동한 뒤 문의를 전송해 주세요.</p>");
        return;
      }
      addUserMessage(message);
      chatInput.value = "";
      try {
        const payload = await window.ChatbotApi.sendChat({
          ticket_id: clientState.activeTicketId || submittedInquiries[0]?.ticketId || 1,
          user_message: message,
          account_id: clientState.login.account_id,
          user_id: clientState.login.user_id,
          session_id: clientState.sessionId,
          source_type: "chatbot",
          previous_messages: clientState.previousMessages,
        });
        clientState.previousMessages.push(
          { role: "user", content: message },
          { role: "assistant", content: payload.answer }
        );
        addAssistantMessage(payload.answer);
        await refreshInquiries();
      } catch (error) {
        console.error("chat failed", error);
        addAssistantMessage(`요청 처리 중 오류가 발생했습니다.\n${error.message || "잠시 후 다시 시도해 주세요."}`);
      }
      return;
      addAssistantMessage("문의 내용을 확인했어요. 데모 화면에서는 실제 API 호출 대신 답변 흐름만 보여드리고 있습니다.");
      chatInput.value = "";
    });
    bindCategoryButtons();
    bindQuickQuestions();
    renderCategoryFaq("payment");
    loadServerRegions();
});
